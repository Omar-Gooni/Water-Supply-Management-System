from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, make_response
from app.extensions import db
from .models import Chemical
from app.Auth.blueprints.auth.views import login_required, role_required
import csv, io
from datetime import datetime
from openpyxl import Workbook

chemical_bp = Blueprint("chemical", __name__, template_folder="templates")


# ---------- Helper Functions ----------
def _apply_filters(q):
    """Filter chemicals by name, status, or unit."""
    name = request.args.get("chemical_name")
    status = request.args.get("status")
    unit = request.args.get("unit")

    if name:
        q = q.filter(Chemical.chemical_name.ilike(f"%{name}%"))
    if status:
        q = q.filter(Chemical.status == status)
    if unit:
        q = q.filter(Chemical.unit == unit)

    return q


# ---------- List (with pagination) ----------
@chemical_bp.route("/admin/chemicals")
@login_required
@role_required("Admin")
def list_chemicals():
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    try:
        per_page = int(request.args.get("per_page", 25))
    except ValueError:
        per_page = 25

    allowed_per_page = {10, 25, 50, 100}
    if per_page not in allowed_per_page:
        per_page = 25

    query = _apply_filters(Chemical.query).order_by(Chemical.id.desc())
    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False, max_per_page=100)
    chemicals = pagination.items

    return render_template(
        "chemical/list.html",
        chemicals=chemicals,
        pagination=pagination,
        per_page=per_page,
        allowed_per_page=sorted(allowed_per_page),
    )


# ---------- Create ----------
@chemical_bp.route("/admin/chemicals/new", methods=["POST"])
@login_required
@role_required("Admin")
def create_chemical():
    chem = Chemical(
        chemical_name=request.form.get("chemical_name", "").strip(),
        unit=request.form.get("unit", "").strip(),
        default_dose_mgL=request.form.get("default_dose_mgL") or None,
        status=request.form.get("status") or "Active",
        remarks=request.form.get("remarks") or None,
    )
    db.session.add(chem)
    db.session.commit()
    flash("Chemical added successfully.", "success")
    return redirect(url_for("chemical.list_chemicals", **request.args))


# ---------- Edit ----------
@chemical_bp.route("/admin/chemicals/<int:chem_id>/edit", methods=["POST"])
@login_required
@role_required("Admin")
def edit_chemical(chem_id):
    chem = Chemical.query.get_or_404(chem_id)
    chem.chemical_name = request.form.get("chemical_name", "").strip()
    chem.unit = request.form.get("unit", "").strip()
    chem.default_dose_mgL = request.form.get("default_dose_mgL") or None
    chem.status = request.form.get("status") or "Active"
    chem.remarks = request.form.get("remarks") or None
    db.session.commit()
    flash("Chemical updated successfully.", "success")
    return redirect(url_for("chemical.list_chemicals", **request.args))


# ---------- Delete ----------
@chemical_bp.route("/admin/chemicals/<int:chem_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def delete_chemical(chem_id):
    chem = Chemical.query.get_or_404(chem_id)
    db.session.delete(chem)
    db.session.commit()
    flash("Chemical deleted.", "info")
    return redirect(url_for("chemical.list_chemicals", **request.args))


# ---------- Export CSV ----------
@chemical_bp.route("/admin/chemicals/export.csv")
@login_required
@role_required("Admin")
def export_csv():
    query = _apply_filters(Chemical.query).order_by(Chemical.id.asc())
    rows = query.all()

    headers = ["ID", "Chemical Name", "Unit", "Default Dose (mg/L)", "Status", "Remarks"]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for c in rows:
        writer.writerow([
            c.id,
            c.chemical_name or "",
            c.unit or "",
            c.default_dose_mgL if c.default_dose_mgL is not None else "",
            c.status or "",
            c.remarks or "",
        ])
    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    fname = f"chemicals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    resp.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp


# ---------- Export Excel ----------
@chemical_bp.route("/admin/chemicals/export.xlsx")
@login_required
@role_required("Admin")
def export_xlsx():
    query = _apply_filters(Chemical.query).order_by(Chemical.id.asc())
    rows = query.all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Chemicals"

    headers = ["ID", "Chemical Name", "Unit", "Default Dose (mg/L)", "Status", "Remarks"]
    ws.append(headers)

    for c in rows:
        ws.append([
            c.id,
            c.chemical_name or "",
            c.unit or "",
            float(c.default_dose_mgL) if c.default_dose_mgL is not None else None,
            c.status or "",
            c.remarks or "",
        ])

    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(12, max_len + 2), 40)

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f"chemicals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        bio,
        as_attachment=True,
        download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
