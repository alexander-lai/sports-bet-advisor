"""Error type shared by routes and services, rendered as JSON."""
from flask import jsonify
from werkzeug.exceptions import HTTPException


class AppError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def register_error_handlers(app):
    @app.errorhandler(AppError)
    def _app_error(exc):
        return jsonify(error=exc.message), exc.status

    @app.errorhandler(HTTPException)
    def _http_error(exc):
        return jsonify(error=exc.description), exc.code

    @app.errorhandler(Exception)
    def _unexpected(exc):
        app.logger.exception("Unhandled error")
        return jsonify(error="Internal server error"), 500
