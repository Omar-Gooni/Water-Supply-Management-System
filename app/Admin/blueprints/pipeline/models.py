# app/Admin/blueprints/pipeline/models.py
from app.extensions import db
from datetime import date

class Pipeline(db.Model):
    __tablename__ = "pipelines"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tank_id = db.Column(db.Integer, db.ForeignKey("storage_tank.id"), nullable=False)
    service_area_id = db.Column(db.Integer, db.ForeignKey("service_areas.id"), nullable=False)
    line_name = db.Column(db.String(120), nullable=False)
    pipe_diameter_mm = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), default="Active")
    last_supply_date = db.Column(db.Date, default=date.today)
    remarks = db.Column(db.Text)

    # Relationships
    tank = db.relationship("StorageTank", backref="pipelines", lazy=True)
    service_area = db.relationship("ServiceArea", backref="pipelines", lazy=True)

    def __repr__(self):
        return f"<Pipeline {self.line_name} ({self.status})>"
