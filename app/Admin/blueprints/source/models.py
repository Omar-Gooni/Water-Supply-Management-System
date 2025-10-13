from app.extensions import db
from datetime import date

class WaterSource(db.Model):
    __tablename__ = "water_sources"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    source_name = db.Column(db.String(120), nullable=False)
    source_type = db.Column(db.String(30), nullable=False)     # well / borehole / dam / river
    location = db.Column(db.String(120), nullable=False)
    capacity_m3_day = db.Column(db.Numeric(10, 2), nullable=True)   # daily capacity
    status = db.Column(db.String(30), nullable=False, default="Active")  # Active / Inactive / Maintenance
    last_production_date = db.Column(db.Date, nullable=True, default=None)
    last_volume_m3 = db.Column(db.Numeric(10, 2), nullable=True)
    remarks = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<WaterSource {self.source_name} ({self.source_type})>"
