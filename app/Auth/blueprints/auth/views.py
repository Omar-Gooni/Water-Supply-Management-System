from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from functools import wraps
from app.extensions import db
from .models import User

auth_bp = Blueprint("auth", __name__, template_folder="templates", static_folder="static")


def _normalize_role(value):
    return (value or "").strip().lower()


def _dashboard_for_role(role):
    role_key = _normalize_role(role)
    if role_key == "admin":
        return redirect(url_for("main.admin_dashboard"))
    if role_key == "staff":
        return redirect(url_for("staff_main.staff_profile"))
    if role_key == "customer":
        return redirect(url_for("auth.customer_dashboard"))
    return redirect(url_for("auth.login"))


# ---------- Guards (reuse these on your dashboards) ----------
def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        return fn(*args, **kwargs)
    return wrapper


def role_required(*roles):
    allowed_roles = {_normalize_role(role) for role in roles}

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("auth.login"))
            if _normalize_role(session.get("role")) not in allowed_roles:
                flash("Access denied.", "danger")
                return redirect(url_for("auth.login"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator
# -------------------------------------------------------------


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return _dashboard_for_role(session.get("role"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            flash("Login successful!", "success")
            return _dashboard_for_role(user.role)

        flash("Invalid username or password!", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/customer/dashboard")
@login_required
@role_required("Customer")
def customer_dashboard():
    return render_template("auth/customer_dashboard.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("auth.login"))
