from datetime import date
from app.extensions import db
from app.Admin.blueprints.source.models import WaterSource

class StorageTank(db.Model):
    __tablename__ = "storage_tank"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    source_id = db.Column(db.Integer, db.ForeignKey(WaterSource.id), nullable=False)
    source = db.relationship(WaterSource, backref=db.backref("storage_tank", lazy="dynamic"))
    tank_name = db.Column(db.String(120), nullable=False)
    capacity_m3       = db.Column(db.Numeric(10, 2), nullable=False)  
    current_level_m3  = db.Column(db.Numeric(10, 2), nullable=True)   
    last_inflow_m3    = db.Column(db.Numeric(10, 2), nullable=True)
    last_outflow_m3   = db.Column(db.Numeric(10, 2), nullable=True)
    last_inflow_date  = db.Column(db.Date, nullable=True)
    last_outflow_date = db.Column(db.Date, nullable=True)
    status  = db.Column(db.String(20), nullable=False, default="Active")
    remarks = db.Column(db.Text, nullable=True)

    # ---- convenience helpers (optional) ----
    @property
    def percent_full(self):
        """Return current fill percentage (0–100) if capacity and level are set."""
        if self.capacity_m3 and self.current_level_m3 is not None:
            try:
                return float(self.current_level_m3) / float(self.capacity_m3) * 100.0
            except ZeroDivisionError:
                return 0.0
        return None

    def __repr__(self):
        return f"<StorageTank id={self.id} name={self.tank_name!r} source_id={self.source_id}>"
