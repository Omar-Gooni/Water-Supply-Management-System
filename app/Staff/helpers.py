from flask import session

from app.Auth.blueprints.auth.models import User


def current_staff_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return User.query.filter_by(id=user_id, role='Staff').first()


def current_staff_service_area_id():
    user = current_staff_user()
    return user.service_area_id if user else None
