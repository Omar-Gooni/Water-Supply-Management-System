from datetime import date

from sqlalchemy import event

from app.extensions import db


class Receipt(db.Model):
    __tablename__ = "receipts"

    id = db.Column(db.Integer, primary_key=True)
    receipt_no = db.Column(db.String(32), unique=True, nullable=False, index=True)

    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)

    amount_paid = db.Column(db.Numeric(12, 2), nullable=False)
    balance_before = db.Column(db.Numeric(12, 2), nullable=False)
    balance_after = db.Column(db.Numeric(12, 2), nullable=False)
    payment_method = db.Column(db.String(32), nullable=False, default="cash")
    payment_date = db.Column(db.Date, nullable=False, default=date.today)
    remarks = db.Column(db.String(255), nullable=True)

    invoice = db.relationship("Invoice", backref=db.backref("receipts", lazy="dynamic", cascade="all, delete-orphan"))
    customer = db.relationship("Customer", backref=db.backref("receipts", lazy="dynamic"))


@event.listens_for(Receipt, "before_insert")
def generate_receipt_no(mapper, connection, target):
    if getattr(target, "receipt_no", None):
        return

    prefix = "REC-"
    last_id = connection.execute(db.select(db.func.max(Receipt.id))).scalar()
    next_num = (last_id or 0) + 1
    target.receipt_no = f"{prefix}{next_num:04d}"