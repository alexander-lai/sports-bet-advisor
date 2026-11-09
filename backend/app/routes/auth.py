"""JWT register / login and the current user's profile."""
import re

from flask import Blueprint, jsonify
from flask_jwt_extended import create_access_token, jwt_required
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from ..errors import AppError
from ..extensions import db
from ..models import User
from ..utils import parse_float
from . import current_user, json_body

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_BANKROLL = 1_000_000_000


def _token_response(user, status=200):
    token = create_access_token(identity=str(user.id))
    return jsonify(access_token=token, user=user.to_dict()), status


@bp.post("/register")
def register():
    data = json_body()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    if not EMAIL_RE.match(email):
        raise AppError("A valid email is required")
    if len(password) < 8:
        raise AppError("Password must be at least 8 characters")
    bankroll = parse_float(
        data.get("bankroll", 1000), "bankroll", 0, MAX_BANKROLL
    )
    exists = db.session.scalar(select(User).where(User.email == email))
    if exists:
        raise AppError("Email is already registered", 409)
    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        bankroll=bankroll,
    )
    db.session.add(user)
    db.session.commit()
    return _token_response(user, 201)


@bp.post("/login")
def login():
    data = json_body()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    user = db.session.scalar(select(User).where(User.email == email))
    if user is None or not check_password_hash(
        user.password_hash, password
    ):
        raise AppError("Invalid email or password", 401)
    return _token_response(user)


@bp.get("/me")
@jwt_required()
def me():
    return jsonify(user=current_user().to_dict())


@bp.patch("/me")
@jwt_required()
def update_me():
    user = current_user()
    data = json_body()
    if "bankroll" in data:
        user.bankroll = parse_float(
            data["bankroll"], "bankroll", 0, MAX_BANKROLL
        )
    db.session.commit()
    return jsonify(user=user.to_dict())
