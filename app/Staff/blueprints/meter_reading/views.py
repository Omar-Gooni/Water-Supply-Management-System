from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.extensions import db
from datetime import datetime

from app.Auth.blueprints.auth.views import login_required, role_required
from app.Admin.blueprints.customer.models import Customer
from app.Admin.blueprints.meter.models import Meter
from app.Admin.blueprints.invoice.views import sync_invoice_from_reading
from app.Admin.blueprints.meter_reading.models import MeterReading
from app.Staff.helpers import current_staff_service_area_id, current_staff_user
from app.utils.billing import calculate_reading_values, customer_reading_snapshot, get_default_water_rate

meter_reading_bp = Blueprint("staff_meter_reading", __name__, template_folder="templates")


def _to_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _apply_filters(query, service_area_id):
    customer_id = request.args.get("customer_id", type=int)
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")

    if service_area_id:
        query = query.join(Customer, Customer.id == MeterReading.customer_id).filter(Customer.service_area_id == service_area_id)
    else:
        query = query.filter(False)

    if customer_id:
        query = query.filter(MeterReading.customer_id == customer_id)
    if date_from:
        d1 = _to_date(date_from)
        if d1:
            query = query.filter(MeterReading.reading_date >= d1)
    if date_to:
        d2 = _to_date(date_to)
        if d2:
            query = query.filter(MeterReading.reading_date <= d2)
    return query


def _customer_meter_map(service_area_id):
    meters = (
        Meter.query.join(Customer, Customer.id == Meter.customer_id)
        .filter(Customer.service_area_id == service_area_id)
        .order_by(Meter.id.asc())
        .all()
        if service_area_id else []
    )
    customer_to_meter = {}
    for meter in meters:
        if meter.customer_id and meter.customer_id not in customer_to_meter:
            customer_to_meter[meter.customer_id] = {"id": meter.id, "serial": meter.meter_serial or ""}
    return customer_to_meter


def _allowed_customer(service_area_id, customer_id):
    if not service_area_id or not customer_id:
        return None
    return Customer.query.filter(
        Customer.id == customer_id,
        Customer.service_area_id == service_area_id,
    ).first()


@meter_reading_bp.route("/staff/meter-readings")
@login_required
@role_required("Staff")
def list_readings():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    allowed_per_page = {10, 25, 50, 100}
    if per_page not in allowed_per_page:
        per_page = 25

    staff_user = current_staff_user()
    service_area_id = current_staff_service_area_id()

    query = _apply_filters(MeterReading.query, service_area_id).order_by(MeterReading.id.desc())
    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False, max_per_page=100)

    active_customers = []
    if service_area_id:
        active_customers = (
            Customer.query
            .filter(Customer.status == "active", Customer.service_area_id == service_area_id)
            .order_by(Customer.customer_name.asc())
            .all()
        )

    customer_to_meter = _customer_meter_map(service_area_id)

    return render_template(
        "meter_reading/list.html",
        readings=pagination.items,
        pagination=pagination,
        per_page=per_page,
        allowed_per_page=sorted(allowed_per_page),
        active_customers=active_customers,
        customer_to_meter=customer_to_meter,
        customer_latest=customer_reading_snapshot(),
        default_rate=get_default_water_rate(),
        staff_user=staff_user,
        service_area_name=staff_user.service_area.area_name if staff_user and staff_user.service_area else None,
    )


@meter_reading_bp.route("/staff/meter-readings/new", methods=["POST"])
@login_required
@role_required("Staff")
def create_reading():
    service_area_id = current_staff_service_area_id()
    customer_id = request.form.get("customer_id", type=int)
    meter_id = request.form.get("meter_id", type=int)
    reading_date = _to_date(request.form.get("reading_date"))
    current_read = request.form.get("current_read_m3", type=float)

    customer = _allowed_customer(service_area_id, customer_id)
    if not customer or not reading_date or current_read is None:
        flash("Customer, Reading Date and Current reading are required.", "danger")
        return redirect(url_for("staff_meter_reading.list_readings", **request.args))

    if not meter_id:
        meter = Meter.query.filter(Meter.customer_id == customer_id).order_by(Meter.id.asc()).first()
        meter_id = meter.id if meter else None

    if not meter_id:
        flash("Please assign a meter to this customer first.", "danger")
        return redirect(url_for("staff_meter_reading.list_readings", **request.args))

    last_read, rate_per_m3, used_water_m3, amount_due = calculate_reading_values(
        customer_id,
        current_read,
        allow_rate_override=False,
    )

    rec = MeterReading(
        customer_id=customer_id,
        meter_id=meter_id,
        reading_date=reading_date,
        last_read_m3=last_read,
        current_read_m3=current_read,
        used_water_m3=used_water_m3,
        rate_per_m3=rate_per_m3,
        amount_due=amount_due,
    )

    db.session.add(rec)
    db.session.flush()
    sync_invoice_from_reading(rec, status="issued")
    db.session.commit()
    flash("Meter reading created and invoice generated.", "success")
    return redirect(url_for("staff_meter_reading.list_readings", **request.args))


@meter_reading_bp.route("/staff/meter-readings/<int:rec_id>/edit", methods=["POST"])
@login_required
@role_required("Staff")
def edit_reading(rec_id):
    service_area_id = current_staff_service_area_id()
    rec = MeterReading.query.get_or_404(rec_id)

    customer_id = request.form.get("customer_id", type=int)
    meter_id = request.form.get("meter_id", type=int)
    reading_date = _to_date(request.form.get("reading_date"))
    current_read = request.form.get("current_read_m3", type=float)

    customer = _allowed_customer(service_area_id, customer_id)
    if not customer or not reading_date or current_read is None:
        flash("Customer, Reading Date and Current reading are required.", "danger")
        return redirect(url_for("staff_meter_reading.list_readings", **request.args))

    if not meter_id:
        meter = Meter.query.filter(Meter.customer_id == customer_id).order_by(Meter.id.asc()).first()
        meter_id = meter.id if meter else None

    if not meter_id:
        flash("Please assign a meter to this customer first.", "danger")
        return redirect(url_for("staff_meter_reading.list_readings", **request.args))

    last_read, rate_per_m3, used_water_m3, amount_due = calculate_reading_values(
        customer_id,
        current_read,
        exclude_reading_id=rec.id,
        allow_rate_override=False,
    )

    rec.customer_id = customer_id
    rec.meter_id = meter_id
    rec.reading_date = reading_date
    rec.last_read_m3 = last_read
    rec.current_read_m3 = current_read
    rec.used_water_m3 = used_water_m3
    rec.rate_per_m3 = rate_per_m3
    rec.amount_due = amount_due

    sync_invoice_from_reading(rec, status="issued")
    db.session.commit()
    flash("Meter reading updated and invoice synchronized.", "success")
    return redirect(url_for("staff_meter_reading.list_readings", **request.args))
