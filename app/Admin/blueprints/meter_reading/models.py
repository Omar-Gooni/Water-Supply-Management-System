# app/Admin/blueprints/meter_reading/models.py
from app.extensions import db
from sqlalchemy import UniqueConstraint
from datetime import date

class MeterReading(db.Model):
    __tablename__ = "meter_readings"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    meter_id = db.Column(db.Integer, db.ForeignKey("meters.id", ondelete="RESTRICT"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)

    last_read_m3    = db.Column(db.Numeric(12, 3), nullable=False, default=0)
    current_read_m3 = db.Column(db.Numeric(12, 3), nullable=False)
    used_water_m3   = db.Column(db.Numeric(12, 3), nullable=False)
    rate_per_m3     = db.Column(db.Numeric(12, 3), nullable=False)
    amount_due      = db.Column(db.Numeric(12, 3), nullable=False)

    reading_date    = db.Column(db.Date, nullable=False, default=date.today)

    # Relations
    meter    = db.relationship("Meter", backref=db.backref("readings", lazy="dynamic"))
    customer = db.relationship("Customer", backref=db.backref("readings", lazy="dynamic"))


