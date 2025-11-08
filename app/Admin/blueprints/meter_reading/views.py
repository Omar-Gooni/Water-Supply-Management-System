from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, make_response
from app.extensions import db
from datetime import datetime
import io, csv
from openpyxl import Workbook

from app.Auth.blueprints.auth.views import login_required, role_required
from app.Admin.blueprints.customer.models import Customer
from app.Admin.blueprints.meter.models import Meter
from .models import MeterReading

meter_reading_bp = Blueprint("meter_reading", __name__, template_folder="templates")

# ---------- helpers ----------
def _to_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None

def _apply_filters(q):
    customer_id = request.args.get("customer_id", type=int)
    date_from   = request.args.get("date_from")
    date_to     = request.args.get("date_to")

    if customer_id:
        q = q.filter(MeterReading.customer_id == customer_id)
    if date_from:
        d1 = _to_date(date_from)
        if d1:
            q = q.filter(MeterReading.reading_date >= d1)
    if date_to:
        d2 = _to_date(date_to)
        if d2:
            q = q.filter(MeterReading.reading_date <= d2)
    return q

# ---------- list (with pagination) ----------
@meter_reading_bp.route("/admin/meter-readings")
@login_required
@role_required("Admin")
def list_readings():
    # pagination
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    allowed_per_page = {10, 25, 50, 100}
    if per_page not in allowed_per_page:
        per_page = 25

    query = _apply_filters(MeterReading.query).order_by(MeterReading.id.desc())
    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False, max_per_page=100)
    items = pagination.items

    # dropdown: only ACTIVE customers (as you wanted earlier)
    active_customers = Customer.query.filter(Customer.status == "active") \
                        .order_by(Customer.customer_name.asc()).all()

    # --- NEW: build mapping customer_id -> {id, serial} from Meter table ---
    # You asked: when selecting a customer, auto-fill its meter and make it read-only,
    # regardless of meter status. So we take the first meter found for each customer.
    meters = Meter.query.order_by(Meter.id.asc()).all()
    customer_to_meter = {}
    for m in meters:
        if m.customer_id and m.customer_id not in customer_to_meter:
            customer_to_meter[m.customer_id] = {"id": m.id, "serial": m.meter_serial or ""}

    return render_template(
        "meter_reading/list.html",
        readings=items,
        pagination=pagination,
        per_page=per_page,
        allowed_per_page=sorted(allowed_per_page),
        active_customers=active_customers,
        customer_to_meter=customer_to_meter,  # <-- make it available to Jinja
    )

# ---------- create ----------
@meter_reading_bp.route("/admin/meter-readings/new", methods=["POST"])
@login_required
@role_required("Admin")
def create_reading():
    rec = MeterReading(
        customer_id     = request.form.get("customer_id", type=int),
        meter_id        = request.form.get("meter_id", type=int),
        reading_date    = _to_date(request.form.get("reading_date")),
        last_read_m3    = request.form.get("last_read_m3") or None,
        current_read_m3 = request.form.get("current_read_m3") or None,
        used_water_m3   = request.form.get("used_water_m3") or None,
        rate_per_m3     = request.form.get("rate_per_m3") or None,
        amount_due      = request.form.get("amount_due") or None,
    )

    if not rec.customer_id or not rec.meter_id or not rec.reading_date:
        flash("Customer, Meter and Reading Date are required.", "danger")
        return redirect(url_for("meter_reading.list_readings", **request.args))

    db.session.add(rec)
    db.session.commit()
    flash("Meter reading created.", "success")
    return redirect(url_for("meter_reading.list_readings", **request.args))

# ---------- edit ----------
@meter_reading_bp.route("/admin/meter-readings/<int:rec_id>/edit", methods=["POST"])
@login_required
@role_required("Admin")
def edit_reading(rec_id):
    rec = MeterReading.query.get_or_404(rec_id)

    rec.customer_id     = request.form.get("customer_id", type=int)
    rec.meter_id        = request.form.get("meter_id", type=int)
    rec.reading_date    = _to_date(request.form.get("reading_date"))
    rec.last_read_m3    = request.form.get("last_read_m3") or None
    rec.current_read_m3 = request.form.get("current_read_m3") or None
    rec.used_water_m3   = request.form.get("used_water_m3") or None
    rec.rate_per_m3     = request.form.get("rate_per_m3") or None
    rec.amount_due      = request.form.get("amount_due") or None

    if not rec.customer_id or not rec.meter_id or not rec.reading_date:
        flash("Customer, Meter and Reading Date are required.", "danger")
        return redirect(url_for("meter_reading.list_readings", **request.args))

    db.session.commit()
    flash("Meter reading updated.", "success")
    return redirect(url_for("meter_reading.list_readings", **request.args))

# ---------- delete ----------
@meter_reading_bp.route("/admin/meter-readings/<int:rec_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def delete_reading(rec_id):
    rec = MeterReading.query.get_or_404(rec_id)
    db.session.delete(rec)
    db.session.commit()
    flash("Meter reading deleted.", "info")
    return redirect(url_for("meter_reading.list_readings", **request.args))

# ---------- exports (respect filters) ----------
@meter_reading_bp.route("/admin/meter-readings/export.csv")
@login_required
@role_required("Admin")
def export_csv():
    query = _apply_filters(MeterReading.query).order_by(MeterReading.id.asc())
    rows = query.all()

    headers = [
        "ID", "Reading Date", "Customer", "Meter",
        "Last (m3)", "Current (m3)", "Used (m3)", "Rate", "Amount"
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for r in rows:
        writer.writerow([
            r.id,
            r.reading_date.isoformat() if r.reading_date else "",
            r.customer.customer_name if r.customer else r.customer_id,
            r.meter.meter_serial if r.meter else r.meter_id,
            f"{r.last_read_m3:.2f}" if r.last_read_m3 is not None else "",
            f"{r.current_read_m3:.2f}" if r.current_read_m3 is not None else "",
            f"{r.used_water_m3:.2f}" if r.used_water_m3 is not None else "",
            f"{r.rate_per_m3:.2f}" if r.rate_per_m3 is not None else "",
            f"{r.amount_due:.2f}" if r.amount_due is not None else "",
        ])

    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    fname = f"meter_readings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    resp.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp

@meter_reading_bp.route("/admin/meter-readings/export.xlsx")
@login_required
@role_required("Admin")
def export_xlsx():
    query = _apply_filters(MeterReading.query).order_by(MeterReading.id.asc())
    rows = query.all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Meter Readings"

    headers = [
        "ID", "Reading Date", "Customer", "Meter",
        "Last (m³)", "Current (m³)", "Used (m³)", "Rate", "Amount"
    ]
    ws.append(headers)

    for r in rows:
        ws.append([
            r.id,
            r.reading_date.isoformat() if r.reading_date else None,
            r.customer.customer_name if r.customer else r.customer_id,
            r.meter.meter_serial if r.meter else r.meter_id,
            float(r.last_read_m3) if r.last_read_m3 is not None else None,
            float(r.current_read_m3) if r.current_read_m3 is not None else None,
            float(r.used_water_m3) if r.used_water_m3 is not None else None,
            float(r.rate_per_m3) if r.rate_per_m3 is not None else None,
            float(r.amount_due) if r.amount_due is not None else None,
        ])

    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(12, max_len + 2), 40)

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f"meter_readings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        bio,
        as_attachment=True,
        download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )



