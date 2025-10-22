# app/Admin/blueprints/invoice/views.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, make_response
from datetime import date
import csv, io
from openpyxl import Workbook 
from app.extensions import db
from app.Auth.blueprints.auth.views import login_required, role_required

from reportlab.pdfgen import canvas # pip install reportlab
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from app.Admin.blueprints.customer.models import Customer
from app.Admin.blueprints.meter.models import Meter
from app.Admin.blueprints.meter_reading.models import MeterReading
from .models import Invoice


invoice_bp = Blueprint("invoice", __name__, template_folder="templates")


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
        rate = float(r.rate_per_m3 or 0.75)
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

def _rollover_overdue(invoices: list[Invoice]) -> None:
    """Flip unpaid -> overdue when due_date has passed for the listed invoices."""
    today = _today()
    changed = False
    for inv in invoices:
        if inv.status == "unpaid" and inv.due_date and inv.due_date < today:
            inv.status = "overdue"
            changed = True
    if changed:
        db.session.commit()

def _apply_filters(q):
    """
    Filters for list + exports:
      - customer_id
      - status (unpaid/paid/overdue/draft/void)
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

    # auto-update status to overdue if past due
    _rollover_overdue(invoices)

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
        default_rate=0.75,
        today=_today(),
    )


# ----------------- create -----------------
@invoice_bp.route("/admin/invoices/new", methods=["POST"])
@login_required
@role_required("Admin")
def create_invoice():
    # required selections
    customer_id = request.form.get("customer_id", type=int)
    if not customer_id:
        flash("Customer is required.", "danger")
        return redirect(url_for("invoice.list_invoices", **request.args))

    # required dates
    try:
        issue_date   = date.fromisoformat(request.form.get("issue_date"))
        due_date     = date.fromisoformat(request.form.get("due_date"))
        period_start = date.fromisoformat(request.form.get("period_start"))
        period_end   = date.fromisoformat(request.form.get("period_end"))
    except Exception:
        flash("Issue date, Due date, Period start and Period end are required and must be valid.", "danger")
        return redirect(url_for("invoice.list_invoices", **request.args))

    # validate ordering
    if period_end < period_start:
        flash("Period end cannot be before period start.", "danger")
        return redirect(url_for("invoice.list_invoices", **request.args))
    if due_date < issue_date:
        flash("Due date cannot be before issue date.", "danger")
        return redirect(url_for("invoice.list_invoices", **request.args))

    # ---- Overlap check (same customer, any status) ----
    existing = Invoice.query.filter(Invoice.customer_id == customer_id).all()
    for inv in existing:
        if _period_overlaps(period_start, period_end, inv.period_start, inv.period_end):
            flash("This customer already has an invoice that overlaps the chosen period.", "danger")
            return redirect(url_for("invoice.list_invoices", **request.args))

    # snapshot values (read-only fields on form)
    reading_id     = request.form.get("reading_id", type=int) or None
    last_read      = float(request.form.get("last_read_m3") or 0)
    current_read   = float(request.form.get("current_read_m3") or 0)
    used_m3        = float(request.form.get("used_water_m3") or max(0, current_read - last_read))
    rate_m3        = float(request.form.get("rate_per_m3") or 0.75)
    amount         = float(request.form.get("amount") or (used_m3 * rate_m3))
    currency       = (request.form.get("currency") or "").strip() or None
    remarks        = (request.form.get("remarks") or "").strip() or None

    # IMPORTANT: Do NOT set invoice_no here (model generates INV-0001 style)
    inv = Invoice(
        customer_id=customer_id,
        reading_id=reading_id,
        period_start=period_start,
        period_end=period_end,
        last_read_m3=last_read,
        current_read_m3=current_read,
        used_water_m3=used_m3,
        rate_per_m3=rate_m3,
        amount=amount,
        issue_date=issue_date,
        due_date=due_date,
        status="unpaid",  # locked on create
        currency=currency,
        remarks=remarks,
    )

    db.session.add(inv)
    db.session.commit()
    flash(f"Invoice {inv.invoice_no} created (status: unpaid).", "success")
    return redirect(url_for("invoice.list_invoices", **request.args))


# ----------------- mark paid -----------------
@invoice_bp.route("/admin/invoices/<int:invoice_id>/paid", methods=["POST"])
@login_required
@role_required("Admin")
def mark_paid(invoice_id: int):
    inv = Invoice.query.get_or_404(invoice_id)
    if inv.status != "paid":
        inv.status = "paid"
        db.session.commit()
        flash("Invoice marked as PAID.", "success")
    else:
        flash("Invoice already paid.", "info")
    return redirect(url_for("invoice.list_invoices", **request.args))


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

# ---------- print (PDF display using ReportLab) ----------
@invoice_bp.route("/admin/invoices/<int:invoice_id>/print")
@login_required
@role_required("Admin")
def print_invoice(invoice_id: int):
    inv = Invoice.query.get_or_404(invoice_id)
    cust = inv.customer
    # ... rest of your object fetching (reading, meter, org)
    
    # Org info (same as before)
    org = {
        "name": "Water Supply Management System",
        "address": "Main Office, City",
        "phone": "+252 61 000 0000",
        "email": "billing@wsms.local",
    }

    # Use a BytesIO buffer to hold the PDF in memory
    buffer = io.BytesIO()
    
    # Create the PDF document template
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    Story = [] # This list holds all the elements to be drawn on the PDF

    # --- 1. Header/Organization Info ---
    # Add your organization name
    Story.append(Paragraph(f"**{org['name']}**", styles['h2']))
    Story.append(Paragraph(org['address'], styles['Normal']))
    Story.append(Paragraph(org['phone'], styles['Normal']))
    Story.append(Paragraph(org['email'], styles['Normal']))
    Story.append(Spacer(1, 12))

    # --- 2. Invoice Details Table ---
    invoice_data = [
        ["INVOICE #:", inv.invoice_no or ""],
        ["Status:", inv.status or ""],
        ["Issue Date:", inv.issue_date.isoformat() if inv.issue_date else ""],
        ["Due Date:", inv.due_date.isoformat() if inv.due_date else ""],
    ]
    invoice_table = Table(invoice_data, colWidths=[100, 200])
    invoice_table.setStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
    ])
    Story.append(invoice_table)
    Story.append(Spacer(1, 24))

    # --- 3. Customer Info ---
    Story.append(Paragraph("<b>CUSTOMER</b>", styles['h4']))
    Story.append(Paragraph(f"**{cust.customer_name}**", styles['Normal']))
    Story.append(Paragraph(cust.address or '', styles['Normal']))
    Story.append(Paragraph(cust.phone or '', styles['Normal']))
    Story.append(Spacer(1, 24))

    # --- 4. Meter Reading Details Table ---
    table_headers = ["Description", "Last (m³)", "Current (m³)", "Used (m³)", "Rate", "Amount"]
    
    # Format the data row
    data_row = [
        f"Water usage ({inv.period_start} - {inv.period_end})",
        f"{inv.last_read_m3:.2f}" if inv.last_read_m3 is not None else "0.00",
        f"{inv.current_read_m3:.2f}" if inv.current_read_m3 is not None else "0.00",
        f"{inv.used_water_m3:.2f}" if inv.used_water_m3 is not None else "0.00",
        f"{inv.rate_per_m3:.2f} {inv.currency or 'USD'}",
        f"{inv.amount:.2f} {inv.currency or 'USD'}",
    ]
    
    item_data = [table_headers, data_row]
    
    item_table = Table(item_data, colWidths=[180, 70, 70, 70, 70, 70])
    item_table.setStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey), # Header background
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke), # Header text
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'), # Numeric columns align right
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
    ])
    Story.append(item_table)
    Story.append(Spacer(1, 12))
    
    # --- 5. Total ---
    total_data = [
        ["TOTAL:", f"{inv.amount:.2f} {inv.currency or 'USD'}"],
    ]
    total_table = Table(total_data, colWidths=[300, 150]) # Aligned right on the page
    total_table.setStyle([
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
    ])
    Story.append(total_table)

    # --- 6. Build the PDF ---
    doc.build(Story)
    
    # Go to the start of the BytesIO buffer
    buffer.seek(0)
    
    # Return the PDF file as a response
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=False, # This is key for 'inline' display
        download_name=f"Invoice_{inv.invoice_no}.pdf"
    )

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
        "Last Read (m3)", "Current Read (m3)", "Used (m3)", "Rate/m3", "Amount",
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
        "Last Read (m3)", "Current Read (m3)", "Used (m3)", "Rate/m3", "Amount",
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
