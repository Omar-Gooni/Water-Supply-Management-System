from flask import Blueprint, render_template, request, flash
from sqlalchemy import or_

from app.extensions import db
from app.Auth.blueprints.auth.views import login_required, role_required
from app.Admin.blueprints.customer.models import Customer
from app.Staff.helpers import current_staff_service_area_id, current_staff_user

customer_bp = Blueprint("staff_customer", __name__, template_folder="templates")


@customer_bp.route("/staff/customers")
@login_required
@role_required("Staff")
def list_customers():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    allowed_per_page = {10, 25, 50, 100}
    if per_page not in allowed_per_page:
        per_page = 25

    staff_user = current_staff_user()
    service_area_id = current_staff_service_area_id()
    q_text = (request.args.get("q") or "").strip()

    query = Customer.query
    if service_area_id:
        query = query.filter(Customer.service_area_id == service_area_id)
    else:
        query = query.filter(False)
        flash("Your account is not assigned to a service area yet.", "warning")

    if q_text:
        like = f"%{q_text}%"
        query = query.filter(
            or_(
                Customer.customer_name.ilike(like),
                Customer.phone.ilike(like),
                Customer.customer_id.ilike(like),
            )
        )

    query = query.order_by(Customer.id.desc())
    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False, max_per_page=100)

    service_area_name = staff_user.service_area.area_name if staff_user and staff_user.service_area else None

    return render_template(
        "customer/list.html",
        customers=pagination.items,
        pagination=pagination,
        per_page=per_page,
        allowed_per_page=sorted(allowed_per_page),
        q_text=q_text,
        staff_user=staff_user,
        service_area_name=service_area_name,
    )
