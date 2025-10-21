# app/Admin/blueprints/service_area/views.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, make_response
from app.extensions import db
from datetime import datetime
import io, csv
from openpyxl import Workbook  # pip install openpyxl

from app.Auth.blueprints.auth.views import login_required, role_required
from .models import ServiceArea

service_area_bp = Blueprint("service_area", __name__, template_folder="templates")

# ---------- helpers ----------
def _apply_filters(q):
    """Shared filters for list + exports."""
    area_code = request.args.get("area_code")
    area_name = request.args.get("area_name")

    if area_code:
        q = q.filter(ServiceArea.area_code.ilike(f"%{area_code}%"))
    if area_name:
        q = q.filter(ServiceArea.area_name.ilike(f"%{area_name}%"))

    return q


# ---------- list (with pagination) ----------
@service_area_bp.route("/admin/service-areas")
@login_required
@role_required("Admin")
def list_areas():
    # Safe pagination
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    allowed_per_page = {10, 25, 50, 100}
    if per_page not in allowed_per_page:
        per_page = 25

    query = _apply_filters(ServiceArea.query).order_by(ServiceArea.id.desc())

    pagination = db.paginate(
        query,
        page=page,
        per_page=per_page,
        error_out=False,
        max_per_page=100,
    )
    items = pagination.items

    return render_template(
        "service_area/list.html",
        areas=items,
        pagination=pagination,
        per_page=per_page,
        allowed_per_page=sorted(allowed_per_page),
    )


# ---------- create ----------
@service_area_bp.route("/admin/service-areas/new", methods=["POST"])
@login_required
@role_required("Admin")
def create_area():
    area = ServiceArea(
        # area_code is auto-generated in models.py (before_insert event)
        area_name=(request.form.get("area_name") or "").strip(),
        remarks=(request.form.get("remarks") or None),
    )

    if not area.area_name:
        flash("Area Name is required.", "danger")
        return redirect(url_for("service_area.list_areas", **request.args))

    db.session.add(area)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        # likely uniqueness on area_code (rare) or other DB error
        flash("Could not create area. Please try again.", "danger")
        return redirect(url_for("service_area.list_areas", **request.args))

    flash("Service area created.", "success")
    return redirect(url_for("service_area.list_areas", **request.args))


# ---------- edit ----------
@service_area_bp.route("/admin/service-areas/<int:area_id>/edit", methods=["POST"])
@login_required
@role_required("Admin")
def edit_area(area_id):
    area = ServiceArea.query.get_or_404(area_id)

    area.area_name = (request.form.get("area_name") or "").strip()
    area.remarks = (request.form.get("remarks") or None)

    if not area.area_name:
        flash("Area Name is required.", "danger")
        return redirect(url_for("service_area.list_areas", **request.args))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not update area. Please try again.", "danger")
        return redirect(url_for("service_area.list_areas", **request.args))

    flash("Service area updated.", "success")
    return redirect(url_for("service_area.list_areas", **request.args))


# ---------- delete ----------
@service_area_bp.route("/admin/service-areas/<int:area_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def delete_area(area_id):
    area = ServiceArea.query.get_or_404(area_id)
    db.session.delete(area)
    db.session.commit()
    flash("Service area deleted.", "info")
    return redirect(url_for("service_area.list_areas", **request.args))


# ---------- exports (respect filters) ----------
@service_area_bp.route("/admin/service-areas/export.csv")
@login_required
@role_required("Admin")
def export_csv():
    rows = _apply_filters(ServiceArea.query).order_by(ServiceArea.id.asc()).all()

    headers = ["ID", "Area Code", "Area Name", "Remarks"]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for a in rows:
        writer.writerow([
            a.id,
            a.area_code or "",
            a.area_name or "",
            a.remarks or "",
        ])

    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    fname = f"service_areas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    resp.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp


@service_area_bp.route("/admin/service-areas/export.xlsx")
@login_required
@role_required("Admin")
def export_xlsx():
    rows = _apply_filters(ServiceArea.query).order_by(ServiceArea.id.asc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Service Areas"

    headers = ["ID", "Area Code", "Area Name", "Remarks"]
    ws.append(headers)

    for a in rows:
        ws.append([
            a.id,
            a.area_code or "",
            a.area_name or "",
            a.remarks or "",
        ])

    # simple auto-widths
    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(12, max_len + 2), 40)

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f"service_areas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        bio,
        as_attachment=True,
        download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
