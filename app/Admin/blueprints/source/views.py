# app/Admin/blueprints/source/views.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, make_response
from app.extensions import db
from .models import WaterSource
from app.Auth.blueprints.auth.views import login_required, role_required
import csv, io
from datetime import datetime
from openpyxl import Workbook  # pip install openpyxl

source_bp = Blueprint("source", __name__, template_folder="templates")


# ---------- helpers ----------
def _to_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _apply_filters(q):
    """Re-use the same filters for list + exports."""
    source_type = request.args.get("source_type")
    status = request.args.get("status")
    location = request.args.get("location")

    if source_type:
        q = q.filter(WaterSource.source_type == source_type)
    if status:
        q = q.filter(WaterSource.status == status)
    if location:
        q = q.filter(WaterSource.location.ilike(f"%{location}%"))

    return q


# ---------- list (with pagination) ----------
@source_bp.route("/admin/sources")
@login_required
@role_required("Admin")
def list_sources():
    # read page/per_page safely
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    try:
        per_page = int(request.args.get("per_page", 25))
    except ValueError:
        per_page = 25

    # only allow a few sizes to protect DB
    allowed_per_page = {10, 25, 50, 100}
    if per_page not in allowed_per_page:
        per_page = 25

    # apply filters + order
    query = _apply_filters(WaterSource.query).order_by(WaterSource.id.desc())

    # efficient server-side pagination
    pagination = db.paginate(
        query,
        page=page,
        per_page=per_page,
        error_out=False,
        max_per_page=100,
    )
    sources = pagination.items

    return render_template(
        "source/list.html",
        sources=sources,
        pagination=pagination,
        per_page=per_page,
        allowed_per_page=sorted(allowed_per_page),
    )


# ---------- create / edit / delete ----------
@source_bp.route("/admin/sources/new", methods=["POST"])
@login_required
@role_required("Admin")
def create_source():
    source = WaterSource(
        source_name=request.form.get("source_name", "").strip(),
        source_type=request.form.get("source_type", "").strip(),
        location=request.form.get("location", "").strip(),
        capacity_m3_day=request.form.get("capacity_m3_day") or None,
        status=request.form.get("status") or "Active",
        remarks=request.form.get("remarks") or None,
    )
    db.session.add(source)
    db.session.commit()
    flash("Source created.", "success")
    # keep current filters/pagination on redirect
    return redirect(url_for("source.list_sources", **request.args))


@source_bp.route("/admin/sources/<int:source_id>/edit", methods=["POST"])
@login_required
@role_required("Admin")
def edit_source(source_id):
    source = WaterSource.query.get_or_404(source_id)
    source.source_name = request.form.get("source_name", "").strip()
    source.source_type = request.form.get("source_type", "").strip()
    source.location = request.form.get("location", "").strip()
    source.capacity_m3_day = request.form.get("capacity_m3_day") or None
    source.status = request.form.get("status") or "Active"
    source.remarks = request.form.get("remarks") or None
    db.session.commit()
    flash("Source updated.", "success")
    return redirect(url_for("source.list_sources", **request.args))


@source_bp.route("/admin/sources/<int:source_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def delete_source(source_id):
    src = WaterSource.query.get_or_404(source_id)
    db.session.delete(src)
    db.session.commit()
    flash("Source deleted.", "info")
    return redirect(url_for("source.list_sources", **request.args))


# ---------- exports (respect filters) ----------
@source_bp.route("/admin/sources/export.csv")
@login_required
@role_required("Admin")
def export_csv():
    query = _apply_filters(WaterSource.query).order_by(WaterSource.id.asc())
    rows = query.all()

    headers = [
        "ID", "Source Name", "Source Type", "Location",
        "Capacity (m3/day)", "Status", "Last Production Date", "Last Volume (m3)", "Remarks"
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for s in rows:
        writer.writerow([
            s.id,
            s.source_name or "",
            s.source_type or "",
            s.location or "",
            f"{s.capacity_m3_day:.2f}" if s.capacity_m3_day is not None else "",
            s.status or "",
            s.remarks or "",
        ])
    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    fname = f"water_sources_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    resp.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp


@source_bp.route("/admin/sources/export.xlsx")
@login_required
@role_required("Admin")
def export_xlsx():
    query = _apply_filters(WaterSource.query).order_by(WaterSource.id.asc())
    rows = query.all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Sources"

    headers = [
        "ID", "Source Name", "Source Type", "Location",
        "Capacity (mÂ³/day)", "Status", "Last Production Date", "Last Volume (mÂ³)", "Remarks"
    ]
    ws.append(headers)

    for s in rows:
        ws.append([
            s.id,
            s.source_name or "",
            s.source_type or "",
            s.location or "",
            float(s.capacity_m3_day) if s.capacity_m3_day is not None else None,
            s.status or "",
            s.remarks or "",
        ])

    # simple auto-width
    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(12, max_len + 2), 40)

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f"water_sources_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        bio,
        as_attachment=True,
        download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


