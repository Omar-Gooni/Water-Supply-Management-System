# app/Admin/blueprints/customer/views.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, make_response
from app.extensions import db
from datetime import datetime
import io, csv
from openpyxl import Workbook  # pip install openpyxl

from app.Auth.blueprints.auth.views import login_required, role_required
from app.Admin.blueprints.service_area.models import ServiceArea
from app.Admin.blueprints.pipeline.models import Pipeline  # supply lines
from .models import Customer

customer_bp = Blueprint("customer", __name__, template_folder="templates")


# ---------- helpers ----------
def _apply_filters(q):
    """Shared filters for list + export."""
    service_area_id = request.args.get("service_area_id", type=int)
    supply_line_id  = request.args.get("supply_line_id", type=int)
    customer_type   = request.args.get("customer_type")
    status          = request.args.get("status")
    q_text          = request.args.get("q")  # search in name/phone/connection id

    if service_area_id:
        q = q.filter(Customer.service_area_id == service_area_id)
    if supply_line_id:
        q = q.filter(Customer.supply_line_id == supply_line_id)
    if customer_type:
        q = q.filter(Customer.customer_type == customer_type)
    if status:
        q = q.filter(Customer.status == status)
    if q_text:
        like = f"%{q_text.strip()}%"
        q = q.filter(
            db.or_(
                Customer.customer_name.ilike(like),
                Customer.phone.ilike(like),
                Customer.customer_id.ilike(like),
            )
        )
    return q


# ---------- list (with pagination) ----------
@customer_bp.route("/admin/customers")
@login_required
@role_required("Admin")
def list_customers():
    # pagination
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    allowed_per_page = {10, 25, 50, 100}
    if per_page not in allowed_per_page:
        per_page = 25

    query = _apply_filters(Customer.query).order_by(Customer.id.desc())
    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False, max_per_page=100)
    items = pagination.items

    # dropdown data (you can further filter to active only if you want)
    service_areas = ServiceArea.query.order_by(ServiceArea.area_name.asc()).all()
    active_pipelines = Pipeline.query.filter_by(status="Active").order_by(Pipeline.line_name.asc()).all()

    return render_template(
        "customer/list.html",
        customers=items,
        pagination=pagination,
        per_page=per_page,
        allowed_per_page=sorted(allowed_per_page),
        service_areas=service_areas,
        pipelines=active_pipelines, 
    )


# ---------- create ----------
@customer_bp.route("/admin/customers/new", methods=["POST"])
@login_required
@role_required("Admin")
def create_customer():
    cust = Customer(
        service_area_id = request.form.get("service_area_id", type=int),
        supply_line_id  = request.form.get("supply_line_id", type=int),
        customer_name   = (request.form.get("customer_name") or "").strip(),
        customer_type   = (request.form.get("customer_type") or "").strip(),  # household / commercial / institution
        address         = (request.form.get("address") or "").strip(),
        phone           = (request.form.get("phone") or "").strip(),
        # customer_id auto (event), created_date auto (server_default)
        status          = (request.form.get("status") or "active").strip(),
    )

    if not cust.service_area_id or not cust.supply_line_id or not cust.customer_name or not cust.customer_type:
        flash("Service area, supply line, customer name and customer type are required.", "danger")
        return redirect(url_for("customer.list_customers", **request.args))

    db.session.add(cust)
    db.session.commit()
    flash("Customer created.", "success")
    return redirect(url_for("customer.list_customers", **request.args))


# ---------- edit ----------
@customer_bp.route("/admin/customers/<int:cust_id>/edit", methods=["POST"])
@login_required
@role_required("Admin")
def edit_customer(cust_id):
    cust = Customer.query.get_or_404(cust_id)

    cust.service_area_id = request.form.get("service_area_id", type=int)
    cust.supply_line_id  = request.form.get("supply_line_id", type=int)
    cust.customer_name   = (request.form.get("customer_name") or "").strip()
    cust.customer_type   = (request.form.get("customer_type") or "").strip()
    cust.address         = (request.form.get("address") or "").strip()
    cust.phone           = (request.form.get("phone") or "").strip()
    cust.status          = (request.form.get("status") or "active").strip()

    if not cust.service_area_id or not cust.supply_line_id or not cust.customer_name or not cust.customer_type:
        flash("Service area, supply line, customer name and customer type are required.", "danger")
        return redirect(url_for("customer.list_customers", **request.args))

    db.session.commit()
    flash("Customer updated.", "success")
    return redirect(url_for("customer.list_customers", **request.args))


# ---------- delete ----------
@customer_bp.route("/admin/customers/<int:cust_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def delete_customer(cust_id):
    cust = Customer.query.get_or_404(cust_id)
    db.session.delete(cust)
    db.session.commit()
    flash("Customer deleted.", "info")
    return redirect(url_for("customer.list_customers", **request.args))


# ---------- export CSV (respects filters) ----------
@customer_bp.route("/admin/customers/export.csv")
@login_required
@role_required("Admin")
def export_csv():
    rows = _apply_filters(Customer.query).order_by(Customer.id.asc()).all()

    headers = [
        "ID", "Customer ID", "Customer Name", "Customer Type",
        "Service Area", "Supply Line",
        "Address", "Phone",
        "Created Date", "Status",
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for c in rows:
        writer.writerow([
            c.id,
            c.customer_id,
            c.customer_name or "",
            c.customer_type or "",
            (c.service_area.area_name if c.service_area else c.service_area_id),
            (c.supply_line.line_name if c.supply_line else c.supply_line_id),
            c.address or "",
            c.phone or "",
            c.created_date.isoformat() if c.created_date else "",
            c.status or "",
        ])

    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    fname = f"customers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    resp.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp


# ---------- export Excel (respects filters) ----------
@customer_bp.route("/admin/customers/export.xlsx")
@login_required
@role_required("Admin")
def export_xlsx():
    rows = _apply_filters(Customer.query).order_by(Customer.id.asc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Customers"

    headers = [
        "ID", "Customer ID", "Customer Name", "Customer Type",
        "Service Area", "Supply Line",
        "Address", "Phone",
        "Created Date", "Status",
    ]
    ws.append(headers)

    for c in rows:
        ws.append([
            c.id,
            c.customer_id,
            c.customer_name or "",
            c.customer_type or "",
            (c.service_area.area_name if c.service_area else c.service_area_id),
            (c.supply_line.line_name if c.supply_line else c.supply_line_id),
            c.address or "",
            c.phone or "",
            c.created_date.isoformat() if c.created_date else None,
            c.status or "",
        ])

    # simple auto-widths
    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(12, max_len + 2), 40)

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f"customers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        bio,
        as_attachment=True,
        download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
