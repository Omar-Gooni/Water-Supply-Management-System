from flask import Blueprint, render_template
from app.Auth.blueprints.auth.views import login_required, role_required

main_bp = Blueprint("main", __name__, template_folder="templates")
@main_bp.route("/admin/dashboard")
@login_required
@role_required("Admin")
def admin_dashboard():
    return render_template("main/index.html")
