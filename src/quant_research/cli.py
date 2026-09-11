import argparse
from datetime import date
from decimal import Decimal, DecimalException
from importlib.resources import files
from pathlib import Path
import sqlite3
import subprocess

from .data import Dataset
from .engine import run
from .evaluation import evaluate
from .walk_forward import WalkForwardConfig, walk_forward
from .uncertainty import UncertaintyConfig
from .market_data import fetch, load_snapshot
from .models import Config
from .reporting import save_bundle
from .strategies import BreakoutConfig, research_strategies


def main():
    parser = argparse.ArgumentParser(description="Auditable daily-bar ETF research")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("demo", "backtest", "evaluate", "walk-forward"):
        p = sub.add_parser(command)
        p.add_argument("--output", type=Path, default=Path("var/runs"))
        p.add_argument("--initial-cash", type=Decimal, default=Decimal("1000"))
        p.add_argument("--allocation", type=Decimal, default=Decimal("0.20"))
        p.add_argument("--fee-bps", type=Decimal, default=Decimal("5"))
        p.add_argument("--slippage-bps", type=Decimal, default=Decimal("5"))
        p.add_argument("--lookback", type=int, default=20)
        p.add_argument("--max-holding-bars", type=int, default=5)
        if command != "demo":
            inputs = p.add_mutually_exclusive_group(required=True)
            inputs.add_argument("--csv", type=Path)
            inputs.add_argument("--snapshot", type=Path)
            p.add_argument("--symbol")
            p.add_argument("--actions", type=Path, help="ordinary dividends/as-traded splits JSON for --csv only")
        if command == "evaluate":
            p.add_argument("--split", type=date.fromisoformat, required=True, help="first evaluation decision session")
        if command == "walk-forward":
            p.add_argument("--train-sessions", type=int, default=80)
            p.add_argument("--test-sessions", type=int, default=40)
            p.add_argument("--gap-sessions", type=int, default=5)
            p.add_argument("--min-training-trades", type=int, default=3)
            p.add_argument("--uncertainty", action="store_true", help="exploratory paired-block bootstrap and Holm diagnostics for fixed candidates")
    p = sub.add_parser("fetch", help="Retrieve and validate a public historical ETF snapshot")
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, required=True, help="exclusive end date")
    p.add_argument("--output", type=Path, default=Path("var/snapshots"))
    p.add_argument("--actions", type=Path, help="sourced dividend payment-date supplement")
    p = sub.add_parser("audit-data", help="Offline raw-data, calendar and corporate-action revalidation")
    p.add_argument("--snapshot", type=Path, required=True)
    from .app import register,dispatch
    register(sub)
    args = parser.parse_args()
    try:
        if getattr(args,'operational',False):
            dispatch(args)
            return
        if args.command == "fetch":
            snapshot = fetch(args.output, args.symbol, args.start, args.end, args.actions.read_bytes() if args.actions else b"")
            print(f"Snapshot: {snapshot.resolve()}")
            print("Admission: vendor/calendar checked; engineering-only, not profitability validation.")
            return
        if args.command == "audit-data":
            dataset = load_snapshot(args.snapshot)
            print(f"PASS: {dataset.symbol}, {len(dataset.bars)} sessions; sha256={dataset.sha256}")
            print(f"Admitted corporate actions: {len(dataset.actions)}. Single-vendor and source-verification limitations remain.")
            return
        if args.command == "demo":
            dataset = Dataset(files("quant_research").joinpath("resources/synthetic.csv").read_bytes(), "SYNTHETIC", "synthetic")
        elif args.snapshot:
            if args.symbol or args.actions:
                parser.error("snapshot owns its symbol and actions; omit --symbol/--actions")
            dataset = load_snapshot(args.snapshot)
        else:
            if not args.symbol:
                parser.error("--csv requires --symbol")
            dataset = Dataset.from_path(args.csv, args.symbol, "user_supplied_unverified", args.actions)
        cfg = Config(args.initial_cash, args.allocation, args.fee_bps, args.slippage_bps)
        strategy_cfg = BreakoutConfig(lookback=args.lookback, max_holding_bars=args.max_holding_bars)
        if args.command == "evaluate":
            bundle = evaluate(args.output, dataset, args.split, cfg, strategy_cfg)
        elif args.command == "walk-forward":
            protocol = WalkForwardConfig(args.train_sessions, args.test_sessions, args.gap_sessions, args.min_training_trades)
            bundle = walk_forward(args.output, dataset, cfg, protocol, strategy_cfg,
                                  uncertainty=UncertaintyConfig() if args.uncertainty else None)
        else:
            results = {name: run(dataset.bars, strategy, cfg, actions=dataset.actions)
                       for name, strategy in research_strategies(strategy_cfg).items()}
            bundle = save_bundle(args.output, dataset, results)
    except (ValueError, OSError, DecimalException, sqlite3.Error, subprocess.SubprocessError, KeyError, TypeError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    print(f"Evidence bundle: {bundle.resolve()}")
    print(f"Report: {(bundle / 'report.html').resolve()}")
    print("Status: engineering_only; no statistical profitability claim.")


if __name__ == "__main__":
    main()
