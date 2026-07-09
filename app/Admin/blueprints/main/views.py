from sqlalchemy import func
from flask import Blueprint, render_template

from app.Auth.blueprints.auth.views import login_required, role_required
from app.Auth.blueprints.auth.models import User
from app.Admin.blueprints.customer.models import Customer
from app.Admin.blueprints.meter.models import Meter
from app.Admin.blueprints.meter_reading.models import MeterReading
from app.Admin.blueprints.invoice.models import Invoice
from app.Admin.blueprints.receipt.models import Receipt
from app.extensions import db
from app.Admin.blueprints.source.models import WaterSource
from app.Admin.blueprints.storage_tank.models import StorageTank
from app.Admin.blueprints.pipeline.models import Pipeline
from app.Admin.blueprints.service_area.models import ServiceArea
from app.Admin.blueprints.chemical.models import Chemical
from app.Admin.blueprints.treatment_record.models import TreatmentRecord

main_bp = Blueprint("main", __name__, template_folder="templates")


def _format_count(value):
    return f"{value:,}"


@main_bp.route("/admin/dashboard")
@login_required
@role_required("Admin")
def admin_dashboard():
    total_customers = Customer.query.count()
    active_customers = Customer.query.filter(Customer.status == "active").count()
    total_admins = User.query.filter(User.role == "Admin").count()
    total_staff = User.query.filter(User.role == "Staff").count()
    total_meters = Meter.query.count()
    active_meters = Meter.query.filter(Meter.status == "Active").count()
    total_invoices = Invoice.query.count()
    unpaid_invoices = Invoice.query.filter(Invoice.status.in_(("issued", "unpaid", "partial"))).count()
    total_revenue = db.session.query(func.coalesce(func.sum(Receipt.amount_paid), 0)).scalar()
    total_sources = WaterSource.query.count()
    total_tanks = StorageTank.query.count()
    total_pipelines = Pipeline.query.count()
    total_service_areas = ServiceArea.query.count()
    total_chemicals = Chemical.query.count()
    total_treatments = TreatmentRecord.query.count()
    total_readings = MeterReading.query.count()

    invoice_status_rows = (
        Invoice.query.with_entities(Invoice.status, func.count(Invoice.id))
        .group_by(Invoice.status)
        .all()
    )
    invoice_status_order = ["issued", "unpaid", "partial", "paid"]
    invoice_status_map = {
        status.lower(): count
        for status, count in invoice_status_rows
        if status
    }
    invoice_chart = {
        "labels": [status.title() for status in invoice_status_order if invoice_status_map.get(status)],
        "values": [invoice_status_map.get(status, 0) for status in invoice_status_order if invoice_status_map.get(status)],
    }

    stats = [
        {
            "label": "Total Customers",
            "value": _format_count(total_customers),
            "note": f"{active_customers} active customers",
            "icon": "fa-solid fa-users",
            "variant": "blue",
        },
        {
            "label": "Staff Members",
            "value": _format_count(total_staff),
            "note": f"{total_admins} admin account(s)",
            "icon": "fa-solid fa-user-gear",
            "variant": "cyan",
        },
        {
            "label": "Revenue",
            "value": f"{float(total_revenue or 0):,.2f}",
            "note": "Collected from receipts",
            "icon": "fa-solid fa-sack-dollar",
            "variant": "teal",
        },
        {
            "label": "Invoices",
            "value": _format_count(total_invoices),
            "note": f"{unpaid_invoices} need attention",
            "icon": "fa-solid fa-file-invoice-dollar",
            "variant": "amber",
        },
    ]

    return render_template(
        "main/index.html",
        stats=stats,
        invoice_chart=invoice_chart,
    )
