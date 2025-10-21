# app/Admin/blueprints/service_area/models.py
from app.extensions import db
from sqlalchemy import event

class ServiceArea(db.Model):
    __tablename__ = "service_areas"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    area_code = db.Column(db.String(20), unique=True, index=True)
    area_name = db.Column(db.String(120), nullable=False)
    remarks = db.Column(db.Text)

    def __repr__(self):
        return f"<ServiceArea {self.area_code} - {self.area_name}>"

# ---------- Auto-generate area_code ----------
@event.listens_for(ServiceArea, "before_insert")
def generate_area_code(mapper, connect, target):
    prefix = "AREA-"
    # find last record
    last_id = connect.execute(db.select(db.func.max(ServiceArea.id))).scalar()
    next_num = (last_id or 0) + 1
    target.area_code = f"{prefix}{next_num:03d}"
