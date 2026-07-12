from app.extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(32), nullable=True)
    created_date = db.Column(db.Date, nullable=False, default=date.today)
    service_area_id = db.Column(
        db.Integer,
        db.ForeignKey("service_areas.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role = db.Column(db.String(20), nullable=False, default="Counter")  # "Admin", "Staff", or "Counter"

    service_area = db.relationship("ServiceArea", backref=db.backref("staff_members", lazy="dynamic"), lazy="joined")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"
