from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from functools import wraps
from app.extensions import db
from .models import User

auth_bp = Blueprint("auth", __name__, template_folder="templates", static_folder="static")

# ---------- Guards (reuse these on your dashboards) ----------
def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        return fn(*args, **kwargs)
    return wrapper

def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("auth.login"))
            if session.get("role") not in roles:
                flash("Access denied.", "danger")
                return redirect(url_for("auth.login"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator
# -------------------------------------------------------------

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        role = session.get("role")
        if role == "Admin":
            return redirect(url_for("main.admin_dashboard"))
        return redirect(url_for("user.dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        role = request.form.get("role") or "User"

        user = User.query.filter_by(username=username, role=role).first()

        if user and user.check_password(password):
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            flash("Login successful!", "success")

            # Redirect by role
            if role == "Admin":
                return redirect(url_for("main.admin_dashboard"))
            return redirect(url_for("user.dashboard"))

        flash("Invalid username, password, or role!", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("auth.login"))
