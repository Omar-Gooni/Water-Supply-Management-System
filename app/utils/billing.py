from flask import current_app

from app.Admin.blueprints.customer.models import Customer
from app.Admin.blueprints.meter.models import Meter
from app.Admin.blueprints.meter_reading.models import MeterReading


def get_default_water_rate() -> float:
    return float(current_app.config.get('WATER_RATE_PER_M3', 0.75))


def latest_reading_for_customer(customer_id: int, exclude_reading_id: int | None = None):
    query = MeterReading.query.filter(MeterReading.customer_id == customer_id)
    if exclude_reading_id is not None:
        query = query.filter(MeterReading.id != exclude_reading_id)
    return query.order_by(MeterReading.reading_date.desc(), MeterReading.id.desc()).first()


def auto_last_read(customer_id: int, exclude_reading_id: int | None = None) -> float:
    reading = latest_reading_for_customer(customer_id, exclude_reading_id=exclude_reading_id)
    if reading is None:
        return 0.0
    if reading.current_read_m3 is not None:
        return float(reading.current_read_m3)
    if reading.last_read_m3 is not None:
        return float(reading.last_read_m3)
    return 0.0


def auto_rate(customer_id: int, exclude_reading_id: int | None = None) -> float:
    reading = latest_reading_for_customer(customer_id, exclude_reading_id=exclude_reading_id)
    if reading is not None and reading.rate_per_m3 is not None:
        return float(reading.rate_per_m3)
    return get_default_water_rate()


def calculate_reading_values(
    customer_id: int,
    current_read_m3,
    *,
    exclude_reading_id: int | None = None,
    rate_override=None,
    allow_rate_override: bool = True,
):
    last_read = auto_last_read(customer_id, exclude_reading_id=exclude_reading_id)

    if allow_rate_override and rate_override not in (None, ''):
        rate_per_m3 = float(rate_override)
    else:
        rate_per_m3 = auto_rate(customer_id, exclude_reading_id=exclude_reading_id)

    current_value = float(current_read_m3 or 0)
    used_water = max(0.0, current_value - last_read)
    amount_due = round(used_water * rate_per_m3, 3)
    return last_read, rate_per_m3, used_water, amount_due


def customer_reading_snapshot() -> dict[int, dict]:
    active_customers = Customer.query.filter(Customer.status == 'active').all()
    customer_ids = [customer.id for customer in active_customers]
    if not customer_ids:
        return {}

    readings = (
        MeterReading.query
        .filter(MeterReading.customer_id.in_(customer_ids))
        .order_by(
            MeterReading.customer_id.asc(),
            MeterReading.reading_date.desc(),
            MeterReading.id.desc(),
        )
        .all()
    )
    meters = {meter.id: meter for meter in Meter.query.all()}

    snapshot = {}
    for reading in readings:
        if reading.customer_id in snapshot:
            continue
        meter = meters.get(reading.meter_id)
        last_read = float(reading.current_read_m3 if reading.current_read_m3 is not None else (reading.last_read_m3 or 0))
        rate = float(reading.rate_per_m3 if reading.rate_per_m3 is not None else get_default_water_rate())
        used = float(reading.used_water_m3 or max(0.0, float(reading.current_read_m3 or 0) - float(reading.last_read_m3 or 0)))
        snapshot[reading.customer_id] = {
            'reading_id': reading.id,
            'meter_serial': (meter.meter_serial if meter else '') or '',
            'reading_date': reading.reading_date.isoformat() if reading.reading_date else '',
            'last_read_m3': last_read,
            'current_read_m3': float(reading.current_read_m3 or 0),
            'used_water_m3': used,
            'rate_per_m3': rate,
            'amount': round(used * rate, 3),
        }
    return snapshot


def apply_invoice_payment(invoice, payment_amount):
    def _normalized_status(value):
        return value if value in {'unpaid', 'partial', 'paid'} else 'unpaid'
    try:
        requested_amount = float(payment_amount or 0)
    except (TypeError, ValueError):
        requested_amount = 0.0

    total_amount = float(invoice.amount or 0)
    paid_before = float(invoice.amount_paid or 0)
    balance_before = max(round(total_amount - paid_before, 2), 0)

    if requested_amount <= 0:
        return 0.0, balance_before, balance_before, _normalized_status(invoice.status)

    applied_amount = round(min(requested_amount, balance_before), 2)
    if applied_amount <= 0:
        return 0.0, balance_before, balance_before, _normalized_status(invoice.status)

    paid_after = round(paid_before + applied_amount, 2)
    balance_after = max(round(total_amount - paid_after, 2), 0)

    invoice.amount_paid = paid_after
    invoice.balance_due = balance_after

    if paid_after <= 0:
        invoice.status = 'unpaid'
    elif balance_after <= 0:
        invoice.status = 'paid'
    else:
        invoice.status = 'partial'

    return applied_amount, balance_before, balance_after, _normalized_status(invoice.status)