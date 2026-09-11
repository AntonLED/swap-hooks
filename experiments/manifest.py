"""The reproducibility manifest, E = <C_θ, D, P₀, L₀, W, S> from Eq. (9).

The paper notes that the artifact records only the project structure and that a
full manifest is "a concrete extension needed for artifact-level
reproducibility". Without every field, two runs on the same nominal month and
pair diverge and nobody can tell why.

The manifest doubles as the resume key: a run whose manifest already matches on
disk is skipped, so an interrupted matrix picks up where it stopped.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"


# Cached: these are constants of a run, but they were recomputed for every one
# of the 4752 cells. `git submodule status --recursive` walks the nested
# chainlink tree and costs 738 ms, so the matrix spent about an hour of
# single-threaded time in the parent process just rebuilding the same answer --
# which is why so few workers were ever busy at once.
@cache
def _submodule_revisions_cached(contracts_dir: Path) -> tuple[tuple[str, str], ...]:
    """Pinned commit of every dependency — field `D`.

    These are load-bearing rather than decorative: the current tip of
    `uniswap-hooks` changed `BaseHook`'s constructor, and none of the policies
    compile against it.
    """
    result = subprocess.run(
        ["git", "submodule", "status", "--recursive"],
        cwd=contracts_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    revisions: dict[str, str] = {}
    for line in result.stdout.splitlines():
        parts = line.strip().lstrip("+-U").split()
        if len(parts) >= 2:
            revisions[parts[1]] = parts[0]
    # Immutable, so the cache cannot hand the same mutable object to every
    # caller. It previously did, and every manifest embedded that one dict:
    # a single mutation anywhere would have rewritten field D of all 4752.
    return tuple(sorted(revisions.items()))


def submodule_revisions(contracts_dir: Path = CONTRACTS) -> dict[str, str]:
    """Pinned commit of every dependency -- field `D`. A fresh dict per call."""
    return dict(_submodule_revisions_cached(contracts_dir))


@cache
def _toml_value(key: str, contracts_dir: Path = CONTRACTS) -> str:
    for line in (contracts_dir / "foundry.toml").read_text().splitlines():
        if line.strip().startswith(key):
            return line.split("=", 1)[1].strip().strip('"')
    return "unknown"


def solc_version(contracts_dir: Path = CONTRACTS) -> str:
    return _toml_value("solc_version", contracts_dir)


def gas_limit(contracts_dir: Path = CONTRACTS) -> str:
    """Part of field D: it demonstrably changes results.

    Raising it from u64 max to 2e10 shifted measured gas in the golden window by
    4.5e-6 relative -- small, but real, because the limit feeds the 63/64 rule
    on every call. A dependency revision is not the only thing that makes two
    runs incomparable.
    """
    return _toml_value("gas_limit", contracts_dir)


@cache
def source_hash(contracts_dir: Path = CONTRACTS) -> str:
    """Hash of our own Solidity sources -- the missing half of field `D`.

    `D` recorded submodule revisions, solc and the gas limit, but nothing about
    the contracts in this repository. Editing a hook or ArbMath changes every
    number a run produces while leaving its manifest identical, so the resume
    logic would skip the cell as already-done and the results directory would
    silently mix two different experiments. Eq. (9) is only closed with this.

    `test/` counts as much as `src/`. The harness is not scaffolding around the
    experiment, it *is* the experiment: `Replay.t.sol` decides trade sizes, the
    candle loop, the participation decision and what gets logged. Covering only
    `src/` left exactly the hole this hash exists to close, one directory over
    -- and it was not hypothetical. Correcting the fee quote in
    `_feeForSender` on 2026-08-10 changed MEVChargeHook's fee income by 56%
    while every manifest stayed byte-identical.
    """
    digest = hashlib.sha256()
    for sub in ("src", "test"):
        for path in sorted(Path(contracts_dir / sub).rglob("*.sol")):
            digest.update(path.relative_to(contracts_dir).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def checksum(paths: list[Path]) -> str:
    """Hash of the exact input candles, so a silent data change is detectable."""
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(Path(path).read_bytes())
    return digest.hexdigest()[:16]


def build_manifest(
    *,
    policy: str,
    policy_params: dict,
    submodules: dict[str, str],
    solc: str,
    p0_sqrt_price_x96: int | None,
    l0_basket_usdt: int,
    window: dict,
    arbitrageur: dict,
    input_checksum: str,
) -> dict:
    """Assemble the Eq. (9) fields under their paper names."""
    return {
        "C_theta": {"policy": policy, "params": policy_params},
        "D": {
            "submodules": submodules,
            "solc": solc,
            "gas_limit": gas_limit(),
            "contracts_src": source_hash(),
        },
        "P0": p0_sqrt_price_x96,
        "L0": l0_basket_usdt,
        "W": window,
        "S": arbitrageur,
        "input_checksum": input_checksum,
    }


def write_manifest(path: Path, manifest: dict) -> None:
    Path(path).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def read_manifest(path: Path) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def matches(path: Path, manifest: dict) -> bool:
    """True when a completed run used exactly this configuration.

    Exact equality, deliberately: any difference at all means the numbers on
    disk answer a different question and the run must be redone.
    """
    existing = read_manifest(path)
    return existing is not None and existing == manifest


def models_in(matrix_dir: Path) -> dict[str, int]:
    """Contract source hashes present in a matrix directory, with cell counts."""
    counts: dict[str, int] = {}
    for path in sorted(Path(matrix_dir).glob("*.manifest.json")):
        manifest = read_manifest(path) or {}
        revision = manifest.get("D", {}).get("contracts_src", "unknown")
        counts[revision] = counts.get(revision, 0) + 1
    return counts


def assert_one_model(matrix_dir: Path) -> str:
    """Refuse a matrix directory that holds cells from more than one model.

    Found 2026-08-12. `results-uu/matrix/` had been holding **two** matrices:
    7,776 current cells and 7,776 from the run withdrawn by the `r` correction,
    told apart only by an `address_mode` field inside the filename. So
    `load_results()` on that directory returned 15,552 cells across two different
    models and `DAHook`'s median read 16,816 against the true 12,240 — a 37%
    error, from a call that looks entirely correct.

    Cell counts do not catch this. The notebook that could reach it guarded on
    "fewer cells than expected", and a blended directory has *more*. The source
    hash does catch it, because it is the thing that actually differs.

    Returns the single revision when there is one, so a caller can print what it
    is reading.
    """
    counts = models_in(matrix_dir)
    if not counts:
        raise FileNotFoundError(f"no manifests under {matrix_dir}")
    if len(counts) > 1:
        listed = ", ".join(f"{rev}: {n} cells" for rev, n in sorted(counts.items()))
        raise ValueError(
            f"{matrix_dir} holds cells from {len(counts)} different contract "
            f"revisions ({listed}). These are different models and must not be "
            "pooled; move all but the current one out of the directory."
        )
    return next(iter(counts))
