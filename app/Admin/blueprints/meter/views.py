# app/Admin/blueprints/meter/views.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, make_response
from app.extensions import db
from datetime import datetime, date, date
import io, csv
from openpyxl import Workbook  # pip install openpyxl

from app.Auth.blueprints.auth.views import login_required, role_required
from app.Admin.blueprints.customer.models import Customer
from .models import Meter

meter_bp = Blueprint("meter", __name__, template_folder="templates")

# ---------- helpers ----------
def _to_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None

def _apply_filters(q):
    """Reuse filters for list + exports."""
    customer_id = request.args.get("customer_id", type=int)
    status      = request.args.get("status")
    serial_q    = request.args.get("serial")       # search by meter_serial
    date_from   = request.args.get("date_from")
    date_to     = request.args.get("date_to")

    if customer_id:
        q = q.filter(Meter.customer_id == customer_id)
    if status:
        q = q.filter(Meter.status == status)
    if serial_q:
        q = q.filter(Meter.meter_serial.ilike(f"%{serial_q}%"))
    if date_from:
        d1 = _to_date(date_from)
        if d1:
            q = q.filter(Meter.install_date >= d1)
    if date_to:
        d2 = _to_date(date_to)
        if d2:
            q = q.filter(Meter.install_date <= d2)

    return q

# ---------- list (with pagination) ----------
@meter_bp.route("/admin/meters")
@login_required
@role_required("Admin")
def list_meters():
    # safe pagination
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    allowed_per_page = {10, 25, 50, 100}
    if per_page not in allowed_per_page:
        per_page = 25

    query = _apply_filters(Meter.query).order_by(Meter.id.desc())
    pagination = db.paginate(
        query, page=page, per_page=per_page, error_out=False, max_per_page=100
    )
    items = pagination.items

    # dropdowns: only ACTIVE customers
    active_customers = Customer.query.filter(Customer.status == "active")\
                        .order_by(Customer.customer_name.asc()).all()

    return render_template(
        "meter/list.html",
        meters=items,
        pagination=pagination,
        per_page=per_page,
        allowed_per_page=sorted(allowed_per_page),
        active_customers=active_customers,
    )

# ---------- create ----------
@meter_bp.route("/admin/meters/new", methods=["POST"])
@login_required
@role_required("Admin")
def create_meter():
    m = Meter(
        customer_id  = request.form.get("customer_id", type=int),
        meter_serial = (request.form.get("meter_serial") or "").strip(),
        install_date = date.today(),
        status       = (request.form.get("status") or "Active").strip(),
    )

    # quick validation
    if not m.customer_id or not m.meter_serial:
        flash("Customer and Meter Serial are required.", "danger")
        return redirect(url_for("meter.list_meters", **request.args))

    # optional: ensure selected customer is active
    cust = Customer.query.get(m.customer_id)
    if not cust or cust.status != "active":
        flash("Selected customer must be active.", "danger")
        return redirect(url_for("meter.list_meters", **request.args))
    db.session.add(m)
    try:
        db.session.commit()
        flash("Meter created.", "success")
    except Exception as e:
        db.session.rollback()
        # likely unique violation on meter_serial
        flash("Failed to create meter (is serial unique?).", "danger")
    return redirect(url_for("meter.list_meters", **request.args))

# ---------- edit ----------
@meter_bp.route("/admin/meters/<int:meter_id>/edit", methods=["POST"])
@login_required
@role_required("Admin")
def edit_meter(meter_id):
    m = Meter.query.get_or_404(meter_id)

    m.customer_id  = request.form.get("customer_id", type=int)
    m.meter_serial = (request.form.get("meter_serial") or "").strip()
    m.status       = (request.form.get("status") or "Active").strip()

    if not m.customer_id or not m.meter_serial:
        flash("Customer and Meter Serial are required.", "danger")
        return redirect(url_for("meter.list_meters", **request.args))

    # ensure selected customer is active
    cust = Customer.query.get(m.customer_id)
    if not cust or cust.status != "active":
        flash("Selected customer must be active.", "danger")
        return redirect(url_for("meter.list_meters", **request.args))

    try:
        db.session.commit()
        flash("Meter updated.", "success")
    except Exception:
        db.session.rollback()
        flash("Failed to update meter (is serial unique?).", "danger")
    return redirect(url_for("meter.list_meters", **request.args))

# ---------- delete ----------
@meter_bp.route("/admin/meters/<int:meter_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def delete_meter(meter_id):
    m = Meter.query.get_or_404(meter_id)
    db.session.delete(m)
    db.session.commit()
    flash("Meter deleted.", "info")
    return redirect(url_for("meter.list_meters", **request.args))

# ---------- exports (respect current filters) ----------
@meter_bp.route("/admin/meters/export.csv")
@login_required
@role_required("Admin")
def export_csv():
    query = _apply_filters(Meter.query).order_by(Meter.id.asc())
    rows = query.all()

    headers = ["ID", "Customer", "Meter Serial", "Install Date", "Status"]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)

    for m in rows:
        writer.writerow([
            m.id,
            m.customer.customer_name if m.customer else m.customer_id,
            m.meter_serial or "",
            m.install_date.isoformat() if m.install_date else "",
            m.status or "",
        ])

    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    fname = f"meters_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    resp.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp

@meter_bp.route("/admin/meters/export.xlsx")
@login_required
@role_required("Admin")
def export_xlsx():
    query = _apply_filters(Meter.query).order_by(Meter.id.asc())
    rows = query.all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Meters"

    headers = ["ID", "Customer", "Meter Serial", "Install Date", "Status"]
    ws.append(headers)

    for m in rows:
        ws.append([
            m.id,
            m.customer.customer_name if m.customer else m.customer_id,
            m.meter_serial or "",
            m.install_date.isoformat() if m.install_date else None,
            m.status or "",
        ])

    # simple auto-width
    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(12, max_len + 2), 40)

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f"meters_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        bio,
        as_attachment=True,
        download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
