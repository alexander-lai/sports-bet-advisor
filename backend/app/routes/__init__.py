from flask import request
from flask_jwt_extended import get_jwt_identity

from ..errors import AppError
from ..extensions import db
from ..models import User


def current_user():
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        raise AppError("User not found", 404)
    return user


def json_body():
    return request.get_json(silent=True) or {}
