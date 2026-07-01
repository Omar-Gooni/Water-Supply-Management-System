from flask import Blueprint, render_template, redirect, url_for, abort

from app.Auth.blueprints.auth.views import login_required, role_required
from app.Staff.helpers import current_staff_user

staff_main_bp = Blueprint("staff_main", __name__, template_folder="templates")


@staff_main_bp.route("/staff/dashboard")
@login_required
@role_required("Staff")
def staff_dashboard():
    return redirect(url_for("staff_main.staff_profile"))


@staff_main_bp.route("/staff/profile")
@login_required
@role_required("Staff")
def staff_profile():
    staff_user = current_staff_user()
    if not staff_user:
        abort(404)
    return render_template(
        "staff/main/profile.html",
        staff_user=staff_user,
        service_area_name=staff_user.service_area.area_name if staff_user.service_area else None,
    )
