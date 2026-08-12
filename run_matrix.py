"""
Run the experiment matrix.

    uv run python run_matrix.py                 # everything, resumable
    uv run python run_matrix.py --workers 8
    uv run python run_matrix.py --pair ETH/SHIB # one pair

Safe to interrupt: completed cells are skipped on the next run, matched by
their reproducibility manifest.

This script produces data only -- `results/summary.csv` and
`results/analysis.csv`. Figures and analysis live in the notebooks under
`analysis/`, so that drawing them never requires re-running the matrix and a
figure can never quietly go stale behind a flag nobody passes.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path

import pandas as pd

from experiments.aggregate import by_regime, paired_against_baseline
from experiments.calibrate_gas import load as load_gas
from experiments.matrix import (
    WINDOWS_PER_TERCILE,
    collect,
    enumerate_runs,
    execute_parallel,
    load_windows,
)
from experiments.stats import analyse

ROOT = Path(__file__).resolve().parent


def available_mb() -> int | None:
    """Free plus inactive memory, in MB. None if it cannot be determined."""
    try:
        out = subprocess.run(
            ["vm_stat"], capture_output=True, text=True, check=True
        ).stdout
    except Exception:  # noqa: BLE001 - Linux or anything else
        try:
            with open("/proc/meminfo") as fh:
                for line in fh:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) // 1024
        except Exception:  # noqa: BLE001
            return None
        return None

    page = 4096
    counts = {}
    for line in out.splitlines():
        if "page size of" in line:
            page = int(line.split("page size of")[1].split()[0])
        elif ":" in line:
            key, _, value = line.partition(":")
            counts[key.strip()] = int(value.strip().rstrip("."))
    free = counts.get("Pages free", 0) + counts.get("Pages inactive", 0)
    return free * page // (1024 * 1024)


def cap_workers_to_memory(requested: int, mb_per_worker: int) -> int:
    """Never start more workers than memory can hold.

    A single replay peaks around 290 MB. It was 4.7 GB before the size search
    started deleting its state snapshots, and ten of those exhausted a machine.
    The guard exists because that failure is silent until the system is already
    thrashing.
    """
    available = available_mb()
    if available is None:
        print("could not read available memory; not capping")
        return requested

    # Leave a quarter of what is free for everything else on the machine.
    affordable = max(1, int(available * 0.75) // mb_per_worker)
    if affordable < requested:
        print(
            f"capping {requested} -> {affordable} workers: "
            f"{available} MB available, {mb_per_worker} MB assumed per worker"
        )
        return affordable
    print(f"{available} MB available; {requested} workers at ~{mb_per_worker} MB each")
    return requested


def forge_writable_paths() -> list[Path]:
    """The read-write entries of `contracts/foundry.toml`'s `fs_permissions`.

    Parsed rather than hardcoded so this cannot drift from the file it is
    protecting.
    """
    import re

    text = (ROOT / "contracts" / "foundry.toml").read_text()
    block = re.search(r"fs_permissions\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not block:
        return []
    entries = re.findall(
        r"access\s*=\s*\"read-write\"\s*,\s*path\s*=\s*\"([^\"]+)\"", block.group(1)
    )
    return [(ROOT / "contracts" / e).resolve() for e in entries]


def assert_forge_can_write(target: Path) -> None:
    """Fail in a second rather than after every cell has failed silently.

    `fs_permissions` is an allowlist. A results directory outside it makes the
    harness abort in `setUp`, which `_worker` records as a per-cell error and
    the sweep dutifully continues -- so an entirely dead run looks like a
    healthy one until the summary is assembled. That happened on 2026-08-11:
    7,776 cells, 26 minutes, zero output.
    """
    allowed = forge_writable_paths()
    target = target.resolve()
    if any(target == a or a in target.parents for a in allowed):
        return
    raise SystemExit(
        f"forge cannot write to {target}.\n"
        f"`fs_permissions` in contracts/foundry.toml allows only:\n"
        + "".join(f"  {a}\n" for a in allowed)
        + "Add an entry there, or choose a directory under one of these."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workers", type=int, default=None, help="processes; default cores-1"
    )
    parser.add_argument(
        "--pair", action="append", help="restrict to a pair; repeatable"
    )
    parser.add_argument(
        "--policy",
        action="append",
        help=(
            "restrict to a policy by name, e.g. MEVChargeHook or MyHook@3000; "
            "repeatable. The summary still covers the whole matrix -- only the "
            "work is restricted."
        ),
    )
    parser.add_argument("--limit", type=int, help="first N cells only, for a smoke run")
    parser.add_argument(
        "--mb-per-worker",
        type=int,
        default=400,
        help="assumed peak RSS per worker; measured worst case is ~290 MB",
    )
    parser.add_argument(
        "--per-tercile",
        type=int,
        default=WINDOWS_PER_TERCILE,
        help="windows drawn from each volatility tercile, per pair",
    )
    parser.add_argument("--no-memory-guard", action="store_true")
    parser.add_argument(
        "--uu-turnover",
        type=float,
        default=1.0,
        help=(
            "retail scale as a multiple of the calibrated kappa (one basket of "
            "uninformed volume per day). 1.0 is the pre-registered headline and "
            "writes to results-uu/; anything else is a second declared "
            "configuration and writes to results-uu/turnover-<multiple>/, so the "
            "two can never merge. See 2026-08-11-informed-share-preregistration.md."
        ),
    )
    parser.add_argument(
        "--uu",
        action="store_true",
        help=(
            "run with uninformed-user flow in `discrete` mode "
            "(2026-08-09-uu-flow-design.md), default lambda, into results-uu/ -- "
            "the arb-only matrix in results/ is never overwritten"
        ),
    )
    args = parser.parse_args()

    # `discrete`, not `share`. Under `share` both directions receive the same
    # potential volume and are thinned by their own P, so near the reference
    # with a symmetric fee the two flows cancel: net displacement per candle is
    # ~0, retail carries almost no inventory cost, and there is nothing toxic
    # for a policy to discriminate against. Measured at the calibrated kappa:
    # `share` leaves the arbitrageur 1.1% of volume with HALF the cells trading
    # zero arbitrage; `discrete` gives 10.9% and no empty cells. It is also the
    # only mode in which retail gas is expressible, because only there does a
    # retail trade have a size.
    uu_mode = "discrete" if args.uu else "off"
    if not args.uu:
        results_root = ROOT / "results"
    elif args.uu_turnover == 1.0:
        results_root = ROOT / "results-uu"
    else:
        # Nested UNDER results-uu/, not beside it. `fs_permissions` in
        # foundry.toml is a path allowlist and covers a subtree, so any future
        # operating point is allowed automatically; a sibling directory is not,
        # and `results-uu-t0.1/` cost a 26-minute run in which all 7,776 cells
        # failed with "the path ... is not allowed to be accessed". The
        # pre-flight check below now catches that in a second instead.
        #
        # Nesting cannot collide with the headline either: `results-uu/*.jsonl`
        # is a non-recursive glob, so the headline's traces and this
        # configuration's never see each other.
        results_root = ROOT / "results-uu" / f"turnover-{args.uu_turnover:g}"
    RESULTS = results_root / "matrix"
    SUMMARY = results_root / "summary.csv"

    assert_forge_can_write(results_root)

    gas = load_gas()
    windows = load_windows(per_tercile=args.per_tercile)

    # `specs` is the whole matrix and stays that way: it is what the summary
    # must describe. Every restriction narrows `selected` only. Filtering the
    # windows here -- which is what `--pair` used to do -- shrank the
    # enumeration itself, so the summary was rebuilt from one pair's specs and
    # the other two thirds vanished from the file every notebook reads.
    specs = enumerate_runs(windows)
    selected = specs

    if args.pair:
        keep = set(args.pair)
        unknown = keep - {s.pair.name for s in specs}
        if unknown:
            parser.error(f"unknown pair: {', '.join(sorted(unknown))}")
        selected = [s for s in selected if s.pair.name in keep]
    if args.policy:
        keep_policies = set(args.policy)
        unknown = keep_policies - {s.policy.name for s in specs}
        if unknown:
            parser.error(f"unknown policy: {', '.join(sorted(unknown))}")
        selected = [s for s in selected if s.policy.name in keep_policies]
    if args.limit:
        selected = selected[: args.limit]

    workers = args.workers or max(1, (os.cpu_count() or 2) - 1)
    if not args.no_memory_guard:
        workers = cap_workers_to_memory(workers, args.mb_per_worker)
    if len(selected) != len(specs):
        print(f"{len(selected)} of {len(specs)} cells selected, {workers} workers")
    else:
        print(f"{len(specs)} cells, {workers} workers")
    if args.uu:
        print(f"retail scale: {args.uu_turnover:g}x the calibrated kappa -> {results_root.name}/")

    started = time.time()

    def progress(done, total, key):
        if done % 25 == 0 or done == total:
            rate = done / max(time.time() - started, 1e-9)
            remaining = (total - done) / rate if rate else 0
            print(
                f"  {done}/{total}  {rate:.1f}/s  ~{remaining / 60:.0f} min left",
                flush=True,
            )

    executed = execute_parallel(
        selected,
        RESULTS,
        gas,
        workers=workers,
        on_progress=progress,
        uu_mode=uu_mode,
        uu_turnover=args.uu_turnover,
    )

    # The summary is rebuilt from every metrics file on disk, not from what this
    # invocation happened to run. Writing the runner's return value meant that
    # `--pair ETH/SHIB` truncated summary.csv to one pair while the other two
    # thirds sat on disk unmentioned -- the file every notebook reads, quietly
    # describing a third of the experiment.
    frame = collect(specs, RESULTS)
    failures = executed[executed["error"].notna()] if "error" in executed else None
    if failures is not None and not failures.empty:
        # A cell that failed in THIS run may still have a stale metrics file
        # from an earlier one, which `collect` already picked up. Concatenating
        # blindly listed it twice: the 2026-08-10 MEVChargeHook run wrote 15,850
        # rows for a 15,552-cell matrix, the excess being exactly its 298
        # failures. The failure is the current truth, so it replaces the row.
        keys = ["policy", "pair", "window_start_ms", "gas_price_wei", "address_mode"]
        if frame.empty:
            # Every cell failed, so there is nothing on disk to deduplicate
            # against. Merging on an empty frame raises KeyError and buries the
            # real problem under a pandas traceback.
            frame = failures
        else:
            stale = frame.merge(
                failures[keys].assign(_failed=True), on=keys, how="left"
            )
            frame = frame[stale["_failed"].isna().to_numpy()]
            frame = pd.concat([frame, failures], ignore_index=True)

    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(SUMMARY, index=False)
    print(f"\nwrote {SUMMARY}: {len(frame)} cells  ({time.time() - started:.0f}s)")

    failed = int(frame["error"].notna().sum()) if "error" in frame else 0
    print(f"errors: {failed}")

    # The conservation check is not a development aid: it caught an int64
    # overflow that would have corrupted every figure silently.
    for column in ("conservation_error_token0", "conservation_error_token1"):
        if column in frame:
            bad = frame[frame[column].abs() > 1e-6]
            print(f"{column}: {len(bad)} violations")
            assert bad.empty, bad[["policy", "pair", "window_start_ms"]].head(20)

    if failed:
        print("\nfirst failures:")
        print(frame[frame["error"].notna()]["error"].head(3).to_string(index=False))

    empty = (
        frame[frame["trade_count"] == 0] if "trade_count" in frame else frame.iloc[:0]
    )
    if len(empty):
        print("\nzero-trade cells by pair (a finding, not a failure):")
        print(empty.groupby("pair").size().to_string())

    print("\nby regime:")
    print(by_regime(frame).round(2).to_string(index=False))

    paired = paired_against_baseline(frame)
    if not paired.empty:
        result = analyse(paired)
        result.to_csv(results_root / "analysis.csv", index=False)
        print("\npre-registered analysis (spec 12.1), FDR-significant rows first:")
        print(result.head(20).round(4).to_string(index=False))

    print("\ndata written. Draw the figures from the notebooks in analysis/.")


if __name__ == "__main__":
    main()
