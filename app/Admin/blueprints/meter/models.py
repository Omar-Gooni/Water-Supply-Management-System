from app.extensions import db
from datetime import date

class Meter(db.Model):
    __tablename__ = "meters"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    meter_serial = db.Column(db.String(50), unique=True, nullable=False)
    install_date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(20), nullable=False, default="Active")
    customer = db.relationship("Customer", backref=db.backref("meters", lazy=True))

    def __repr__(self):
        return f"<Meter {self.meter_serial}>"
