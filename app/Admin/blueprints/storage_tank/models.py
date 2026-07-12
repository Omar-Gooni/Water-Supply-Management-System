from app.extensions import db
from app.Admin.blueprints.source.models import WaterSource

class StorageTank(db.Model):
    __tablename__ = "storage_tank"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    source_id = db.Column(db.Integer, db.ForeignKey(WaterSource.id), nullable=False)
    source = db.relationship(WaterSource, backref=db.backref("storage_tank", lazy="dynamic"))
    tank_name = db.Column(db.String(120), nullable=False)
    capacity_m3       = db.Column(db.Numeric(10, 2), nullable=False)  
    status  = db.Column(db.String(20), nullable=False, default="Active")
    remarks = db.Column(db.Text, nullable=True)


    def __repr__(self):
        return f"<StorageTank id={self.id} name={self.tank_name!r} source_id={self.source_id}>"


