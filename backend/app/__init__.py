"""Flask application factory."""
import logging

from flask import Flask, jsonify
from flask_cors import CORS

from .config import Config
from .errors import register_error_handlers
from .extensions import db, jwt


def create_app(overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    if not app.config["JWT_SECRET_KEY"]:
        raise RuntimeError("JWT_SECRET is not set; see .env.example")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db.init_app(app)
    jwt.init_app(app)
    CORS(app, origins=app.config["CORS_ORIGINS"])
    register_error_handlers(app)

    from .routes.auth import bp as auth_bp
    from .routes.backtest import bp as backtest_bp
    from .routes.bets import bp as bets_bp
    from .routes.model import bp as model_bp
    from .routes.predictions import bp as predictions_bp

    for blueprint in (
        auth_bp, predictions_bp, bets_bp, model_bp, backtest_bp
    ):
        app.register_blueprint(blueprint)

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    from . import models  # noqa: F401  (register tables)
    from .cli import register_cli

    register_cli(app)

    with app.app_context():
        db.create_all()

    return app
