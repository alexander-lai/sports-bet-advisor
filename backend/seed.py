"""Seeding script: python seed.py [--force]

Fetches every game log for SEED_SEASONS (default 2023-24, 2024-25,
2025-26) plus the current season so far from Ball Don't Lie, stores
them in PostgreSQL, engineers features, trains the XGBoost models and
saves them with joblib. Safe to re-run: finished seasons are skipped
and an interrupted season resumes from its last page.
"""
import argparse

from app import create_app
from app.services.pipeline import run_seed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="re-fetch every season"
    )
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        summary = run_seed(force=args.force)
    print(f"Trained on {summary['n_rows']} rows, seasons "
          f"{summary['seasons']}")
    for stat, metrics in summary["metrics"].items():
        print(f"  {stat}: MAE {metrics['mae']:.2f} "
              f"(rolling-avg baseline {metrics['baseline_mae']:.2f})")


if __name__ == "__main__":
    main()
