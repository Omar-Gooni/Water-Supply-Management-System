from flask import Blueprint, redirect, url_for
from app.Auth.blueprints.auth.views import login_required, role_required

counter_main_bp = Blueprint("counter_main", __name__, template_folder="templates")

@counter_main_bp.route("/")
@login_required
@role_required("Counter")
def dashboard():
    return redirect(url_for("receipt.list_receipts"))
