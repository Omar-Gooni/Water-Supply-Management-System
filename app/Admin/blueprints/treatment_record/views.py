# app/Admin/blueprints/treatment_record/views.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, make_response
from app.extensions import db
from datetime import datetime
from sqlalchemy import and_
from app.Auth.blueprints.auth.views import login_required, role_required

from app.Admin.blueprints.source.models import WaterSource
from app.Admin.blueprints.chemical.models import Chemical
from .models import TreatmentRecord

# --- NEW for exports ---
import csv, io
from openpyxl import Workbook  # pip install openpyxl

treatment_record_bp = Blueprint("treatment_record", __name__, template_folder="templates")

# -------------- helpers --------------
def _to_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None

def _apply_filters(q):
    source_id   = request.args.get("source_id", type=int)
    chemical_id = request.args.get("chemical_id", type=int)
    date_from   = request.args.get("date_from")
    date_to     = request.args.get("date_to")

    if source_id:
        q = q.filter(TreatmentRecord.source_id == source_id)
    if chemical_id:
        q = q.filter(TreatmentRecord.chemical_id == chemical_id)
    if date_from:
        d1 = _to_date(date_from)
        if d1:
            q = q.filter(TreatmentRecord.treatment_date >= d1)
    if date_to:
        d2 = _to_date(date_to)
        if d2:
            q = q.filter(TreatmentRecord.treatment_date <= d2)
    return q

# -------------- list (with pagination) --------------
@treatment_record_bp.route("/admin/treatment-records")
@login_required
@role_required("Admin")
def list_records():
    # pagination
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    if per_page not in {10, 25, 50, 100}:
        per_page = 25

    query = _apply_filters(TreatmentRecord.query).order_by(TreatmentRecord.id.desc())
    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False, max_per_page=100)
    items = pagination.items

    # dropdowns (ACTIVE ONLY)
    active_sources   = WaterSource.query.filter(WaterSource.status == "Active").order_by(WaterSource.source_name.asc()).all()
    active_chemicals = Chemical.query.filter(Chemical.status == "Active").order_by(Chemical.chemical_name.asc()).all()

    return render_template(
        "treatment_record/list.html",
        records=items,
        pagination=pagination,
        per_page=per_page,
        allowed_per_page=[10, 25, 50, 100],
        active_sources=active_sources,
        active_chemicals=active_chemicals,
    )

# -------------- create --------------
@treatment_record_bp.route("/admin/treatment-records/new", methods=["POST"])
@login_required
@role_required("Admin")
def create_record():
    rec = TreatmentRecord(
        source_id        = request.form.get("source_id", type=int),
        chemical_id      = request.form.get("chemical_id", type=int),
        treatment_date   = _to_date(request.form.get("treatment_date")) or datetime.now().date(),
        treated_water_m3 = request.form.get("treated_water_m3") or None,
        amount_used      = request.form.get("amount_used") or None,
        unit             = request.form.get("unit", "").strip(),  # required
        quality_status   = request.form.get("quality_status") or None,
        operator_name    = request.form.get("operator_name") or None,
        remarks          = request.form.get("remarks") or None,
    )
    if not rec.source_id or not rec.chemical_id or not rec.treatment_date or not rec.unit:
        flash("Source, Chemical, Treatment Date and Unit are required.", "danger")
        return redirect(url_for("treatment_record.list_records", **request.args))

    db.session.add(rec)
    db.session.commit()
    flash("Treatment record created.", "success")
    return redirect(url_for("treatment_record.list_records", **request.args))

# -------------- edit --------------
@treatment_record_bp.route("/admin/treatment-records/<int:rec_id>/edit", methods=["POST"])
@login_required
@role_required("Admin")
def edit_record(rec_id):
    rec = TreatmentRecord.query.get_or_404(rec_id)

    rec.source_id        = request.form.get("source_id", type=int)
    rec.chemical_id      = request.form.get("chemical_id", type=int)
    rec.treatment_date   = _to_date(request.form.get("treatment_date"))
    rec.treated_water_m3 = request.form.get("treated_water_m3") or None
    rec.amount_used      = request.form.get("amount_used") or None
    rec.unit             = request.form.get("unit", "").strip()
    rec.quality_status   = request.form.get("quality_status") or None
    rec.operator_name    = request.form.get("operator_name") or None
    rec.remarks          = request.form.get("remarks") or None

    if not rec.source_id or not rec.chemical_id or not rec.treatment_date or not rec.unit:
        flash("Source, Chemical, Treatment Date and Unit are required.", "danger")
        return redirect(url_for("treatment_record.list_records", **request.args))

    db.session.commit()
    flash("Treatment record updated.", "success")
    return redirect(url_for("treatment_record.list_records", **request.args))

# -------------- delete --------------
@treatment_record_bp.route("/admin/treatment-records/<int:rec_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def delete_record(rec_id):
    rec = TreatmentRecord.query.get_or_404(rec_id)
    db.session.delete(rec)
    db.session.commit()
    flash("Treatment record deleted.", "info")
    return redirect(url_for("treatment_record.list_records", **request.args))

# -------------- EXPORTS (CSV / XLSX) --------------
@treatment_record_bp.route("/admin/treatment-records/export.csv")
@login_required
@role_required("Admin")
def export_csv():
    query = _apply_filters(TreatmentRecord.query).order_by(TreatmentRecord.id.asc())
    rows = query.all()

    headers = [
        "ID", "Treatment Date", "Source", "Chemical",
        "Treated water (m3)",
        "Amount used", "Unit",
        "Quality status", "Operator", "Remarks"
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)

    for r in rows:
        writer.writerow([
            r.id,
            r.treatment_date.isoformat() if r.treatment_date else "",
            (r.source.source_name if r.source else r.source_id) or "",
            (r.chemical.chemical_name if r.chemical else r.chemical_id) or "",
            f"{r.treated_water_m3:.2f}" if r.treated_water_m3 is not None else "",
            f"{r.amount_used:.3f}" if r.amount_used is not None else "",
            r.unit or "",
            r.quality_status or "",
            r.operator_name or "",
            r.remarks or "",
        ])

    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    fname = f"treatment_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    resp.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp

@treatment_record_bp.route("/admin/treatment-records/export.xlsx")
@login_required
@role_required("Admin")
def export_xlsx():
    query = _apply_filters(TreatmentRecord.query).order_by(TreatmentRecord.id.asc())
    rows = query.all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Treatment Records"

    headers = [
        "ID", "Treatment Date", "Source", "Chemical",
        "Treated water (m3)",
        "Amount used", "Unit",
        "Quality status", "Operator", "Remarks"
    ]
    ws.append(headers)

    for r in rows:
        ws.append([
            r.id,
            r.treatment_date.isoformat() if r.treatment_date else None,
            (r.source.source_name if r.source else r.source_id) or None,
            (r.chemical.chemical_name if r.chemical else r.chemical_id) or None,
            float(r.treated_water_m3) if r.treated_water_m3 is not None else None,
            float(r.amount_used) if r.amount_used is not None else None,
            r.unit or None,
            r.quality_status or None,
            r.operator_name or None,
            r.remarks or None,
        ])

    # simple auto-width
    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(12, max_len + 2), 40)

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f"treatment_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        bio,
        as_attachment=True,
        download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
