# app/Admin/blueprints/customer/models.py
from datetime import date
from app.extensions import db
from sqlalchemy import event, func
import re

from app.Admin.blueprints.service_area.models import ServiceArea
from app.Admin.blueprints.pipeline.models import Pipeline


class Customer(db.Model):
    __tablename__ = "customers"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    customer_id = db.Column(db.String(32), unique=True, nullable=False, index=True)  
    customer_name = db.Column(db.String(120), nullable=False)
    customer_type = db.Column(db.String(32), nullable=False) 
    address = db.Column(db.String(200))
    phone = db.Column(db.String(32))
    
    service_area_id = db.Column(db.Integer, db.ForeignKey("service_areas.id", ondelete="RESTRICT"),
                                nullable=False, index=True,)
    supply_line_id = db.Column(db.Integer,db.ForeignKey("pipelines.id", ondelete="RESTRICT"), 
                               nullable=False, index=True,)
    created_date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(20), nullable=False, default="active") 

    service_area = db.relationship(ServiceArea, backref=db.backref("customers", lazy="dynamic"), lazy="joined")
    supply_line = db.relationship(Pipeline, backref=db.backref("customers", lazy="dynamic"), lazy="joined")

    def __repr__(self):
        return f"<Customer #{self.id} {self.customer_id} - {self.customer_name}>"


# ---------- AUTO-GENERATE customer_id ----------
PREFIX = "CUS-"
PAD = 6  # CUS-000001

@event.listens_for(Customer, "before_insert")
def _set_customer_id(mapper, connection, target: Customer):
    """Auto-creates customer_id before insert (like CUS-000001)."""
    if target.customer_id:
        return

    tbl = Customer.__table__
    result = connection.execute(
        db.select(tbl.c.customer_id)
          .where(tbl.c.customer_id.like(f"{PREFIX}%"))
          .order_by(tbl.c.customer_id.desc())
          .limit(1)
    ).first()

    next_num = 1
    if result and result[0]:
        m = re.search(rf"^{re.escape(PREFIX)}(\d+)$", result[0])
        if m:
            next_num = int(m.group(1)) + 1

    target.customer_id = f"{PREFIX}{str(next_num).zfill(PAD)}"
