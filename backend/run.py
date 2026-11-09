"""Development entry point.

On first run (nothing seeded and no trained model) this runs the
seeding script before starting the API, so predictions work
immediately. Pass --skip-seed to start the API anyway.
"""
import argparse
import os

from app import create_app
from app.services.pipeline import is_seeded, run_seed, start_scheduler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-seed", action="store_true")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("PORT", "5000"))
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        if (
            not args.skip_seed
            and app.config["AUTO_SEED"]
            and not is_seeded()
        ):
            app.logger.info("First run detected: seeding data")
            run_seed()
    if app.config["ENABLE_SCHEDULER"]:
        start_scheduler(app)
    app.run(host=args.host, port=args.port, use_reloader=False)


if __name__ == "__main__":
    main()
