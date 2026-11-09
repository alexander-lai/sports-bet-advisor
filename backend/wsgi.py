"""WSGI entry point, e.g. `gunicorn -w 1 wsgi:app`.

Use a single worker (or ENABLE_SCHEDULER=false on all but one) so
the nightly job is not scheduled more than once.
"""
from app import create_app
from app.services.pipeline import start_scheduler

app = create_app()

if app.config["ENABLE_SCHEDULER"] and __name__ != "__main__":
    import sys

    # `flask --app wsgi <command>` imports this module too; only
    # schedule for long-running servers.
    if "flask" not in sys.argv[0]:
        start_scheduler(app)
