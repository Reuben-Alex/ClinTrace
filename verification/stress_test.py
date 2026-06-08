"""NHAMCS stress test — batch triage with evals and Phoenix logging.

Usage:
    python -m verification.stress_test --n_samples 100
"""

from __future__ import annotations

import argparse
import asyncio

from verification.run_verification import run_verification


async def run_stress_test(
    n_samples: int = 100,
    delay: float = 1.0,
    output_path: str = "results_stress_nhamcs.csv",
    years: list[int] | None = None,
) -> None:
    """Run a larger NHAMCS verification pass with evals enabled."""
    await run_verification(
        n_samples=n_samples,
        output_path=output_path,
        delay_between=delay,
        run_evals=True,
        run_diag_eval=True,
        log_phoenix=True,
        years=years,
    )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="NHAMCS stress test for ClinTrace"
    )
    parser.add_argument(
        "--n_samples",
        type=int,
        default=100,
        help="Number of NHAMCS cases (default: 100)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between cases in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results_stress_nhamcs.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--years",
        type=str,
        default="2022",
        help="Comma-separated NHAMCS years",
    )
    args = parser.parse_args()
    years = [int(y.strip()) for y in args.years.split(",")]

    asyncio.run(
        run_stress_test(
            n_samples=args.n_samples,
            delay=args.delay,
            output_path=args.output,
            years=years,
        )
    )


if __name__ == "__main__":
    main()
