from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, send_file

from datetime import date, timedelta
import csv, io
from openpyxl import Workbook
from sqlalchemy import func
from app.extensions import db
from app.Auth.blueprints.auth.views import login_required, role_required


from app.Admin.blueprints.customer.models import Customer
from app.Admin.blueprints.meter.models import Meter
from app.Admin.blueprints.meter_reading.models import MeterReading
from app.Admin.blueprints.receipt.models import Receipt
from app.utils.billing import apply_invoice_payment, get_default_water_rate
from .models import Invoice


invoice_bp = Blueprint("invoice", __name__, template_folder="templates")

INVOICE_STATUSES = ("unpaid", "partial", "paid")


# ----------------- helpers -----------------
def _today() -> date:
    return date.today()

def _period_overlaps(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    """Closed interval overlap: [a_start, a_end] vs [b_start, b_end]."""
    return a_start <= b_end and a_end >= b_start

def _customer_latest_reading_snapshot() -> dict[int, dict]:
    """
    Build a snapshot per ACTIVE customer of their most recent meter reading:
    {
      customer_id: {
        reading_id, meter_serial, reading_date, last_read_m3,
        current_read_m3, used_water_m3, rate_per_m3, amount
      }
    }
    Used to auto-fill read-only fields on the create form.
    """
    active_customers = Customer.query.filter(Customer.status == "active").all()
    cust_ids = [c.id for c in active_customers]
    if not cust_ids:
        return {}

    readings = (
        MeterReading.query
        .filter(MeterReading.customer_id.in_(cust_ids))
        .order_by(
            MeterReading.customer_id.asc(),
            MeterReading.reading_date.desc(),
            MeterReading.id.desc(),
        )
        .all()
    )
    meters = Meter.query.all()
    meter_by_id = {m.id: m for m in meters}

    latest = {}
    for r in readings:
        if r.customer_id in latest:
            continue
        m = meter_by_id.get(r.meter_id)
        used = float(r.used_water_m3 or max(0, (r.current_read_m3 or 0) - (r.last_read_m3 or 0)))
        rate = float(r.rate_per_m3 or get_default_water_rate())
        latest[r.customer_id] = {
            "reading_id": r.id,
            "meter_serial": (m.meter_serial if m else "") or "",
            "reading_date": r.reading_date.isoformat() if r.reading_date else "",
            "last_read_m3": float(r.last_read_m3 or 0),
            "current_read_m3": float(r.current_read_m3 or 0),
            "used_water_m3": used,
            "rate_per_m3": rate,
            "amount": round(used * rate, 2),
        }
    return latest

def sync_invoice_from_reading(reading: MeterReading, *, status: str = "unpaid") -> Invoice:
    """Create or update the invoice that belongs to a meter reading."""
    issue_date = reading.reading_date or _today()
    try:
        period_start = issue_date.replace(day=1)
    except ValueError:
        period_start = issue_date
    period_end = issue_date
    due_date = issue_date + timedelta(days=14)

    last_read = float(reading.last_read_m3 or 0)
    current_read = float(reading.current_read_m3 or 0)
    used_m3 = float(reading.used_water_m3 or max(0, current_read - last_read))
    rate_m3 = float(reading.rate_per_m3 or get_default_water_rate())
    amount = float(reading.amount_due or (used_m3 * rate_m3))

    inv = Invoice.query.filter_by(reading_id=reading.id).first()
    if inv is None:
        inv = Invoice(reading_id=reading.id)
        db.session.add(inv)

    previous_paid = float(inv.amount_paid or 0)

    inv.customer_id = reading.customer_id
    inv.period_start = period_start
    inv.period_end = period_end
    inv.last_read_m3 = last_read
    inv.current_read_m3 = current_read
    inv.used_water_m3 = used_m3
    inv.rate_per_m3 = rate_m3
    inv.amount = amount
    inv.amount_paid = previous_paid
    inv.balance_due = max(round(amount - previous_paid, 2), 0)
    inv.issue_date = issue_date
    inv.due_date = due_date

    if previous_paid >= amount and amount > 0:
        inv.status = "paid"
    elif previous_paid > 0:
        inv.status = "partial"
    elif inv.status not in INVOICE_STATUSES:
        inv.status = status if status in INVOICE_STATUSES else "unpaid"

    return inv

def _apply_filters(q):
    """
    Filters for list + exports:
      - customer_id
      - status (unpaid/partial/paid)
      - invoice_no (contains)
      - issued_from / issued_to   (issue_date range)
      - period_from / period_to   (period range intersects)
    """
    customer_id = request.args.get("customer_id", type=int)
    status      = request.args.get("status", type=str)
    invoice_no  = request.args.get("invoice_no", type=str)
    issued_from = request.args.get("issued_from", type=str)
    issued_to   = request.args.get("issued_to", type=str)
    period_from = request.args.get("period_from", type=str)
    period_to   = request.args.get("period_to", type=str)

    if customer_id:
        q = q.filter(Invoice.customer_id == customer_id)
    if status:
        q = q.filter(Invoice.status == status)
    if invoice_no:
        like = f"%{invoice_no.strip()}%"
        q = q.filter(Invoice.invoice_no.ilike(like))

    # issue_date range
    if issued_from:
        try:
            d1 = date.fromisoformat(issued_from)
            q = q.filter(Invoice.issue_date >= d1)
        except Exception:
            pass
    if issued_to:
        try:
            d2 = date.fromisoformat(issued_to)
            q = q.filter(Invoice.issue_date <= d2)
        except Exception:
            pass

    # period intersection (if both given, require overlap)
    try:
        p_from = date.fromisoformat(period_from) if period_from else None
    except Exception:
        p_from = None
    try:
        p_to = date.fromisoformat(period_to) if period_to else None
    except Exception:
        p_to = None

    if p_from and p_to:
        q = q.filter((Invoice.period_start <= p_to) & (Invoice.period_end >= p_from))
    elif p_from:
        q = q.filter(Invoice.period_end >= p_from)
    elif p_to:
        q = q.filter(Invoice.period_start <= p_to)

    return q


# ----------------- list -----------------
@invoice_bp.route("/admin/invoices")
@login_required
@role_required("Admin")
def list_invoices():
    # pagination guard
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    if per_page not in {10, 25, 50, 100}:
        per_page = 25

    base_q = _apply_filters(Invoice.query)
    pagination = db.paginate(
        base_q.order_by(Invoice.id.desc()),
        page=page,
        per_page=per_page,
        error_out=False,
        max_per_page=100,
    )
    invoices = pagination.items

    summary_rows = (
        base_q.with_entities(
            Invoice.status,
            func.count(Invoice.id),
            func.coalesce(func.sum(Invoice.amount), 0),
            func.coalesce(func.sum(Invoice.balance_due), 0),
        )
        .group_by(Invoice.status)
        .all()
    )
    summary_map = {
        (status or "unpaid").lower(): {
            "count": int(count or 0),
            "amount": float(total_amount or 0),
            "balance": float(total_balance or 0),
        }
        for status, count, total_amount, total_balance in summary_rows
    }
    invoice_summary = {
        "total_count": pagination.total,
        "total_amount": float(sum(float(inv.amount or 0) for inv in invoices)),
        "total_balance": float(sum(float(inv.balance_due or 0) for inv in invoices)),
        "unpaid_count": summary_map.get("unpaid", {}).get("count", 0),
        "partial_count": summary_map.get("partial", {}).get("count", 0),
        "paid_count": summary_map.get("paid", {}).get("count", 0),
        "unpaid_amount": summary_map.get("unpaid", {}).get("amount", 0.0),
        "partial_amount": summary_map.get("partial", {}).get("amount", 0.0),
        "paid_amount": summary_map.get("paid", {}).get("amount", 0.0),
    }

    # dropdown + auto-fill map
    active_customers = Customer.query.filter(Customer.status == "active") \
                                     .order_by(Customer.customer_name.asc()).all()
    customer_latest = _customer_latest_reading_snapshot()

    return render_template(
        "invoice/list.html",
        invoices=invoices,
        pagination=pagination,
        per_page=per_page,
        allowed_per_page=[10, 25, 50, 100],
        customers=active_customers,
        customer_latest=customer_latest,
        default_rate=get_default_water_rate(),
        today=_today(),
        invoice_summary=invoice_summary,
    )


# ----------------- create -----------------
@invoice_bp.route("/admin/invoices/new", methods=["POST"])
@login_required
@role_required("Admin")
def create_invoice():
    flash("Invoices are created automatically from meter readings.", "info")
    return redirect(url_for("invoice.list_invoices", **request.args))


@invoice_bp.route("/admin/invoices/<int:invoice_id>/payment", methods=["POST"])
@login_required
@role_required("Admin")
def record_payment(invoice_id: int):
    inv = Invoice.query.get_or_404(invoice_id)

    try:
        payment_amount = float(request.form.get("payment_amount", 0))
    except (TypeError, ValueError):
        payment_amount = 0.0

    if payment_amount <= 0:
        flash("Enter a valid payment amount.", "danger")
        return redirect(url_for("receipt.list_receipts", customer_id=inv.customer_id))

    applied, balance_before, balance_after, status = apply_invoice_payment(inv, payment_amount)
    if applied <= 0:
        flash("This invoice is already fully paid.", "info")
        return redirect(url_for("receipt.list_receipts", customer_id=inv.customer_id))

    receipt = Receipt(
        invoice_id=inv.id,
        customer_id=inv.customer_id,
        amount_paid=applied,
        balance_before=balance_before,
        balance_after=balance_after,
        payment_date=_today(),
    )
    db.session.add(receipt)
    db.session.commit()

    if payment_amount > applied:
        flash(f"Only {applied:.2f} was applied because that is the remaining balance. Receipt {receipt.receipt_no} created.", "warning")
    else:
        flash(f"Receipt {receipt.receipt_no} created. Invoice is now {status.title()}.", "success")
    return redirect(url_for("receipt.list_receipts", customer_id=inv.customer_id))

# ----------------- delete -----------------
@invoice_bp.route("/admin/invoices/<int:invoice_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def delete_invoice(invoice_id: int):
    inv = Invoice.query.get_or_404(invoice_id)
    db.session.delete(inv)
    db.session.commit()
    flash("Invoice deleted.", "info")
    return redirect(url_for("invoice.list_invoices", **request.args))
# ----------------- exports (respect filters) -----------------
@invoice_bp.route("/admin/invoices/export.csv")
@login_required
@role_required("Admin")
def export_csv():
    q = _apply_filters(Invoice.query).order_by(Invoice.id.asc())
    rows = q.all()

    headers = [
        "Invoice No", "Customer", "Meter Serial", "Reading ID",
        "Period Start", "Period End",
        "Last Read (m3)", "Current Read (m3)", "Used (m3)", "Rate/m3", "Amount", "Amount Paid", "Balance Due",
        "Issue Date", "Due Date", "Status", "Currency", "Remarks"
    ]

    customers = {c.id: c for c in Customer.query.all()}
    meters = {m.id: m for m in Meter.query.all()}
    readings = {r.id: r for r in MeterReading.query.all()}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)

    for inv in rows:
        cust = customers.get(inv.customer_id)
        reading = readings.get(inv.reading_id)
        meter_serial = meters.get(reading.meter_id).meter_serial if (reading and reading.meter_id in meters) else ""
        writer.writerow([
            inv.invoice_no or "",
            (cust.customer_name if cust else inv.customer_id),
            meter_serial,
            inv.reading_id or "",
            inv.period_start.isoformat() if inv.period_start else "",
            inv.period_end.isoformat() if inv.period_end else "",
            f"{inv.last_read_m3:.2f}" if inv.last_read_m3 is not None else "",
            f"{inv.current_read_m3:.2f}" if inv.current_read_m3 is not None else "",
            f"{inv.used_water_m3:.2f}" if inv.used_water_m3 is not None else "",
            f"{inv.rate_per_m3:.4f}" if inv.rate_per_m3 is not None else "",
            f"{inv.amount:.2f}" if inv.amount is not None else "",
            f"{inv.amount_paid:.2f}" if inv.amount_paid is not None else "",
            f"{inv.balance_due:.2f}" if inv.balance_due is not None else "",
            inv.issue_date.isoformat() if inv.issue_date else "",
            inv.due_date.isoformat() if inv.due_date else "",
            inv.status or "",
            inv.currency or "",
            inv.remarks or "",
        ])

    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    fname = f"invoices_{_today().strftime('%Y%m%d')}.csv"
    resp.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp


@invoice_bp.route("/admin/invoices/export.xlsx")
@login_required
@role_required("Admin")
def export_xlsx():
    q = _apply_filters(Invoice.query).order_by(Invoice.id.asc())
    rows = q.all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Invoices"

    headers = [
        "Invoice No", "Customer", "Meter Serial", "Reading ID",
        "Period Start", "Period End",
        "Last Read (m3)", "Current Read (m3)", "Used (m3)", "Rate/m3", "Amount", "Amount Paid", "Balance Due",
        "Issue Date", "Due Date", "Status", "Currency", "Remarks"
    ]
    ws.append(headers)

    customers = {c.id: c for c in Customer.query.all()}
    meters = {m.id: m for m in Meter.query.all()}
    readings = {r.id: r for r in MeterReading.query.all()}

    for inv in rows:
        cust = customers.get(inv.customer_id)
        reading = readings.get(inv.reading_id)
        meter_serial = meters.get(reading.meter_id).meter_serial if (reading and reading.meter_id in meters) else ""
        ws.append([
            inv.invoice_no or "",
            (cust.customer_name if cust else inv.customer_id),
            meter_serial,
            inv.reading_id or None,
            inv.period_start.isoformat() if inv.period_start else None,
            inv.period_end.isoformat() if inv.period_end else None,
            float(inv.last_read_m3) if inv.last_read_m3 is not None else None,
            float(inv.current_read_m3) if inv.current_read_m3 is not None else None,
            float(inv.used_water_m3) if inv.used_water_m3 is not None else None,
            float(inv.rate_per_m3) if inv.rate_per_m3 is not None else None,
            float(inv.amount) if inv.amount is not None else None,
            float(inv.amount_paid) if inv.amount_paid is not None else None,
            float(inv.balance_due) if inv.balance_due is not None else None,
            inv.issue_date.isoformat() if inv.issue_date else None,
            inv.due_date.isoformat() if inv.due_date else None,
            inv.status or "",
            inv.currency or "",
            inv.remarks or "",
        ])

    # simple auto-width
    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(12, max_len + 2), 42)

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f"invoices_{_today().strftime('%Y%m%d')}.xlsx"
    return send_file(
        bio,
        as_attachment=True,
        download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

@invoice_bp.route("/admin/invoices/<int:invoice_id>/print")
@login_required
@role_required("Admin")
def print_invoice(invoice_id):
    inv = Invoice.query.get_or_404(invoice_id)
    cust = inv.customer
    reading = inv.reading
    meter = reading.meter if (reading and hasattr(reading, "meter")) else None

    return render_template(
        "invoice/invoice_print.html",  # make sure filename matches
        inv=inv,
        cust=cust,
        reading=reading,
        meter=meter,
        today  =_today(),
    )






