from datetime import date
from io import BytesIO, StringIO
import csv

from flask import Blueprint, abort, make_response, render_template, request, send_file, url_for
from openpyxl import Workbook
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from app.Auth.blueprints.auth.models import User
from app.Auth.blueprints.auth.views import login_required, role_required
from app.Admin.blueprints.customer.models import Customer
from app.Admin.blueprints.invoice.models import Invoice
from app.Admin.blueprints.meter.models import Meter
from app.Admin.blueprints.meter_reading.models import MeterReading
from app.Admin.blueprints.receipt.models import Receipt
from app.Admin.blueprints.service_area.models import ServiceArea
from app.extensions import db

reports_bp = Blueprint("reports", __name__, template_folder="templates")

PAYMENT_METHOD_LABELS = {
    "cash": "Cash",
    "evc": "EVC",
    "edahab": "Edahab",
    "account": "Account",
}

REPORT_LINKS = [
    {"label": "Report", "endpoint": "reports.index", "icon": "fa-solid fa-layer-group", "description": "Open all report shortcuts in one place."},
    {"label": "Customer", "endpoint": "reports.customers_report", "icon": "fa-solid fa-users", "description": "Filter customers by created date and review the list."},
    {"label": "Area", "endpoint": "reports.service_areas_report", "icon": "fa-solid fa-map-location-dot", "description": "Filter service areas by date and review assignments."},
    {"label": "Meter", "endpoint": "reports.meters_report", "icon": "fa-solid fa-gauge-high", "description": "Filter meters by install date and review status."},
    {"label": "Reading", "endpoint": "reports.readings_report", "icon": "fa-solid fa-tachograph-digital", "description": "Filter meter readings by reading date."},
    {"label": "Invoice", "endpoint": "reports.invoices_report", "icon": "fa-solid fa-file-invoice-dollar", "description": "Filter invoices by issue date."},
    {"label": "Receipt", "endpoint": "reports.receipts_report", "icon": "fa-solid fa-receipt", "description": "Filter receipts by payment date."},
    {"label": "Revenue", "endpoint": "reports.revenue_report", "icon": "fa-solid fa-sack-dollar", "description": "Review company revenue collected from receipts."},
    {"label": "Collection", "endpoint": "reports.collections_report", "icon": "fa-solid fa-hand-holding-dollar", "description": "Filter outstanding invoices by due date."},
]

REPORT_ROUTE_MAP = {
    "customers": "reports.customers_report",
    "service_areas": "reports.service_areas_report",
    "meters": "reports.meters_report",
    "readings": "reports.readings_report",
    "invoices": "reports.invoices_report",
    "receipts": "reports.receipts_report",
    "revenue": "reports.revenue_report",
    "collections": "reports.collections_report",
}


def _fmt_count(value):
    return f"{int(value or 0):,}"


def _fmt_money(value):
    return f"{float(value or 0):,.2f}"


def _fmt_date(value):
    return value.isoformat() if value else "-"


def _pretty_label(value):
    return str(value).replace("_", " ").strip().title()


def _parse_date(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _date_range():
    start = _parse_date(request.args.get("from_date"))
    end = _parse_date(request.args.get("to_date"))
    if start and end and start > end:
        start, end = end, start
    return start, end


def _range_text(start, end):
    if start and end:
        return f"{start.isoformat()} to {end.isoformat()}"
    if start:
        return f"from {start.isoformat()}"
    if end:
        return f"up to {end.isoformat()}"
    return "all dates"


def _apply_date_filter(query, column, start, end):
    if start:
        query = query.filter(column >= start)
    if end:
        query = query.filter(column <= end)
    return query


def _query_text(name):
    return (request.args.get(name) or "").strip()


def _query_int(name):
    return request.args.get(name, type=int)


def _service_area_options(all_label="All service areas"):
    areas = ServiceArea.query.order_by(ServiceArea.area_name.asc()).all()
    return [{"value": "", "label": all_label}] + [
        {"value": str(area.id), "label": f"{area.area_name} ({area.area_code})" if area.area_code else area.area_name}
        for area in areas
    ]


def _customer_options(all_label="All customers"):
    customers = Customer.query.order_by(Customer.customer_name.asc()).all()
    return [{"value": "", "label": all_label}] + [
        {"value": str(customer.id), "label": f"{customer.customer_name} ({customer.customer_id})"}
        for customer in customers
    ]


def _distinct_options(model_column, all_label):
    values = [
        row[0]
        for row in db.session.query(model_column).distinct().order_by(model_column.asc()).all()
        if row[0] not in (None, "")
    ]
    return [{"value": "", "label": all_label}] + [{"value": str(value), "label": _pretty_label(value)} for value in values]


def _build_selected_label(options, value):
    if not value:
        return "All"
    value = str(value)
    for option in options:
        if str(option.get("value", "")) == value:
            return option.get("label", value)
    return value


def _active_filter_summary(date_label, start, end, filter_fields):
    summary = [{"label": date_label, "value": _range_text(start, end)}]
    for field in filter_fields:
        value = field.get("value")
        if value in (None, ""):
            continue
        if field.get("type") == "select":
            value = _build_selected_label(field.get("options", []), value)
        summary.append({"label": field.get("label", field.get("name", "Filter")), "value": value})
    return summary


def _export_csv(columns, rows, filename):
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow([column["label"] for column in columns])
    for row in rows:
        writer.writerow([row.get(column["key"], "") for column in columns])
    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def _export_xlsx(columns, rows, sheet_title, filename):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append([column["label"] for column in columns])
    for row in rows:
        ws.append([row.get(column["key"], "") for column in columns])
    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(12, max_len + 2), 42)
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return send_file(
        bio,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _report_action_urls(report_key):
    params = request.args.to_dict(flat=True)
    return {
        "export_csv_url": url_for("reports.report_export_csv", report_key=report_key, **params),
        "export_xlsx_url": url_for("reports.report_export_xlsx", report_key=report_key, **params),
        "print_url": url_for("reports.report_print", report_key=report_key, **params),
    }


def _render_report(report_key, spec):
    context = {
        "report_links": REPORT_LINKS,
        "current_report": REPORT_ROUTE_MAP[report_key],
        "report_key": report_key,
        "report_title": spec["report_title"],
        "report_eyebrow": spec["report_eyebrow"],
        "report_description": spec["report_description"],
        "filter_label": spec["filter_label"],
        "from_date": spec["from_date"],
        "to_date": spec["to_date"],
        "result_range": spec["result_range"],
        "filter_fields": spec["filter_fields"],
        "filter_summary": spec["filter_summary"],
        "report_metrics": spec.get("report_metrics", []),
        "table_title": spec["table_title"],
        "table_note": spec["table_note"],
        "table_columns": spec["table_columns"],
        "table_rows": spec["table_rows"],
        "row_count": len(spec["table_rows"]),
        "empty_message": spec["empty_message"],
    }
    context.update(_report_action_urls(report_key))
    return render_template("reports/detail.html", **context)


def _render_print(report_key, spec):
    params = request.args.to_dict(flat=True)
    current_report = REPORT_ROUTE_MAP[report_key]
    return render_template(
        "reports/print.html",
        report_key=report_key,
        current_report=current_report,
        back_url=url_for(current_report, **params),
        print_url=url_for("reports.report_print", report_key=report_key, **params),
        report_title=spec["report_title"],
        report_description=spec["report_description"],
        filter_summary=spec["filter_summary"],
        report_metrics=spec.get("report_metrics", []),
        table_title=spec["table_title"],
        table_columns=spec["table_columns"],
        table_rows=spec["table_rows"],
        row_count=len(spec["table_rows"]),
        generated_on=date.today().isoformat(),
    )


# ---------- report builders + routes ----------

def _fmt_quantity(value):
    return f"{float(value or 0):,.3f}"


def _customer_display(customer):
    if not customer:
        return "-"
    suffix = f" ({customer.customer_id})" if customer.customer_id else ""
    return f"{customer.customer_name or '-'}{suffix}"


def _service_area_display(area):
    if not area:
        return "-"
    suffix = f" ({area.area_code})" if area.area_code else ""
    return f"{area.area_name or '-'}{suffix}"


def _labeled_options(items, all_label):
    return [{"value": "", "label": all_label}] + [{"value": str(value), "label": label} for value, label in items]


def _invoice_status_options(all_label="All statuses"):
    return _labeled_options(
        [
            ("issued", "Issued"),
            ("unpaid", "Unpaid"),
            ("partial", "Partial"),
            ("paid", "Paid"),
        ],
        all_label,
    )


def _collection_status_options(all_label="All outstanding statuses"):
    return _labeled_options(
        [
            ("issued", "Issued"),
            ("unpaid", "Unpaid"),
            ("partial", "Partial"),
        ],
        all_label,
    )


def _payment_method_options(all_label="All payment methods"):
    return _labeled_options(
        [
            ("cash", "Cash"),
            ("evc", "EVC"),
            ("edahab", "Edahab"),
            ("account", "Account"),
        ],
        all_label,
    )


def _sheet_name(title):
    cleaned = "".join(ch for ch in title if ch not in "[]:*?/\\")
    return cleaned[:31] or "Report"


def build_customers_report():
    start, end = _date_range()
    service_area_id = _query_int("service_area_id")
    status = _query_text("status")
    q_text = _query_text("q")

    query = Customer.query.options(joinedload(Customer.service_area))
    if service_area_id:
        query = query.filter(Customer.service_area_id == service_area_id)
    if status:
        query = query.filter(Customer.status == status)
    if q_text:
        like = f"%{q_text}%"
        query = query.filter(
            or_(
                Customer.customer_name.ilike(like),
                Customer.customer_id.ilike(like),
                Customer.phone.ilike(like),
                Customer.address.ilike(like),
            )
        )
    query = _apply_date_filter(query, Customer.created_date, start, end)

    customers = query.order_by(Customer.customer_name.asc(), Customer.id.desc()).all()
    rows = [
        {
            "customer_id": customer.customer_id or "-",
            "customer_name": customer.customer_name or "-",
            "customer_type": _pretty_label(customer.customer_type),
            "service_area": _service_area_display(customer.service_area),
            "phone": customer.phone or "-",
            "created_date": _fmt_date(customer.created_date),
            "status": _pretty_label(customer.status),
        }
        for customer in customers
    ]

    filter_fields = [
        {
            "name": "service_area_id",
            "label": "Service Area",
            "type": "select",
            "value": str(service_area_id or ""),
            "options": _service_area_options(),
        },
        {
            "name": "status",
            "label": "Status",
            "type": "select",
            "value": status or "",
            "options": _distinct_options(Customer.status, "All statuses"),
        },
        {
            "name": "q",
            "label": "Search",
            "type": "text",
            "value": q_text,
            "placeholder": "Name, customer ID, phone, or address",
        },
    ]

    return {
        "report_title": "Customer Report",
        "report_eyebrow": "Customer intelligence",
        "report_description": "Review customers by date, service area, and status, then export the results for records or follow-up.",
        "filter_label": "Created Date",
        "from_date": start.isoformat() if start else "",
        "to_date": end.isoformat() if end else "",
        "result_range": "",
        "filter_fields": filter_fields,
        "filter_summary": _active_filter_summary("Created Date", start, end, filter_fields),
        "table_title": "Registered Customers",
        "table_note": "Customers currently stored in the system with their assigned service areas.",
        "table_columns": [
            {"key": "customer_id", "label": "Customer ID"},
            {"key": "customer_name", "label": "Full Name"},
            {"key": "customer_type", "label": "Type"},
            {"key": "service_area", "label": "Service Area"},
            {"key": "phone", "label": "Phone"},
            {"key": "created_date", "label": "Created Date", "align": "center"},
            {"key": "status", "label": "Status", "align": "center"},
        ],
        "table_rows": rows,
        "empty_message": "No customers matched the selected filters.",
        "sheet_title": "Customers",
    }


def build_service_areas_report():
    start, end = _date_range()
    q_text = _query_text("q")

    query = ServiceArea.query
    if q_text:
        like = f"%{q_text}%"
        query = query.filter(
            or_(
                ServiceArea.area_name.ilike(like),
                ServiceArea.area_code.ilike(like),
                ServiceArea.remarks.ilike(like),
            )
        )
    query = _apply_date_filter(query, ServiceArea.created_date, start, end)

    areas = query.order_by(ServiceArea.area_name.asc(), ServiceArea.id.desc()).all()

    customer_counts = dict(
        db.session.query(Customer.service_area_id, func.count(Customer.id))
        .group_by(Customer.service_area_id)
        .all()
    )
    meter_counts = dict(
        db.session.query(Customer.service_area_id, func.count(Meter.id))
        .join(Meter, Meter.customer_id == Customer.id)
        .group_by(Customer.service_area_id)
        .all()
    )
    staff_counts = dict(
        db.session.query(User.service_area_id, func.count(User.id))
        .filter(User.role == "Staff")
        .group_by(User.service_area_id)
        .all()
    )

    rows = [
        {
            "area_code": area.area_code or "-",
            "area_name": area.area_name or "-",
            "customers_count": _fmt_count(customer_counts.get(area.id, 0)),
            "meters_count": _fmt_count(meter_counts.get(area.id, 0)),
            "staff_count": _fmt_count(staff_counts.get(area.id, 0)),
            "created_date": _fmt_date(area.created_date),
            "remarks": area.remarks or "-",
        }
        for area in areas
    ]

    filter_fields = [
        {
            "name": "q",
            "label": "Search",
            "type": "text",
            "value": q_text,
            "placeholder": "Area code, area name, or remarks",
        }
    ]

    return {
        "report_title": "Service Area Report",
        "report_eyebrow": "Distribution mapping",
        "report_description": "Review each service area together with the number of customers, meters, and staff assigned to it.",
        "filter_label": "Created Date",
        "from_date": start.isoformat() if start else "",
        "to_date": end.isoformat() if end else "",
        "result_range": "",
        "filter_fields": filter_fields,
        "filter_summary": _active_filter_summary("Created Date", start, end, filter_fields),
        "table_title": "Service Areas",
        "table_note": "Area coverage and assignment counts across the system.",
        "table_columns": [
            {"key": "area_code", "label": "Area Code"},
            {"key": "area_name", "label": "Area Name"},
            {"key": "customers_count", "label": "Customers", "align": "end"},
            {"key": "meters_count", "label": "Meters", "align": "end"},
            {"key": "staff_count", "label": "Staff", "align": "end"},
            {"key": "created_date", "label": "Created Date", "align": "center"},
            {"key": "remarks", "label": "Remarks"},
        ],
        "table_rows": rows,
        "empty_message": "No service areas matched the selected filters.",
        "sheet_title": "Areas",
    }


def build_meters_report():
    start, end = _date_range()
    service_area_id = _query_int("service_area_id")
    customer_id = _query_int("customer_id")
    status = _query_text("status")
    serial = _query_text("meter_serial")

    query = Meter.query.options(joinedload(Meter.customer).joinedload(Customer.service_area))
    if customer_id:
        query = query.filter(Meter.customer_id == customer_id)
    if service_area_id:
        query = query.filter(Meter.customer.has(Customer.service_area_id == service_area_id))
    if status:
        query = query.filter(Meter.status == status)
    if serial:
        query = query.filter(Meter.meter_serial.ilike(f"%{serial}%"))
    query = _apply_date_filter(query, Meter.install_date, start, end)

    meters = query.order_by(Meter.install_date.desc(), Meter.id.desc()).all()
    rows = [
        {
            "meter_serial": meter.meter_serial or "-",
            "customer": _customer_display(meter.customer),
            "service_area": _service_area_display(meter.customer.service_area if meter.customer else None),
            "install_date": _fmt_date(meter.install_date),
            "status": _pretty_label(meter.status),
        }
        for meter in meters
    ]

    filter_fields = [
        {
            "name": "service_area_id",
            "label": "Service Area",
            "type": "select",
            "value": str(service_area_id or ""),
            "options": _service_area_options(),
        },
        {
            "name": "customer_id",
            "label": "Customer",
            "type": "select",
            "value": str(customer_id or ""),
            "options": _customer_options(),
        },
        {
            "name": "status",
            "label": "Status",
            "type": "select",
            "value": status or "",
            "options": _distinct_options(Meter.status, "All statuses"),
        },
        {
            "name": "meter_serial",
            "label": "Meter Serial",
            "type": "text",
            "value": serial,
            "placeholder": "Search by meter serial",
        },
    ]

    return {
        "report_title": "Meter Report",
        "report_eyebrow": "Asset register",
        "report_description": "Track installed meters by customer, service area, date, and status.",
        "filter_label": "Install Date",
        "from_date": start.isoformat() if start else "",
        "to_date": end.isoformat() if end else "",
        "result_range": "",
        "filter_fields": filter_fields,
        "filter_summary": _active_filter_summary("Install Date", start, end, filter_fields),
        "table_title": "Installed Meters",
        "table_note": "Meters connected to customers and service areas.",
        "table_columns": [
            {"key": "meter_serial", "label": "Meter Serial"},
            {"key": "customer", "label": "Customer"},
            {"key": "service_area", "label": "Service Area"},
            {"key": "install_date", "label": "Install Date", "align": "center"},
            {"key": "status", "label": "Status", "align": "center"},
        ],
        "table_rows": rows,
        "empty_message": "No meters matched the selected filters.",
        "sheet_title": "Meters",
    }


def build_readings_report():
    start, end = _date_range()
    service_area_id = _query_int("service_area_id")
    customer_id = _query_int("customer_id")
    meter_serial = _query_text("meter_serial")

    query = MeterReading.query.options(
        joinedload(MeterReading.customer).joinedload(Customer.service_area),
        joinedload(MeterReading.meter),
    )
    if customer_id:
        query = query.filter(MeterReading.customer_id == customer_id)
    if service_area_id:
        query = query.filter(MeterReading.customer.has(Customer.service_area_id == service_area_id))
    if meter_serial:
        query = query.filter(MeterReading.meter.has(Meter.meter_serial.ilike(f"%{meter_serial}%")))
    query = _apply_date_filter(query, MeterReading.reading_date, start, end)

    readings = query.order_by(MeterReading.reading_date.desc(), MeterReading.id.desc()).all()
    rows = [
        {
            "reading_date": _fmt_date(reading.reading_date),
            "meter_serial": reading.meter.meter_serial if reading.meter else "-",
            "customer": _customer_display(reading.customer),
            "service_area": _service_area_display(reading.customer.service_area if reading.customer else None),
            "last_read_m3": _fmt_quantity(reading.last_read_m3),
            "current_read_m3": _fmt_quantity(reading.current_read_m3),
            "used_water_m3": _fmt_quantity(reading.used_water_m3),
            "rate_per_m3": _fmt_money(reading.rate_per_m3),
            "amount_due": _fmt_money(reading.amount_due),
        }
        for reading in readings
    ]

    filter_fields = [
        {
            "name": "service_area_id",
            "label": "Service Area",
            "type": "select",
            "value": str(service_area_id or ""),
            "options": _service_area_options(),
        },
        {
            "name": "customer_id",
            "label": "Customer",
            "type": "select",
            "value": str(customer_id or ""),
            "options": _customer_options(),
        },
        {
            "name": "meter_serial",
            "label": "Meter Serial",
            "type": "text",
            "value": meter_serial,
            "placeholder": "Search by meter serial",
        },
    ]

    return {
        "report_title": "Reading Report",
        "report_eyebrow": "Consumption audit",
        "report_description": "Review meter readings, used water, and calculated charges for each customer.",
        "filter_label": "Reading Date",
        "from_date": start.isoformat() if start else "",
        "to_date": end.isoformat() if end else "",
        "result_range": "",
        "filter_fields": filter_fields,
        "filter_summary": _active_filter_summary("Reading Date", start, end, filter_fields),
        "table_title": "Meter Readings",
        "table_note": "Reading history with water usage and computed billing amount.",
        "table_columns": [
            {"key": "reading_date", "label": "Reading Date", "align": "center"},
            {"key": "meter_serial", "label": "Meter Serial"},
            {"key": "customer", "label": "Customer"},
            {"key": "service_area", "label": "Service Area"},
            {"key": "last_read_m3", "label": "Last Read (m3)", "align": "end"},
            {"key": "current_read_m3", "label": "Current Read (m3)", "align": "end"},
            {"key": "used_water_m3", "label": "Used (m3)", "align": "end"},
            {"key": "rate_per_m3", "label": "Rate / m3", "align": "end"},
            {"key": "amount_due", "label": "Amount", "align": "end"},
        ],
        "table_rows": rows,
        "empty_message": "No meter readings matched the selected filters.",
        "sheet_title": "Readings",
    }


def build_invoices_report():
    start, end = _date_range()
    service_area_id = _query_int("service_area_id")
    customer_id = _query_int("customer_id")
    status = _query_text("status")
    invoice_no = _query_text("invoice_no")

    query = Invoice.query.options(joinedload(Invoice.customer).joinedload(Customer.service_area))
    if customer_id:
        query = query.filter(Invoice.customer_id == customer_id)
    if service_area_id:
        query = query.filter(Invoice.customer.has(Customer.service_area_id == service_area_id))
    if status:
        query = query.filter(Invoice.status == status)
    if invoice_no:
        query = query.filter(Invoice.invoice_no.ilike(f"%{invoice_no}%"))
    query = _apply_date_filter(query, Invoice.issue_date, start, end)

    invoices = query.order_by(Invoice.issue_date.desc(), Invoice.id.desc()).all()
    rows = [
        {
            "invoice_no": invoice.invoice_no or "-",
            "customer": _customer_display(invoice.customer),
            "service_area": _service_area_display(invoice.customer.service_area if invoice.customer else None),
            "issue_date": _fmt_date(invoice.issue_date),
            "due_date": _fmt_date(invoice.due_date),
            "amount": _fmt_money(invoice.amount),
            "amount_paid": _fmt_money(invoice.amount_paid),
            "balance_due": _fmt_money(invoice.balance_due),
            "status": _pretty_label(invoice.status),
            "currency": invoice.currency or "-",
        }
        for invoice in invoices
    ]

    filter_fields = [
        {
            "name": "service_area_id",
            "label": "Service Area",
            "type": "select",
            "value": str(service_area_id or ""),
            "options": _service_area_options(),
        },
        {
            "name": "customer_id",
            "label": "Customer",
            "type": "select",
            "value": str(customer_id or ""),
            "options": _customer_options(),
        },
        {
            "name": "status",
            "label": "Status",
            "type": "select",
            "value": status or "",
            "options": _invoice_status_options(),
        },
        {
            "name": "invoice_no",
            "label": "Invoice No",
            "type": "text",
            "value": invoice_no,
            "placeholder": "Search by invoice number",
        },
    ]

    return {
        "report_title": "Invoice Report",
        "report_eyebrow": "Billing intelligence",
        "report_description": "Filter invoices by issue date, customer, service area, and billing status.",
        "filter_label": "Issue Date",
        "from_date": start.isoformat() if start else "",
        "to_date": end.isoformat() if end else "",
        "result_range": "",
        "filter_fields": filter_fields,
        "filter_summary": _active_filter_summary("Issue Date", start, end, filter_fields),
        "table_title": "Invoices",
        "table_note": "Invoice records generated from meter readings and payment activity.",
        "table_columns": [
            {"key": "invoice_no", "label": "Invoice No"},
            {"key": "customer", "label": "Customer"},
            {"key": "service_area", "label": "Service Area"},
            {"key": "issue_date", "label": "Issue Date", "align": "center"},
            {"key": "due_date", "label": "Due Date", "align": "center"},
            {"key": "amount", "label": "Amount", "align": "end"},
            {"key": "amount_paid", "label": "Paid", "align": "end"},
            {"key": "balance_due", "label": "Balance Due", "align": "end"},
            {"key": "status", "label": "Status", "align": "center"},
            {"key": "currency", "label": "Currency", "align": "center"},
        ],
        "table_rows": rows,
        "empty_message": "No invoices matched the selected filters.",
        "sheet_title": "Invoices",
    }


def build_receipts_report():
    start, end = _date_range()
    service_area_id = _query_int("service_area_id")
    customer_id = _query_int("customer_id")
    payment_method = _query_text("payment_method")
    receipt_no = _query_text("receipt_no")

    query = Receipt.query.options(
        joinedload(Receipt.customer).joinedload(Customer.service_area),
        joinedload(Receipt.invoice),
    )
    if customer_id:
        query = query.filter(Receipt.customer_id == customer_id)
    if service_area_id:
        query = query.filter(Receipt.customer.has(Customer.service_area_id == service_area_id))
    if payment_method:
        query = query.filter(Receipt.payment_method == payment_method)
    if receipt_no:
        query = query.filter(Receipt.receipt_no.ilike(f"%{receipt_no}%"))
    query = _apply_date_filter(query, Receipt.payment_date, start, end)

    receipts = query.order_by(Receipt.payment_date.desc(), Receipt.id.desc()).all()
    rows = [
        {
            "receipt_no": receipt.receipt_no or "-",
            "invoice_no": receipt.invoice.invoice_no if receipt.invoice else "-",
            "customer": _customer_display(receipt.customer),
            "service_area": _service_area_display(receipt.customer.service_area if receipt.customer else None),
            "payment_date": _fmt_date(receipt.payment_date),
            "payment_method": PAYMENT_METHOD_LABELS.get(receipt.payment_method, _pretty_label(receipt.payment_method)),
            "amount_paid": _fmt_money(receipt.amount_paid),
            "balance_before": _fmt_money(receipt.balance_before),
            "balance_after": _fmt_money(receipt.balance_after),
            "currency": receipt.invoice.currency if receipt.invoice and receipt.invoice.currency else "-",
        }
        for receipt in receipts
    ]

    filter_fields = [
        {
            "name": "service_area_id",
            "label": "Service Area",
            "type": "select",
            "value": str(service_area_id or ""),
            "options": _service_area_options(),
        },
        {
            "name": "customer_id",
            "label": "Customer",
            "type": "select",
            "value": str(customer_id or ""),
            "options": _customer_options(),
        },
        {
            "name": "payment_method",
            "label": "Payment Method",
            "type": "select",
            "value": payment_method or "",
            "options": _payment_method_options(),
        },
        {
            "name": "receipt_no",
            "label": "Receipt No",
            "type": "text",
            "value": receipt_no,
            "placeholder": "Search by receipt number",
        },
    ]

    return {
        "report_title": "Receipt Report",
        "report_eyebrow": "Collection intelligence",
        "report_description": "Review payment receipts, balances before and after payment, and the payment method used.",
        "filter_label": "Payment Date",
        "from_date": start.isoformat() if start else "",
        "to_date": end.isoformat() if end else "",
        "result_range": "",
        "filter_fields": filter_fields,
        "filter_summary": [],
        "table_title": "Receipts",
        "table_note": "Recorded payments against invoices and their remaining balances.",
        "table_columns": [
            {"key": "receipt_no", "label": "Receipt No"},
            {"key": "invoice_no", "label": "Invoice No"},
            {"key": "customer", "label": "Customer"},
            {"key": "service_area", "label": "Service Area"},
            {"key": "payment_date", "label": "Payment Date", "align": "center"},
            {"key": "payment_method", "label": "Method", "align": "center"},
            {"key": "amount_paid", "label": "Amount Paid", "align": "end"},
            {"key": "balance_before", "label": "Balance Before", "align": "end"},
            {"key": "balance_after", "label": "Balance After", "align": "end"},
            {"key": "currency", "label": "Currency", "align": "center"},
        ],
        "table_rows": rows,
        "empty_message": "No receipts matched the selected filters.",
        "sheet_title": "Receipts",
    }


def build_revenue_report():
    start, end = _date_range()

    base_query = Receipt.query.join(Receipt.customer).outerjoin(Customer.service_area)
    base_query = _apply_date_filter(base_query, Receipt.payment_date, start, end)

    totals = base_query.with_entities(
        func.count(Receipt.id).label("receipt_count"),
        func.coalesce(func.sum(Receipt.amount_paid), 0).label("total_revenue"),
    ).one()

    revenue_rows = (
        base_query.with_entities(
            ServiceArea.area_name.label("service_area_name"),
            ServiceArea.area_code.label("service_area_code"),
            Receipt.payment_date.label("payment_date"),
            Receipt.payment_method.label("payment_method"),
            func.count(Receipt.id).label("receipt_count"),
            func.coalesce(func.sum(Receipt.amount_paid), 0).label("total_revenue"),
        )
        .group_by(ServiceArea.id, ServiceArea.area_name, ServiceArea.area_code, Receipt.payment_date, Receipt.payment_method)
        .order_by(func.coalesce(ServiceArea.area_name, "Unassigned").asc(), Receipt.payment_date.desc(), Receipt.payment_method.asc())
        .all()
    )

    rows = []
    service_area_labels = set()
    for row in revenue_rows:
        service_area_label = row.service_area_name or "Unassigned"
        if row.service_area_code:
            service_area_label = f"{service_area_label} ({row.service_area_code})"
        service_area_labels.add(service_area_label)
        rows.append(
            {
                "service_area": service_area_label,
                "payment_date": _fmt_date(row.payment_date),
                "payment_method": PAYMENT_METHOD_LABELS.get(row.payment_method, _pretty_label(row.payment_method)),
                "receipt_count": _fmt_count(row.receipt_count),
                "total_revenue": _fmt_money(row.total_revenue),
                "avg_receipt": _fmt_money((row.total_revenue or 0) / (row.receipt_count or 1)),
            }
        )

    receipt_count = totals.receipt_count or 0
    total_revenue = totals.total_revenue or 0
    report_metrics = [
        {"label": "Total Revenue", "value": _fmt_money(total_revenue)},
        {"label": "Receipts", "value": _fmt_count(receipt_count)},
        {"label": "Average Receipt", "value": _fmt_money((total_revenue or 0) / (receipt_count or 1))},
        {"label": "Service Areas", "value": _fmt_count(len(service_area_labels))},
    ]

    filter_fields = []

    return {
        "report_title": "Revenue Report",
        "report_eyebrow": "Company revenue",
        "report_description": "Review revenue collected from receipts across the selected period, grouped by service area, payment date, and payment method.",
        "filter_label": "Payment Date",
        "from_date": start.isoformat() if start else "",
        "to_date": end.isoformat() if end else "",
        "result_range": "",
        "filter_fields": filter_fields,
        "filter_summary": [],
        "report_metrics": [],
        "table_title": "Revenue Summary",
        "table_note": "Revenue grouped by service area, payment date, and payment method.",
        "table_columns": [
            {"key": "service_area", "label": "Service Area"},
            {"key": "payment_date", "label": "Payment Date", "align": "center"},
            {"key": "payment_method", "label": "Method", "align": "center"},
            {"key": "receipt_count", "label": "Receipts", "align": "end"},
            {"key": "total_revenue", "label": "Revenue", "align": "end"},
            {"key": "avg_receipt", "label": "Avg Receipt", "align": "end"},
        ],
        "table_rows": rows,
        "empty_message": "No revenue records matched the selected filters.",
        "sheet_title": "Revenue",
    }

def build_collections_report():
    start, end = _date_range()
    service_area_id = _query_int("service_area_id")
    customer_id = _query_int("customer_id")
    status = _query_text("status")
    invoice_no = _query_text("invoice_no")
    today = date.today()

    query = Invoice.query.options(joinedload(Invoice.customer).joinedload(Customer.service_area)).filter(Invoice.balance_due > 0)
    if customer_id:
        query = query.filter(Invoice.customer_id == customer_id)
    if service_area_id:
        query = query.filter(Invoice.customer.has(Customer.service_area_id == service_area_id))
    if status:
        query = query.filter(Invoice.status == status)
    if invoice_no:
        query = query.filter(Invoice.invoice_no.ilike(f"%{invoice_no}%"))
    query = _apply_date_filter(query, Invoice.due_date, start, end)

    invoices = query.order_by(Invoice.due_date.asc(), Invoice.id.desc()).all()
    rows = [
        {
            "invoice_no": invoice.invoice_no or "-",
            "customer": _customer_display(invoice.customer),
            "service_area": _service_area_display(invoice.customer.service_area if invoice.customer else None),
            "issue_date": _fmt_date(invoice.issue_date),
            "due_date": _fmt_date(invoice.due_date),
            "days_overdue": str(max((today - invoice.due_date).days, 0)) if invoice.due_date else "-",
            "amount": _fmt_money(invoice.amount),
            "amount_paid": _fmt_money(invoice.amount_paid),
            "balance_due": _fmt_money(invoice.balance_due),
            "status": _pretty_label(invoice.status),
            "currency": invoice.currency or "-",
        }
        for invoice in invoices
    ]

    filter_fields = [
        {
            "name": "service_area_id",
            "label": "Service Area",
            "type": "select",
            "value": str(service_area_id or ""),
            "options": _service_area_options(),
        },
        {
            "name": "customer_id",
            "label": "Customer",
            "type": "select",
            "value": str(customer_id or ""),
            "options": _customer_options(),
        },
        {
            "name": "status",
            "label": "Status",
            "type": "select",
            "value": status or "",
            "options": _collection_status_options(),
        },
        {
            "name": "invoice_no",
            "label": "Invoice No",
            "type": "text",
            "value": invoice_no,
            "placeholder": "Search by invoice number",
        },
    ]

    return {
        "report_title": "Collection Report",
        "report_eyebrow": "Outstanding balances",
        "report_description": "Track unpaid and partially paid invoices that still have balances due.",
        "filter_label": "Due Date",
        "from_date": start.isoformat() if start else "",
        "to_date": end.isoformat() if end else "",
        "result_range": "",
        "filter_fields": filter_fields,
        "filter_summary": _active_filter_summary("Due Date", start, end, filter_fields),
        "table_title": "Outstanding Collections",
        "table_note": "Invoices that still require payment collection.",
        "table_columns": [
            {"key": "invoice_no", "label": "Invoice No"},
            {"key": "customer", "label": "Customer"},
            {"key": "service_area", "label": "Service Area"},
            {"key": "issue_date", "label": "Issue Date", "align": "center"},
            {"key": "due_date", "label": "Due Date", "align": "center"},
            {"key": "days_overdue", "label": "Days Overdue", "align": "end"},
            {"key": "amount", "label": "Amount", "align": "end"},
            {"key": "amount_paid", "label": "Paid", "align": "end"},
            {"key": "balance_due", "label": "Balance Due", "align": "end"},
            {"key": "status", "label": "Status", "align": "center"},
            {"key": "currency", "label": "Currency", "align": "center"},
        ],
        "table_rows": rows,
        "empty_message": "No outstanding invoices matched the selected filters.",
        "sheet_title": "Collections",
    }


REPORT_BUILDERS = {
    "customers": build_customers_report,
    "service_areas": build_service_areas_report,
    "meters": build_meters_report,
    "readings": build_readings_report,
    "invoices": build_invoices_report,
    "receipts": build_receipts_report,
    "revenue": build_revenue_report,
    "collections": build_collections_report,
}


def _get_report_builder(report_key):
    builder = REPORT_BUILDERS.get(report_key)
    if builder is None:
        abort(404)
    return builder


@reports_bp.route("/admin/reports")
@login_required
@role_required("Admin")
def index():
    return render_template(
        "reports/index.html",
        quick_links=REPORT_LINKS,
        report_links=REPORT_LINKS,
        current_report="reports.index",
    )


@reports_bp.route("/admin/reports/customers")
@login_required
@role_required("Admin")
def customers_report():
    return _render_report("customers", _get_report_builder("customers")())


@reports_bp.route("/admin/reports/service-areas")
@login_required
@role_required("Admin")
def service_areas_report():
    return _render_report("service_areas", _get_report_builder("service_areas")())


@reports_bp.route("/admin/reports/meters")
@login_required
@role_required("Admin")
def meters_report():
    return _render_report("meters", _get_report_builder("meters")())


@reports_bp.route("/admin/reports/readings")
@login_required
@role_required("Admin")
def readings_report():
    return _render_report("readings", _get_report_builder("readings")())


@reports_bp.route("/admin/reports/invoices")
@login_required
@role_required("Admin")
def invoices_report():
    return _render_report("invoices", _get_report_builder("invoices")())


@reports_bp.route("/admin/reports/receipts")
@login_required
@role_required("Admin")
def receipts_report():
    return _render_report("receipts", _get_report_builder("receipts")())


@reports_bp.route("/admin/reports/revenue")
@login_required
@role_required("Admin")
def revenue_report():
    return _render_report("revenue", _get_report_builder("revenue")())

@reports_bp.route("/admin/reports/collections")
@login_required
@role_required("Admin")
def collections_report():
    return _render_report("collections", _get_report_builder("collections")())


@reports_bp.route("/admin/reports/<report_key>/export.csv")
@login_required
@role_required("Admin")
def report_export_csv(report_key):
    builder = _get_report_builder(report_key)
    spec = builder()
    filename = f"{report_key}_report_{date.today().strftime('%Y%m%d')}.csv"
    return _export_csv(spec["table_columns"], spec["table_rows"], filename)


@reports_bp.route("/admin/reports/<report_key>/export.xlsx")
@login_required
@role_required("Admin")
def report_export_xlsx(report_key):
    builder = _get_report_builder(report_key)
    spec = builder()
    filename = f"{report_key}_report_{date.today().strftime('%Y%m%d')}.xlsx"
    return _export_xlsx(
        spec["table_columns"],
        spec["table_rows"],
        _sheet_name(spec["sheet_title"]),
        filename,
    )


@reports_bp.route("/admin/reports/<report_key>/print")
@login_required
@role_required("Admin")
def report_print(report_key):
    builder = _get_report_builder(report_key)
    spec = builder()
    return _render_print(report_key, spec)



