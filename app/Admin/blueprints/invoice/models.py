from app.extensions import db
from datetime import date
from sqlalchemy import event

class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    invoice_no = db.Column(db.String(32), unique=True, nullable=False, index=True)

    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    reading_id  = db.Column(db.Integer, db.ForeignKey("meter_readings.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True)

    period_start      = db.Column(db.Date, nullable=False)
    period_end        = db.Column(db.Date, nullable=False)
    last_read_m3      = db.Column(db.Numeric(12, 3), nullable=False)
    current_read_m3   = db.Column(db.Numeric(12, 3), nullable=False)
    used_water_m3     = db.Column(db.Numeric(12, 3), nullable=False)
    rate_per_m3       = db.Column(db.Numeric(12, 3), nullable=False, default=0.75)
    amount            = db.Column(db.Numeric(12, 2), nullable=False)

    issue_date        = db.Column(db.Date, nullable=False, default=date.today)
    due_date          = db.Column(db.Date, nullable=False)
    status            = db.Column(db.String(16), nullable=False, default="issued")  # issued/unpaid/paid
    currency          = db.Column(db.String(8), nullable=True)
    
    remarks           = db.Column(db.String(255), nullable=True)

    # Relationships
    customer = db.relationship("Customer", backref=db.backref("invoices", lazy="dynamic"))
    reading  = db.relationship("MeterReading", backref=db.backref("invoice", uselist=False))


# ==========================
# Auto-generate Invoice No.
# ==========================
@event.listens_for(Invoice, "before_insert")
def generate_invoice_no(mapper, connection, target):
    prefix = "INV-"
    # Find the last invoice id
    last_id = connection.execute(db.select(db.func.max(Invoice.id))).scalar()
    next_num = (last_id or 0) + 1
    # Format with 4-digit padding (e.g. INV-0001, INV-0002, ...)
    target.invoice_no = f"{prefix}{next_num:04d}"
