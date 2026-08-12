import json

import pytest

from experiments.manifest import (
    assert_one_model,
    build_manifest,
    checksum,
    matches,
    read_manifest,
    solc_version,
    submodule_revisions,
    write_manifest,
)


def _fields(**kw):
    base = {
        "policy": "ABHook",
        "policy_params": {"K": 6000, "A": 100},
        "submodules": {"lib/v4-core": "d153b04"},
        "solc": "0.8.30",
        "p0_sqrt_price_x96": 79228162514264337593543950336,
        "l0_basket_usdt": 20_000_000,
        "window": {"start_ms": 0, "end_ms": 86_400_000, "regime": "low"},
        "arbitrageur": {
            "gas_price_wei": 20_000_000_000,
            "gas_estimate": 93838,
            "size_dependent": False,
        },
        "input_checksum": "abc123",
    }
    base.update(kw)
    return base


def test_manifest_carries_every_field_of_equation_9():
    m = build_manifest(**_fields())
    for key in ("C_theta", "D", "P0", "L0", "W", "S", "input_checksum"):
        assert key in m, f"Eq. (9) field {key} missing"


def test_matches_is_true_for_an_identical_configuration(tmp_path):
    m = build_manifest(**_fields())
    path = tmp_path / "run.manifest.json"
    write_manifest(path, m)

    assert matches(path, m)


@pytest.mark.parametrize(
    "field,value",
    [
        (
            "arbitrageur",
            {
                "gas_price_wei": 5_000_000_000,
                "gas_estimate": 93838,
                "size_dependent": False,
            },
        ),
        ("l0_basket_usdt", 1_000_000),
        ("solc", "0.8.29"),
        ("input_checksum", "deadbeef"),
        ("window", {"start_ms": 0, "end_ms": 86_400_000, "regime": "high"}),
    ],
)
def test_matches_is_false_when_any_field_differs(tmp_path, field, value):
    """Any difference means the numbers on disk answer a different question."""
    path = tmp_path / "run.manifest.json"
    write_manifest(path, build_manifest(**_fields()))

    assert not matches(path, build_manifest(**_fields(**{field: value})))


def test_matches_is_false_when_no_manifest_exists(tmp_path):
    assert not matches(tmp_path / "absent.json", build_manifest(**_fields()))


def test_large_integers_survive_the_round_trip(tmp_path):
    """P0 is a Q96 square-root price and exceeds float64 precision."""
    path = tmp_path / "run.manifest.json"
    m = build_manifest(**_fields())
    write_manifest(path, m)

    assert read_manifest(path)["P0"] == 79228162514264337593543950336


def test_checksum_changes_when_the_input_changes(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("1,100\n")
    first = checksum([a])

    a.write_text("1,101\n")
    assert checksum([a]) != first, "a silent data change must be detectable"


def test_checksum_is_order_independent(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("1,100\n")
    b.write_text("1,200\n")

    assert checksum([a, b]) == checksum([b, a])


def test_submodule_revisions_are_recorded():
    """Field D is load-bearing: the policies do not compile against the current
    tip of uniswap-hooks."""
    revisions = submodule_revisions()

    assert revisions, "no submodules found; the manifest would be incomplete"
    assert any("uniswap-hooks" in name for name in revisions)


def test_solc_version_is_read_from_the_build_config():
    assert solc_version() == "0.8.30"


def test_the_gas_limit_is_part_of_the_dependency_field():
    """It changes results: raising it shifted measured gas in the golden window,
    because the limit feeds the 63/64 rule on every call."""
    from experiments.manifest import gas_limit

    m = build_manifest(**_fields())
    assert "gas_limit" in m["D"]
    assert gas_limit() == "20000000000"


def test_source_hash_tracks_our_own_contracts(tmp_path):
    """Field D must move when our Solidity moves.

    Without this a hook edit changes every result while leaving the manifest
    identical, so the resume logic skips the cell and results/ ends up holding
    two different experiments with no way to tell them apart.
    """
    from experiments.manifest import source_hash

    # Cached by directory for the run's sake -- sources cannot change mid-run,
    # and recomputing per cell cost an hour. A test that edits them must say so.
    source_hash.cache_clear()

    src = tmp_path / "src"
    src.mkdir()
    (src / "Hook.sol").write_text("contract A {}")
    before = source_hash(tmp_path)

    (src / "Hook.sol").write_text("contract A { uint x; }")
    source_hash.cache_clear()
    assert source_hash(tmp_path) != before, "an edited contract must change the hash"

    (src / "Hook.sol").write_text("contract A {}")
    source_hash.cache_clear()
    assert source_hash(tmp_path) == before, (
        "the hash must be a pure function of content"
    )

    (src / "Other.sol").write_text("contract B {}")
    source_hash.cache_clear()
    assert source_hash(tmp_path) != before, "a new contract must change the hash"


def test_source_hash_covers_the_harness_not_only_the_policies(tmp_path):
    """The replay harness IS the experiment, so field D must track it too.

    `Replay.t.sol` decides trade sizes, the candle loop, the participation
    decision and what reaches the log. Hashing only `src/` left the same hole
    this field exists to close, one directory over: correcting the fee quote in
    `_feeForSender` moved MEVChargeHook's fee income by 56% and every manifest
    stayed byte-identical, so a rerun would have skipped all 15,552 cells.
    """
    from experiments.manifest import source_hash

    source_hash.cache_clear()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Hook.sol").write_text("contract A {}")
    test = tmp_path / "test"
    test.mkdir()
    (test / "Replay.t.sol").write_text("contract R { uint amountSpecified; }")
    before = source_hash(tmp_path)

    (test / "Replay.t.sol").write_text("contract R { int amountSpecified; }")
    source_hash.cache_clear()
    assert source_hash(tmp_path) != before, "an edited harness must change the hash"


def test_cached_lookups_never_share_a_mutable_object():
    """The cache must not hand the same dict to every caller.

    It did: `submodule_revisions()` returned one shared dict that was embedded
    into every manifest, so a single mutation anywhere would have silently
    rewritten field D of all 4752 of them.
    """
    from experiments.manifest import submodule_revisions

    first = submodule_revisions()
    first["poisoned"] = "x"
    assert "poisoned" not in submodule_revisions(), "callers must not share state"


def _manifest_at(path, revision, mode):
    """A manifest of the shape `build_manifest` writes, minimal but real."""
    path.write_text(
        json.dumps(
            {
                "C_theta": {"policy": "ABHook", "params": {}},
                "D": {"contracts_src": revision, "solc": "0.8.30"},
                "P0": {"extPrice0": 1, "extPrice1": 1},
                "L0": 20_000_000,
                "W": {"pair": "ETH/SHIB", "start_ms": 0, "end_ms": 1},
                "S": {"address_mode": mode},
                "input_checksum": "abc",
            }
        )
    )


def test_one_model_passes_on_a_clean_matrix(tmp_path):
    for i in range(3):
        _manifest_at(tmp_path / f"c{i}.manifest.json", "a7222113bf234b39", "persistent")

    assert assert_one_model(tmp_path) == "a7222113bf234b39"


def test_two_models_in_one_directory_are_refused(tmp_path):
    """The 2026-08-12 defect: `results-uu/matrix/` held the current matrix and
    the one withdrawn by the `r` correction side by side, told apart only by a
    field inside the filename. `load_results()` pooled them and DAHook's median
    read 16,816 against a true 12,240."""
    _manifest_at(tmp_path / "new.manifest.json", "a7222113bf234b39", "persistent")
    _manifest_at(tmp_path / "old.manifest.json", "c5dff798da6e0bff", "fresh")

    with pytest.raises(ValueError, match="different contract"):
        assert_one_model(tmp_path)


def test_the_refusal_names_both_revisions_and_their_counts(tmp_path):
    """A guard that says only "mixed" leaves the reader to work out which half
    to move, and moving the wrong half destroys the current run."""
    for i in range(2):
        _manifest_at(tmp_path / f"n{i}.manifest.json", "aaaa", "persistent")
    _manifest_at(tmp_path / "o0.manifest.json", "bbbb", "fresh")

    with pytest.raises(ValueError) as excinfo:
        assert_one_model(tmp_path)

    message = str(excinfo.value)
    assert "aaaa: 2 cells" in message and "bbbb: 1 cells" in message


def test_an_empty_directory_is_an_error_not_a_pass(tmp_path):
    """Returning "one model" for zero manifests would make the guard vacuous
    exactly when the results are missing."""
    with pytest.raises(FileNotFoundError):
        assert_one_model(tmp_path)
