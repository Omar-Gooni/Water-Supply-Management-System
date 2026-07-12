# app/Admin/blueprints/pipeline/views.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, make_response
from app.extensions import db
from datetime import datetime
import io, csv
from openpyxl import Workbook  # pip install openpyxl

from app.Auth.blueprints.auth.views import login_required, role_required
from app.Admin.blueprints.storage_tank.models import StorageTank
from app.Admin.blueprints.service_area.models import ServiceArea
from .models import Pipeline

pipeline_bp = Blueprint("pipeline", __name__, template_folder="templates")

# ---------- helpers ----------
def _to_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None

def _apply_filters(q):
    """Reuse the same filtering logic for list + exports."""
    tank_id        = request.args.get("tank_id", type=int)
    area_id        = request.args.get("service_area_id", type=int)
    status         = request.args.get("status")
    line_name      = request.args.get("line_name")
    date_from      = request.args.get("date_from")
    date_to        = request.args.get("date_to")

    if tank_id:
        q = q.filter(Pipeline.tank_id == tank_id)
    if area_id:
        q = q.filter(Pipeline.service_area_id == area_id)
    if status:
        q = q.filter(Pipeline.status == status)
    if line_name:
        q = q.filter(Pipeline.line_name.ilike(f"%{line_name}%"))
    if date_from:
        d1 = _to_date(date_from)
        if d1:
            q = q.filter(Pipeline.last_supply_date >= d1)
    if date_to:
        d2 = _to_date(date_to)
        if d2:
            q = q.filter(Pipeline.last_supply_date <= d2)

    return q

# ---------- list (with pagination) ----------
@pipeline_bp.route("/admin/pipelines")
@login_required
@role_required("Admin")
def list_pipelines():
    # page & per_page (defensive)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    allowed_per_page = {10, 25, 50, 100}
    if per_page not in allowed_per_page:
        per_page = 25

    # base query + filters + order
    query = _apply_filters(Pipeline.query).order_by(Pipeline.id.desc())

    pagination = db.paginate(
        query,
        page=page,
        per_page=per_page,
        error_out=False,
        max_per_page=100,
    )
    items = pagination.items

    # dropdowns: only active tanks/areas shown for selection UX
    active_tanks = StorageTank.query.filter(StorageTank.status == "Active") \
                        .order_by(StorageTank.tank_name.asc()).all()
    service_areas = ServiceArea.query.order_by(ServiceArea.area_name.asc()).all()

    return render_template(
        "pipeline/list.html",
        pipelines=items,
        pagination=pagination,
        per_page=per_page,
        allowed_per_page=sorted(allowed_per_page),

        active_tanks=active_tanks,
        service_areas=service_areas,

        # for status filter select
        status_options=["Active", "Leak", "Maintenance", "Inactive"],
    )

# ---------- create ----------
@pipeline_bp.route("/admin/pipelines/new", methods=["POST"])
@login_required
@role_required("Admin")
def create_pipeline():
    pl = Pipeline(
        tank_id          = request.form.get("tank_id", type=int),
        service_area_id  = request.form.get("service_area_id", type=int),
        line_name        = (request.form.get("line_name") or "").strip(),
        pipe_diameter_mm = request.form.get("pipe_diameter_mm") or None,
        status           = (request.form.get("status") or "Active").strip(),
        last_supply_date = _to_date(request.form.get("last_supply_date")),
        remarks          = request.form.get("remarks") or None,
    )

    if not pl.tank_id or not pl.service_area_id or not pl.line_name or not pl.pipe_diameter_mm :
        flash("Tank, Service Area, Line Name and Pipe Diameter are required.", "danger")
        return redirect(url_for("pipeline.list_pipelines", **request.args))

    db.session.add(pl)
    db.session.commit()
    flash("Pipeline created.", "success")
    return redirect(url_for("pipeline.list_pipelines", **request.args))

# ---------- edit ----------
@pipeline_bp.route("/admin/pipelines/<int:pipeline_id>/edit", methods=["POST"])
@login_required
@role_required("Admin")
def edit_pipeline(pipeline_id):
    pl = Pipeline.query.get_or_404(pipeline_id)

    pl.tank_id          = request.form.get("tank_id", type=int)
    pl.service_area_id  = request.form.get("service_area_id", type=int)
    pl.line_name        = (request.form.get("line_name") or "").strip()
    pl.pipe_diameter_mm = request.form.get("pipe_diameter_mm") or None
    pl.status           = (request.form.get("status") or "Active").strip()
    pl.last_supply_date = _to_date(request.form.get("last_supply_date"))
    pl.remarks          = request.form.get("remarks") or None

    if not pl.tank_id or not pl.service_area_id or not pl.line_name or not pl.pipe_diameter_mm :
        flash("Tank, Service Area, Line Name and Pipe Diameter are required.", "danger")
        return redirect(url_for("pipeline.list_pipelines", **request.args))

    db.session.commit()
    flash("Pipeline updated.", "success")
    return redirect(url_for("pipeline.list_pipelines", **request.args))

# ---------- delete ----------
@pipeline_bp.route("/admin/pipelines/<int:pipeline_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def delete_pipeline(pipeline_id):
    pl = Pipeline.query.get_or_404(pipeline_id)
    db.session.delete(pl)
    db.session.commit()
    flash("Pipeline deleted.", "info")
    return redirect(url_for("pipeline.list_pipelines", **request.args))

# ---------- exports (respect filters) ----------
@pipeline_bp.route("/admin/pipelines/export.csv")
@login_required
@role_required("Admin")
def export_csv():
    query = _apply_filters(Pipeline.query).order_by(Pipeline.id.asc())
    rows = query.all()

    headers = [
        "ID", "Tank", "Service Area", "Line Name", "Diameter (mm)",
        "Status", "Last Supply Date", "Remarks"
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for p in rows:
        writer.writerow([
            p.id,
            (p.tank.tank_name if p.tank else p.tank_id),
            (p.service_area.area_name if p.service_area else p.service_area_id),
            p.line_name or "",
            f"{p.pipe_diameter_mm:.2f}" if p.pipe_diameter_mm is not None else "",
            p.status or "",
            p.last_supply_date.isoformat() if p.last_supply_date else "",
            p.remarks or "",
        ])

    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    fname = f"pipelines_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    resp.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp

@pipeline_bp.route("/admin/pipelines/export.xlsx")
@login_required
@role_required("Admin")
def export_xlsx():
    query = _apply_filters(Pipeline.query).order_by(Pipeline.id.asc())
    rows = query.all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Pipelines"

    headers = [
        "ID", "Tank", "Service Area", "Line Name", "Diameter (mm)",
        "Status", "Last Supply Date", "Remarks"
    ]
    ws.append(headers)

    for p in rows:
        ws.append([
            p.id,
            (p.tank.tank_name if p.tank else p.tank_id),
            (p.service_area.area_name if p.service_area else p.service_area_id),
            p.line_name or "",
            float(p.pipe_diameter_mm) if p.pipe_diameter_mm is not None else None,
            p.status or "",
            p.last_supply_date.isoformat() if p.last_supply_date else None,
            p.remarks or "",
        ])

    # simple auto-widths
    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(12, max_len + 2), 40)

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f"pipelines_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        bio,
        as_attachment=True,
        download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )



