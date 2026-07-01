from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func

from app.Auth.blueprints.auth.views import login_required, role_required
from app.Admin.blueprints.customer.models import Customer
from app.Admin.blueprints.invoice.models import Invoice
from app.Admin.blueprints.service_area.models import ServiceArea
from app.extensions import db
from app.utils.billing import apply_invoice_payment

from .models import Receipt

receipt_bp = Blueprint("receipt", __name__, template_folder="templates")

PAYMENT_METHODS = {
    "cash": "Cash",
    "evc": "EVC",
    "edahab": "Edahab",
    "account": "Account",
}
SCOPE_ALL_CUSTOMERS = "all_customers"
SCOPE_ONE_CUSTOMER = "one_customer"


def _today() -> date:
    return date.today()


def _normalize_scope(scope: str | None) -> str:
    if scope in (SCOPE_ALL_CUSTOMERS, SCOPE_ONE_CUSTOMER):
        return scope
    return SCOPE_ALL_CUSTOMERS


def _normalize_payment_method(value: str | None) -> str:
    value = (value or "cash").strip().lower()
    return value if value in PAYMENT_METHODS else "cash"


def _selected_ids():
    service_area_id = request.args.get("service_area_id", type=int)
    customer_id = request.args.get("customer_id", type=int)
    scope = _normalize_scope(request.args.get("scope"))
    return service_area_id, customer_id, scope


def _customer_query(service_area_id: int | None):
    query = Customer.query.filter(Customer.status == "active")
    if service_area_id:
        query = query.filter(Customer.service_area_id == service_area_id)
    return query.order_by(Customer.customer_name.asc())


def _customer_summary_rows(service_area_id: int | None):
    query = (
        db.session.query(
            Customer,
            func.count(Invoice.id).label("invoice_count"),
            func.coalesce(func.sum(Invoice.amount), 0).label("total_amount"),
            func.coalesce(func.sum(Invoice.amount_paid), 0).label("total_paid"),
            func.coalesce(func.sum(Invoice.balance_due), 0).label("total_balance"),
        )
        .outerjoin(Invoice, Invoice.customer_id == Customer.id)
        .filter(Customer.status == "active")
    )
    if service_area_id:
        query = query.filter(Customer.service_area_id == service_area_id)
    rows = query.group_by(Customer.id).order_by(Customer.customer_name.asc()).all()

    summaries = []
    for customer, invoice_count, total_amount, total_paid, total_balance in rows:
        summaries.append(
            {
                "customer": customer,
                "customer_id": customer.id,
                "customer_code": customer.customer_id,
                "customer_name": customer.customer_name,
                "service_area_name": customer.service_area.area_name if customer.service_area else "",
                "service_area_code": customer.service_area.area_code if customer.service_area else "",
                "invoice_count": int(invoice_count or 0),
                "total_amount": float(total_amount or 0),
                "total_paid": float(total_paid or 0),
                "total_balance": float(total_balance or 0),
            }
        )
    return summaries


def _selected_customer(service_area_id: int | None, customer_id: int | None):
    if not customer_id:
        return None
    query = Customer.query.filter(Customer.id == customer_id, Customer.status == "active")
    if service_area_id:
        query = query.filter(Customer.service_area_id == service_area_id)
    return query.first()


def _customer_invoices(customer_id: int):
    return (
        Invoice.query
        .filter(Invoice.customer_id == customer_id)
        .order_by(Invoice.issue_date.desc(), Invoice.id.desc())
        .all()
    )


def _customer_outstanding_invoices(customer_id: int):
    return (
        Invoice.query
        .filter(Invoice.customer_id == customer_id)
        .filter(Invoice.balance_due > 0)
        .order_by(Invoice.issue_date.asc(), Invoice.id.asc())
        .all()
    )


def _currency_for_service_area(service_area_id: int | None) -> str:
    query = (
        Invoice.query.join(Customer, Customer.id == Invoice.customer_id)
        .filter(Customer.status == "active")
    )
    if service_area_id:
        query = query.filter(Customer.service_area_id == service_area_id)
    row = (
        query.filter(Invoice.currency.isnot(None))
        .filter(Invoice.currency != "")
        .with_entities(Invoice.currency)
        .order_by(Invoice.id.asc())
        .first()
    )
    return row[0] if row and row[0] else "USD"


def _recent_receipts(service_area_id: int | None = None, customer_id: int | None = None):
    query = Receipt.query.join(Customer, Customer.id == Receipt.customer_id)
    if service_area_id:
        query = query.filter(Customer.service_area_id == service_area_id)
    if customer_id:
        query = query.filter(Receipt.customer_id == customer_id)
    return query.order_by(Receipt.id.desc()).limit(10).all()


def _next_receipt_seed() -> int:
    last_id = db.session.query(func.coalesce(func.max(Receipt.id), 0)).scalar()
    return int(last_id or 0) + 1


def _build_receipt_row(invoice, customer, amount_paid, balance_before, balance_after, payment_method, remarks, receipt_seed):
    receipt = Receipt(
        receipt_no=f"REC-{receipt_seed:04d}",
        invoice_id=invoice.id,
        customer_id=customer.id,
        amount_paid=round(float(amount_paid or 0), 2),
        balance_before=round(float(balance_before or 0), 2),
        balance_after=round(float(balance_after or 0), 2),
        payment_method=payment_method,
        payment_date=_today(),
        remarks=remarks or None,
    )
    db.session.add(receipt)
    return receipt


def _apply_payment_to_customer(customer, payment_amount, payment_method, remarks, receipt_seed):
    outstanding_invoices = _customer_outstanding_invoices(customer.id)
    outstanding_before = round(sum(float(inv.balance_due or 0) for inv in outstanding_invoices), 2)
    amount_to_apply = round(min(float(payment_amount or 0), outstanding_before), 2)
    created_receipts = []

    if amount_to_apply <= 0:
        return created_receipts, 0.0, outstanding_before, outstanding_before, receipt_seed

    remaining = amount_to_apply
    next_seed = receipt_seed
    for invoice in outstanding_invoices:
        if remaining <= 0:
            break
        applied, balance_before, balance_after, _status = apply_invoice_payment(invoice, remaining)
        if applied <= 0:
            continue
        created_receipts.append(
            _build_receipt_row(
                invoice=invoice,
                customer=customer,
                amount_paid=applied,
                balance_before=balance_before,
                balance_after=balance_after,
                payment_method=payment_method,
                remarks=remarks,
                receipt_seed=next_seed,
            )
        )
        next_seed += 1
        remaining = round(remaining - float(applied or 0), 2)

    applied_total = round(sum(float(receipt.amount_paid or 0) for receipt in created_receipts), 2)
    remaining_after = round(max(outstanding_before - applied_total, 0), 2)
    return created_receipts, applied_total, outstanding_before, remaining_after, next_seed


def _collect_service_area_receipts(service_area_id, payment_method, remarks):
    customers = _customer_query(None).all()
    next_seed = _next_receipt_seed()
    created_receipts = []
    applied_total = 0.0
    customer_count = 0

    for customer in customers:
        outstanding_before = round(sum(float(inv.balance_due or 0) for inv in _customer_outstanding_invoices(customer.id)), 2)
        if outstanding_before <= 0:
            continue
        customer_count += 1
        receipts, applied, _before, _after, next_seed = _apply_payment_to_customer(
            customer=customer,
            payment_amount=outstanding_before,
            payment_method=payment_method,
            remarks=remarks,
            receipt_seed=next_seed,
        )
        created_receipts.extend(receipts)
        applied_total += applied

    return created_receipts, round(applied_total, 2), customer_count


def _aggregate_rows(rows):
    return {
        "invoice_count": sum(row["invoice_count"] for row in rows),
        "total_amount": round(sum(row["total_amount"] for row in rows), 2),
        "total_paid": round(sum(row["total_paid"] for row in rows), 2),
        "total_balance": round(sum(row["total_balance"] for row in rows), 2),
    }


@receipt_bp.route("/admin/receipts")
@login_required
@role_required("Admin")
def list_receipts():
    service_area_id, customer_id, scope = _selected_ids()
    service_areas = ServiceArea.query.order_by(ServiceArea.area_name.asc()).all()
    customers = _customer_query(None).all()
    customer_summary_rows = _customer_summary_rows(None)
    selected_service_area = db.session.get(ServiceArea, service_area_id) if service_area_id else None
    selected_customer = _selected_customer(service_area_id, customer_id)
    selected_invoices = _customer_invoices(selected_customer.id) if selected_customer else []

    area_rows = [
        row for row in customer_summary_rows
        if not selected_service_area or (row["customer"] and row["customer"].service_area_id == selected_service_area.id)
    ]

    if scope == SCOPE_ONE_CUSTOMER and selected_customer:
        selected_summary = next((row for row in customer_summary_rows if row["customer_id"] == selected_customer.id), None)
        summary_data = selected_summary or {
            "invoice_count": 0,
            "total_amount": 0.0,
            "total_paid": 0.0,
            "total_balance": 0.0,
        }
        summary_label = selected_customer.customer_name
    else:
        selected_summary = None
        summary_data = _aggregate_rows(area_rows) if area_rows else {
            "invoice_count": 0,
            "total_amount": 0.0,
            "total_paid": 0.0,
            "total_balance": 0.0,
        }
        summary_label = selected_service_area.area_name if selected_service_area else "All customers"

    summary_currency = _currency_for_service_area(service_area_id)
    if selected_invoices:
        for invoice in selected_invoices:
            if invoice.currency:
                summary_currency = invoice.currency
                break

    recent_receipts = _recent_receipts()
    receipt_modal_open = bool(request.args.get("open_receipt") or service_area_id or customer_id)

    return render_template(
        "receipt/list.html",
        service_areas=service_areas,
        customers=customers,
        customer_summary_rows=customer_summary_rows,
        selected_service_area=selected_service_area,
        selected_customer=selected_customer,
        selected_invoices=selected_invoices,
        selected_summary=summary_data,
        summary_label=summary_label,
        summary_currency=summary_currency,
        recent_receipts=recent_receipts,
        payment_methods=PAYMENT_METHODS,
        scope=scope,
        receipt_modal_open=receipt_modal_open,
        service_area_id=service_area_id,
        customer_id=customer_id,
    )


@receipt_bp.route("/admin/receipts/create", methods=["POST"])
@login_required
@role_required("Admin")
def create_receipts():
    service_area_id = request.form.get("service_area_id", type=int)
    scope = _normalize_scope(request.form.get("scope"))
    customer_id = request.form.get("customer_id", type=int)
    payment_method = _normalize_payment_method(request.form.get("payment_method"))
    remarks = (request.form.get("remarks") or "").strip()

    if scope == SCOPE_ALL_CUSTOMERS:
        if not service_area_id:
            flash("Choose a service area before creating receipts for all customers.", "danger")
            return redirect(url_for("receipt.list_receipts", scope=SCOPE_ALL_CUSTOMERS, open_receipt=1))

        area = db.session.get(ServiceArea, service_area_id)
        if area is None:
            flash("Selected service area was not found.", "danger")
            return redirect(url_for("receipt.list_receipts", open_receipt=1))

        created_receipts, applied_total, customer_count = _collect_service_area_receipts(
            service_area_id=service_area_id,
            payment_method=payment_method,
            remarks=remarks,
        )
        if not created_receipts:
            flash("No outstanding balances were found for that service area.", "info")
            return redirect(url_for("receipt.list_receipts", service_area_id=service_area_id, scope=SCOPE_ALL_CUSTOMERS, open_receipt=1))

        db.session.commit()
        flash(
            f"Created {len(created_receipts)} receipt(s) for {customer_count} customer(s) in {area.area_name}. Total collected {applied_total:.2f}.",
            "success",
        )
        return redirect(url_for("receipt.list_receipts", service_area_id=service_area_id, scope=SCOPE_ALL_CUSTOMERS, open_receipt=1))

    customer = _selected_customer(service_area_id, customer_id)
    if customer is None:
        flash("Choose a valid customer before creating a receipt.", "danger")
        return redirect(url_for("receipt.list_receipts", service_area_id=service_area_id, scope=SCOPE_ONE_CUSTOMER, open_receipt=1))

    try:
        payment_amount = float(request.form.get("payment_amount", 0) or 0)
    except (TypeError, ValueError):
        payment_amount = 0.0

    if payment_amount <= 0:
        flash("Enter a valid receipt amount.", "danger")
        return redirect(url_for("receipt.list_receipts", service_area_id=service_area_id, customer_id=customer.id, scope=SCOPE_ONE_CUSTOMER, open_receipt=1))

    created_receipts, applied_total, outstanding_before, remaining_after, _ = _apply_payment_to_customer(
        customer=customer,
        payment_amount=payment_amount,
        payment_method=payment_method,
        remarks=remarks,
        receipt_seed=_next_receipt_seed(),
    )

    if not created_receipts:
        flash("This customer has no outstanding balance.", "info")
        return redirect(url_for("receipt.list_receipts", service_area_id=service_area_id, customer_id=customer.id, scope=SCOPE_ONE_CUSTOMER, open_receipt=1))

    db.session.commit()

    if payment_amount > applied_total:
        flash(
            f"Only {applied_total:.2f} was applied because that was the remaining balance. Remaining balance is {remaining_after:.2f}.",
            "warning",
        )
    elif remaining_after <= 0:
        flash(f"Receipt(s) created for {customer.customer_name}. The customer is now fully paid.", "success")
    else:
        flash(
            f"Receipt(s) created for {customer.customer_name}. Outstanding balance moved from {outstanding_before:.2f} to {remaining_after:.2f}.",
            "success",
        )

    return redirect(url_for("receipt.list_receipts", service_area_id=service_area_id, customer_id=customer.id, scope=SCOPE_ONE_CUSTOMER, open_receipt=1))


@receipt_bp.route("/admin/receipts/invoice/<int:invoice_id>", methods=["POST"])
@login_required
@role_required("Admin")
def record_receipt(invoice_id: int):
    invoice = Invoice.query.get_or_404(invoice_id)

    try:
        payment_amount = float(request.form.get("payment_amount", 0))
    except (TypeError, ValueError):
        payment_amount = 0.0

    if payment_amount <= 0:
        flash("Enter a valid receipt amount.", "danger")
        return redirect(url_for("receipt.list_receipts", customer_id=invoice.customer_id, open_receipt=1))

    payment_method = _normalize_payment_method(request.form.get("payment_method"))
    remarks = (request.form.get("remarks") or "").strip()
    applied, balance_before, balance_after, status = apply_invoice_payment(invoice, payment_amount)
    if applied <= 0:
        flash("This invoice has no outstanding balance.", "info")
        return redirect(url_for("receipt.list_receipts", customer_id=invoice.customer_id, open_receipt=1))

    receipt = Receipt(
        receipt_no=f"REC-{_next_receipt_seed():04d}",
        invoice_id=invoice.id,
        customer_id=invoice.customer_id,
        amount_paid=applied,
        balance_before=balance_before,
        balance_after=balance_after,
        payment_method=payment_method,
        payment_date=_today(),
        remarks=remarks or None,
    )
    db.session.add(receipt)
    db.session.commit()

    if payment_amount > applied:
        flash(
            f"Only {applied:.2f} was applied because that is the remaining balance. Receipt {receipt.receipt_no} created.",
            "warning",
        )
    else:
        flash(f"Receipt {receipt.receipt_no} created. Invoice is now {status.title()}.", "success")
    return redirect(url_for("receipt.list_receipts", customer_id=invoice.customer_id, scope=SCOPE_ONE_CUSTOMER, open_receipt=1))


@receipt_bp.route("/admin/receipts/<int:receipt_id>/print")
@login_required
@role_required("Admin")
def print_receipt(receipt_id: int):
    receipt = Receipt.query.get_or_404(receipt_id)
    return render_template(
        "receipt/receipt_print.html",
        receipt=receipt,
        inv=receipt.invoice,
        cust=receipt.customer,
        payment_method_label=PAYMENT_METHODS.get(receipt.payment_method or "", "Cash"),
        today=_today(),
    )