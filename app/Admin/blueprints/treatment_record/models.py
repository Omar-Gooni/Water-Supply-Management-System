from app.extensions import db

class TreatmentRecord(db.Model):
    __tablename__ = "treatment_records"

    id = db.Column(db.Integer, primary_key=True)

    # FKs
    source_id   = db.Column(db.Integer, db.ForeignKey("water_sources.id"), nullable=False)
    chemical_id = db.Column(db.Integer, db.ForeignKey("chemical.id"), nullable=False)

    # Dates & volumes
    treatment_date    = db.Column(db.Date, nullable=False)
    raw_water_m3      = db.Column(db.Numeric(12, 2), nullable=True)
    treated_water_m3  = db.Column(db.Numeric(12, 2), nullable=True)

    # Chemical usage
    amount_used = db.Column(db.Numeric(12, 3), nullable=True)
    unit        = db.Column(db.String(20), nullable=False)  # kg / L / mg/L

    # Lab readings
    ph_level       = db.Column(db.Numeric(4, 2), nullable=True)
    turbidity_ntu  = db.Column(db.Numeric(6, 2), nullable=True)
    chlorine_mgL   = db.Column(db.Numeric(6, 3), nullable=True)

    # Status & metadata
    quality_status = db.Column(db.String(20), nullable=True)  # Safe / Unsafe
    operator_name  = db.Column(db.String(100), nullable=True)
    remarks        = db.Column(db.Text, nullable=True)

    # Relationships (optional helpers)
    source   = db.relationship("WaterSource", backref=db.backref("treatment_records", lazy="dynamic"))
    chemical = db.relationship("Chemical",    backref=db.backref("treatment_records", lazy="dynamic"))

    def __repr__(self):
        return f"<TreatmentRecord #{self.id}>"
