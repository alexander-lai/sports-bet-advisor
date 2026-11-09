"""Flask CLI commands: `flask --app wsgi <command>`."""
from datetime import date

import click


def register_cli(app):
    @app.cli.command("seed")
    @click.option("--force", is_flag=True, help="Re-fetch every season.")
    def seed_command(force):
        """Fetch historical seasons and train the model."""
        from .services.pipeline import run_seed

        run_seed(force=force)

    @app.cli.command("refresh")
    def refresh_command():
        """Run the nightly refresh job now."""
        from .services.pipeline import nightly_refresh

        nightly_refresh()

    @app.cli.command("retrain")
    def retrain_command():
        """Retrain the model on all stored game logs."""
        from .services.training import retrain

        click.echo(retrain()["metrics"])

    @app.cli.command("fetch-historical-odds")
    @click.option("--start", required=True, help="YYYY-MM-DD")
    @click.option("--days", default=7, show_default=True)
    def historical_command(start, days):
        """Backfill historical prop lines (paid Odds API plan)."""
        from .services.historical import fetch_historical_lines

        stored = fetch_historical_lines(date.fromisoformat(start), days)
        click.echo(f"Stored {stored} historical lines")
