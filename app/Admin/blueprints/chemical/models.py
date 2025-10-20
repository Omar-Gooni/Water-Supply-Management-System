from app.extensions import db

class Chemical(db.Model):
    __tablename__ = "chemical"

    id = db.Column(db.Integer, primary_key=True)
    chemical_name = db.Column(db.String(100), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    default_dose_mgL = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(20), default="Active")
    remarks = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<Chemical {self.chemical_name}>"
    
