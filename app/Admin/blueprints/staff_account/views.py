from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import or_

from app.extensions import db
from app.Auth.blueprints.auth.views import login_required, role_required
from app.Auth.blueprints.auth.models import User
from app.Admin.blueprints.service_area.models import ServiceArea

staff_account_bp = Blueprint("staff_account", __name__, template_folder="templates")


def _apply_filters(q):
    q_text = (request.args.get("q") or "").strip()
    service_area_id = request.args.get("service_area_id", type=int)

    if q_text:
        like = f"%{q_text}%"
        q = q.filter(
            or_(
                User.username.ilike(like),
                User.full_name.ilike(like),
                User.job_title.ilike(like),
                User.phone.ilike(like),
            )
        )

    if service_area_id:
        q = q.filter(User.service_area_id == service_area_id)

    return q.filter(User.role == "Staff")


def _get_form_values():
    return {
        "full_name": (request.form.get("full_name") or "").strip(),
        "username": (request.form.get("username") or "").strip(),
        "job_title": (request.form.get("job_title") or "").strip(),
        "phone": (request.form.get("phone") or "").strip(),
        "service_area_id": request.form.get("service_area_id", type=int),
        "password": request.form.get("password") or "",
        "confirm_password": request.form.get("confirm_password") or "",
    }


@staff_account_bp.route("/admin/staff")
@login_required
@role_required("Admin")
def list_staff():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    allowed_per_page = {10, 25, 50, 100}
    if per_page not in allowed_per_page:
        per_page = 25

    query = _apply_filters(User.query).order_by(User.id.desc())
    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False, max_per_page=100)
    service_areas = ServiceArea.query.order_by(ServiceArea.area_name.asc()).all()

    return render_template(
        "staff_account/list.html",
        staff_users=pagination.items,
        pagination=pagination,
        per_page=per_page,
        allowed_per_page=sorted(allowed_per_page),
        service_areas=service_areas,
    )


@staff_account_bp.route("/admin/staff/new", methods=["POST"])
@login_required
@role_required("Admin")
def create_staff():
    form = _get_form_values()

    if not form["full_name"] or not form["username"] or not form["job_title"] or not form["phone"] or not form["service_area_id"] or not form["password"]:
        flash("Full name, username, job title, service area, phone, and password are required.", "danger")
        return redirect(url_for("staff_account.list_staff", **request.args))
    if form["password"] != form["confirm_password"]:
        flash("Passwords do not match.", "danger")
        return redirect(url_for("staff_account.list_staff", **request.args))

    service_area = ServiceArea.query.get(form["service_area_id"])
    if service_area is None:
        flash("Please choose a valid service area.", "danger")
        return redirect(url_for("staff_account.list_staff", **request.args))

    existing = User.query.filter_by(username=form["username"]).first()
    if existing:
        flash("Username already exists.", "danger")
        return redirect(url_for("staff_account.list_staff", **request.args))

    user = User(
        full_name=form["full_name"],
        username=form["username"],
        job_title=form["job_title"],
        phone=form["phone"],
        service_area_id=form["service_area_id"],
        role="Staff",
    )
    user.set_password(form["password"])
    db.session.add(user)
    db.session.commit()

    flash("Staff user created.", "success")
    return redirect(url_for("staff_account.list_staff", **request.args))


@staff_account_bp.route("/admin/staff/<int:user_id>/edit", methods=["POST"])
@login_required
@role_required("Admin")
def edit_staff(user_id):
    user = User.query.filter_by(id=user_id, role="Staff").first_or_404()
    form = _get_form_values()

    if not form["full_name"] or not form["username"] or not form["job_title"] or not form["phone"] or not form["service_area_id"]:
        flash("Full name, username, job title, service area, and phone are required.", "danger")
        return redirect(url_for("staff_account.list_staff", **request.args))
    if form["password"] and form["password"] != form["confirm_password"]:
        flash("Passwords do not match.", "danger")
        return redirect(url_for("staff_account.list_staff", **request.args))

    service_area = ServiceArea.query.get(form["service_area_id"])
    if service_area is None:
        flash("Please choose a valid service area.", "danger")
        return redirect(url_for("staff_account.list_staff", **request.args))

    duplicate = User.query.filter(User.username == form["username"], User.id != user.id).first()
    if duplicate:
        flash("Username already exists.", "danger")
        return redirect(url_for("staff_account.list_staff", **request.args))

    user.full_name = form["full_name"]
    user.username = form["username"]
    user.job_title = form["job_title"]
    user.phone = form["phone"]
    user.service_area_id = form["service_area_id"]
    if form["password"]:
        user.set_password(form["password"])

    db.session.commit()

    flash("Staff user updated.", "success")
    return redirect(url_for("staff_account.list_staff", **request.args))


@staff_account_bp.route("/admin/staff/<int:user_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def delete_staff(user_id):
    user = User.query.filter_by(id=user_id, role="Staff").first_or_404()
    db.session.delete(user)
    db.session.commit()
    flash("Staff user deleted.", "info")
    return redirect(url_for("staff_account.list_staff", **request.args))
