# app/Admin/blueprints/storage_tank/views.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, make_response
from app.extensions import db
from datetime import datetime
import io, csv
from openpyxl import Workbook  # pip install openpyxl

from app.Auth.blueprints.auth.views import login_required, role_required
from app.Admin.blueprints.source.models import WaterSource
from app.Admin.blueprints.treatment_record.models import TreatmentRecord  # <-- NEW
from .models import StorageTank

storage_tank_bp = Blueprint("storage_tank", __name__, template_folder="templates")

# ---------- helpers ----------
def _to_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None

def _apply_filters(q):
    """Reuse filters for list + exports."""
    source_id  = request.args.get("source_id", type=int)
    status     = request.args.get("status")
    tank_name  = request.args.get("tank_name")

    if source_id:
        q = q.filter(StorageTank.source_id == source_id)
    if status:
        q = q.filter(StorageTank.status == status)
    if tank_name:
        q = q.filter(StorageTank.tank_name.ilike(f"%{tank_name}%"))

    return q

def _has_safe_treatment(source_id: int) -> bool:
    """Check if this source has at least one SAFE treatment record."""
    return db.session.query(
        db.exists().where(
            (TreatmentRecord.source_id == source_id) &
            (TreatmentRecord.quality_status == "Safe")
        )
    ).scalar()

# ---------- list (with pagination) ----------
@storage_tank_bp.route("/admin/storage-tanks")
@login_required
@role_required("Admin")
def list_tanks():
    # pagination safe parse
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    allowed_per_page = {10, 25, 50, 100}
    if per_page not in allowed_per_page:
        per_page = 25

    # base query + filters + order
    query = _apply_filters(StorageTank.query).order_by(StorageTank.id.desc())

    pagination = db.paginate(
        query,
        page=page,
        per_page=per_page,
        error_out=False,
        max_per_page=100,
    )
    items = pagination.items

    # DROPDOWN: Only sources that have at least one SAFE treatment record
    safe_sources = (
        db.session.query(WaterSource)
        .join(TreatmentRecord, TreatmentRecord.source_id == WaterSource.id)
        .filter(TreatmentRecord.quality_status == "Safe")
        .distinct()
        .order_by(WaterSource.source_name.asc())
        .all()
    )

    return render_template(
        "storage_tank/list.html",
        tanks=items,
        pagination=pagination,
        per_page=per_page,
        allowed_per_page=sorted(allowed_per_page),
        safe_sources=safe_sources,   # <â€” use in template dropdowns
    )

# ---------- create ----------
@storage_tank_bp.route("/admin/storage-tanks/new", methods=["POST"])
@login_required
@role_required("Admin")
def create_tank():
    source_id = request.form.get("source_id", type=int)

    tank = StorageTank(
        source_id        = source_id,
        tank_name        = (request.form.get("tank_name") or "").strip(),
        capacity_m3      = request.form.get("capacity_m3") or None,
        status           = request.form.get("status") or "Active",
        remarks          = request.form.get("remarks") or None,
    )

    if not tank.source_id or not tank.tank_name or not tank.capacity_m3:
        flash("Source, Tank Name and Capacity are required.", "danger")
        return redirect(url_for("storage_tank.list_tanks", **request.args))

    # Enforce SAFE treatment requirement
    if not _has_safe_treatment(tank.source_id):
        flash("Selected source has no SAFE treatment record. Choose another source.", "danger")
        return redirect(url_for("storage_tank.list_tanks", **request.args))

    db.session.add(tank)
    db.session.commit()
    flash("Storage tank created.", "success")
    return redirect(url_for("storage_tank.list_tanks", **request.args))

# ---------- edit ----------
@storage_tank_bp.route("/admin/storage-tanks/<int:tank_id>/edit", methods=["POST"])
@login_required
@role_required("Admin")
def edit_tank(tank_id):
    tank = StorageTank.query.get_or_404(tank_id)

    source_id = request.form.get("source_id", type=int)

    tank.source_id        = source_id
    tank.tank_name        = (request.form.get("tank_name") or "").strip()
    tank.capacity_m3      = request.form.get("capacity_m3") or None
    tank.status           = request.form.get("status") or "Active"
    tank.remarks          = request.form.get("remarks") or None

    if not tank.source_id or not tank.tank_name or not tank.capacity_m3:
        flash("Source, Tank Name and Capacity are required.", "danger")
        return redirect(url_for("storage_tank.list_tanks", **request.args))

    # Enforce SAFE treatment requirement on edit too
    if not _has_safe_treatment(tank.source_id):
        flash("Selected source has no SAFE treatment record. Choose another source.", "danger")
        return redirect(url_for("storage_tank.list_tanks", **request.args))

    db.session.commit()
    flash("Storage tank updated.", "success")
    return redirect(url_for("storage_tank.list_tanks", **request.args))

# ---------- delete ----------
@storage_tank_bp.route("/admin/storage-tanks/<int:tank_id>/delete", methods=["POST"])
@login_required
@role_required("Admin")
def delete_tank(tank_id):
    tank = StorageTank.query.get_or_404(tank_id)
    db.session.delete(tank)
    db.session.commit()
    flash("Storage tank deleted.", "info")
    return redirect(url_for("storage_tank.list_tanks", **request.args))

# ---------- exports (respect filters) ----------
@storage_tank_bp.route("/admin/storage-tanks/export.csv")
@login_required
@role_required("Admin")
def export_csv():
    query = _apply_filters(StorageTank.query).order_by(StorageTank.id.asc())
    rows = query.all()

    headers = [
        "ID", "Source", "Tank Name", "Capacity (m3)", "Current Level (m3)",
        "Last Inflow (m3)", "Last Inflow Date", "Last Outflow (m3)",
        "Last Outflow Date", "Status", "Remarks"
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for t in rows:
        writer.writerow([
            t.id,
            t.source.source_name if t.source else t.source_id,
            t.tank_name or "",
            f"{t.capacity_m3:.2f}" if t.capacity_m3 is not None else "",
            t.status or "",
            t.remarks or "",
        ])

    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    fname = f"storage_tanks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    resp.headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp

@storage_tank_bp.route("/admin/storage-tanks/export.xlsx")
@login_required
@role_required("Admin")
def export_xlsx():
    query = _apply_filters(StorageTank.query).order_by(StorageTank.id.asc())
    rows = query.all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Storage Tanks"

    headers = [
        "ID", "Source", "Tank Name", "Capacity (mÂ³)", "Current Level (mÂ³)",
        "Last Inflow (mÂ³)", "Last Inflow Date", "Last Outflow (mÂ³)",
        "Last Outflow Date", "Status", "Remarks"
    ]
    ws.append(headers)

    for t in rows:
        ws.append([
            t.id,
            (t.source.source_name if t.source else t.source_id),
            t.tank_name or "",
            float(t.capacity_m3) if t.capacity_m3 is not None else None,
            t.status or "",
            t.remarks or "",
        ])

    # simple auto-widths
    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(12, max_len + 2), 40)

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    fname = f"storage_tanks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        bio,
        as_attachment=True,
        download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


