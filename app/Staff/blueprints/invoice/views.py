from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.extensions import db
from datetime import date

from app.Auth.blueprints.auth.views import login_required, role_required
from app.Admin.blueprints.customer.models import Customer
from app.Admin.blueprints.invoice.models import Invoice
from app.Staff.helpers import current_staff_service_area_id, current_staff_user

staff_invoice_bp = Blueprint("staff_invoice", __name__, template_folder="templates")


def _today() -> date:
    return date.today()


def _apply_filters(q, service_area_id):
    customer_id = request.args.get("customer_id", type=int)
    status = request.args.get("status", type=str)
    invoice_no = request.args.get("invoice_no", type=str)

    if service_area_id:
        q = q.join(Customer, Customer.id == Invoice.customer_id).filter(Customer.service_area_id == service_area_id)
    else:
        q = q.filter(False)

    if customer_id:
        q = q.filter(Invoice.customer_id == customer_id)
    if status:
        q = q.filter(Invoice.status == status)
    if invoice_no:
        like = f"%{invoice_no.strip()}%"
        q = q.filter(Invoice.invoice_no.ilike(like))
    return q


@staff_invoice_bp.route("/staff/invoices")
@login_required
@role_required("Staff")
def list_invoices():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    if per_page not in {10, 25, 50, 100}:
        per_page = 25

    staff_user = current_staff_user()
    service_area_id = current_staff_service_area_id()

    query = _apply_filters(Invoice.query, service_area_id).order_by(Invoice.id.desc())
    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False, max_per_page=100)

    active_customers = []
    if service_area_id:
        active_customers = (
            Customer.query
            .filter(Customer.status == "active", Customer.service_area_id == service_area_id)
            .order_by(Customer.customer_name.asc())
            .all()
        )

    return render_template(
        "invoice/list.html",
        invoices=pagination.items,
        pagination=pagination,
        per_page=per_page,
        allowed_per_page=[10, 25, 50, 100],
        customers=active_customers,
        staff_user=staff_user,
        service_area_name=staff_user.service_area.area_name if staff_user and staff_user.service_area else None,
    )


@staff_invoice_bp.route("/staff/invoices/new", methods=["POST"])
@login_required
@role_required("Staff")
def create_invoice():
    flash("Invoices are generated automatically from meter readings.", "info")
    return redirect(url_for("staff_invoice.list_invoices", **request.args))


@staff_invoice_bp.route("/staff/invoices/<int:invoice_id>/print")
@login_required
@role_required("Staff")
def print_invoice(invoice_id):
    inv = Invoice.query.get_or_404(invoice_id)
    cust = inv.customer
    reading = inv.reading
    meter = reading.meter if (reading and hasattr(reading, "meter")) else None

    return render_template(
        "invoice/invoice_print.html",
        inv=inv,
        cust=cust,
        reading=reading,
        meter=meter,
        today=_today(),
    )
