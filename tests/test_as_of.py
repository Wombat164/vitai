"""The knowledge cutoff: what the record said THEN, not what it says now.

Synthetic data only (public repo). Dates are in 2030 for the same reason the
rest of the suite uses them.

`clocks.py` promised this in its own docstring - telling "what the record said
on 30 July, as we understood it then" apart from "as we understand it now" -
and the record was bitemporal in storage while every evaluation path was
unitemporal. `recorded_at` was stamped rigorously and used only as an ordering
tie-break; nothing ever filtered on it.

The case that motivates it: a month of degraded data whose cause is filed six
weeks later. Under a cutoff inside those six weeks it reads unexplained, and
after it reads explained. Judging a decision and judging it with hindsight are
different questions, and an engine that cannot tell them apart will be trained
toward confident attribution by its own test suite.
"""
from datetime import datetime, timedelta, timezone

import pytest

from vitai.api import Vitai
from vitai.jsonl import known_by, load

UTC = timezone.utc


def at(day, hour=12):
    return datetime(2030, 4, day, hour, tzinfo=UTC)


def stamp(day, hour=12):
    return at(day, hour).isoformat()


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "data").mkdir()

    def write(name, rows):
        import json
        (tmp_path / "data" / f"{name}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return tmp_path, write


# --- the primitive ----------------------------------------------------------

def test_an_unstamped_line_survives_every_cutoff():
    """Absent sorts before present, per the clocks canon. A legacy line has no
    transaction time because it predates the clock, not because it came later,
    and dropping it would empty a legacy corpus rather than reconstruct one."""
    assert known_by({"date": "2030-04-01"}, at(1)) is True


def test_a_line_written_after_the_cutoff_is_not_known():
    assert known_by({"recorded_at": stamp(20)}, at(10)) is False
    assert known_by({"recorded_at": stamp(5)}, at(10)) is True


def test_the_cutoff_is_inclusive_of_its_own_instant():
    assert known_by({"recorded_at": stamp(10)}, at(10)) is True


def test_offsets_compare_as_instants_not_as_text():
    """`+02:00` sorts after `+00:00` as a string no matter which came first."""
    later_wall_earlier_instant = {
        "recorded_at": datetime(2030, 4, 10, 13,
                                tzinfo=timezone(timedelta(hours=2))).isoformat()}
    assert known_by(later_wall_earlier_instant, at(10, 12)) is True


# --- the ordering that is the correctness argument --------------------------

def test_a_correction_written_after_the_cutoff_does_not_retire_its_target(repo):
    """THE reason the filter runs before the supersedes walk. Applying a future
    retraction to a past reconstruction produces a state the record never
    held."""
    root, write = repo
    write("weight", [
        {"date": "2030-04-01", "kg": 80.0, "source": "scale",
         "recorded_at": stamp(1)},
        {"date": "2030-04-01", "kg": 78.0, "source": "scale",
         "recorded_at": stamp(20), "supersedes": "2030-04-01/scale"},
    ])
    then = load(root / "data", "weight", as_of=at(10))
    assert [r["kg"] for r in then] == [80.0], "the correction had not happened yet"

    now = load(root / "data", "weight")
    assert [r["kg"] for r in now] == [78.0]


# --- the motivating case ----------------------------------------------------

def test_a_backdated_explanation_is_absent_before_it_was_filed(repo):
    """A context line appended in April about a February state is valid-time
    February and transaction-time April. Reconstructing March must not see it,
    and reconstructing May must."""
    root, write = repo
    write("context", [{"date": "2030-04-01", "mode": "travel",
                       "facilities": None, "place": None, "source": "athlete",
                       "note": None, "recorded_at": stamp(25)}])

    unexplained = Vitai(root, as_of=at(10)).dataset("context")
    assert unexplained == [], "the cause had not been disclosed yet"

    explained = Vitai(root, as_of=at(28)).dataset("context")
    assert len(explained) == 1 and explained[0]["mode"] == "travel"
    assert explained[0]["date"] == "2030-04-01", "valid time is unchanged"


def test_the_cutoff_reaches_every_dataset_through_one_thread(repo):
    """Threaded at `dataset()`, so resolution, verdicts, safety and the build
    inherit it rather than each remembering."""
    root, write = repo
    write("weight", [{"date": "2030-04-02", "kg": 80.0, "source": "scale",
                      "recorded_at": stamp(22)}])
    write("daily", [{"date": "2030-04-02", "steps": 9000, "source": "watch",
                     "recorded_at": stamp(22)}])
    early = Vitai(root, as_of=at(10)).datasets()
    assert early["weight"] == [] and early["daily"] == []
    late = Vitai(root, as_of=at(25)).datasets()
    assert len(late["weight"]) == 1 and len(late["daily"]) == 1


def test_no_cutoff_means_everything_known_now(repo):
    root, write = repo
    write("weight", [{"date": "2030-04-02", "kg": 80.0, "source": "scale",
                      "recorded_at": stamp(22)}])
    assert len(Vitai(root).dataset("weight")) == 1


# --- the guard --------------------------------------------------------------

def test_a_naive_cutoff_is_refused(repo):
    """It would be read in the local zone, so the same call would return
    different records on two machines."""
    root, _ = repo
    with pytest.raises(ValueError, match="explicit offset"):
        Vitai(root, as_of=datetime(2030, 4, 10, 12))


# ---- #148: the policy the record does not hold ----------------------------

def test_the_digest_moves_when_the_policy_moves():
    """A reconstruction taken under one `vitai.toml` and one taken under
    another are not comparable, and until now nothing said so."""
    from vitai.config import Config, policy_digest
    base = Config(steps_floor=8000)
    assert policy_digest(base) != policy_digest(Config(steps_floor=9000))
    assert policy_digest(base) == policy_digest(Config(steps_floor=8000))


def test_the_digest_ignores_which_machine_is_reading():
    """`device` changes which FILE the engine appends to, not what it says.
    Including it would give two devices reading one record two digests, so
    every cross-device comparison would report a policy change that never
    happened."""
    from vitai.config import Config, policy_digest
    assert (policy_digest(Config(steps_floor=8000, device="watch"))
            == policy_digest(Config(steps_floor=8000, device="laptop")))


def test_the_digest_covers_the_fields_with_no_dated_history():
    """`thresholds.jsonl` overlays five keys. The rate phases, the resolution
    ladder, suppressed metrics, the check tolerance and the intake buffer
    have no dated history at all - which is exactly why they need to be in
    the digest rather than left to the overlay."""
    from vitai.config import THRESHOLD_TYPES, Config, policy_digest
    base = Config()
    for field, value in (("phases", ((100.0, 90.0, 0.5),)),
                         ("source_order", ("scale", "app")),
                         ("precedence", {"kg": ("scale",)}),
                         ("suppressed_metrics", ("kg",)),
                         ("check_tolerance", 0.05),
                         ("intake_buffer_pct", 10.0)):
        assert field not in THRESHOLD_TYPES, f"{field} is overlaid after all"
        moved = policy_digest(Config(**{field: value}))
        assert moved != policy_digest(base), field


def test_the_digest_is_stable_across_equal_configs_built_differently():
    """Canonical serialisation, not dict or dataclass ordering: a digest that
    depended on insertion order would differ between two runs that loaded the
    same toml, and the row would be noise rather than a signal."""
    from vitai.config import Config, policy_digest
    one = Config(precedence={"kg": ("scale", "app"), "steps": ("watch",)})
    two = Config(precedence={"steps": ("watch",), "kg": ("scale", "app")})
    assert policy_digest(one) == policy_digest(two)


# A distinct, valid value per policy field, so each can be shown to move the
# digest ON ITS OWN. A count assertion would have passed a `policy_digest`
# rewritten with a hardcoded field list that went stale, and would have
# survived a field being renamed out of the digest entirely.
MOVED = {
    "phases": ((100.0, 90.0, 0.5),),
    "easy_hr_cap": 150,
    "rhr_baseline": 48,
    "steps_floor": 8000,
    "sleep_floor_h": 7.5,
    "pain_gate": 4,
    "source_order": ("scale", "app"),
    "precedence": {"kg": ("scale",)},
    "suppressed_metrics": ("kg",),
    "nudge_ok": True,
    "check_tolerance": 0.05,
    "intake_buffer_pct": 10.0,
}


def test_every_policy_field_is_actually_consulted():
    """Not a count - a count stays green while a field silently drops out of
    the digest, which is the whole failure this guards. Each field must move
    the digest by itself, and a field added to `Config` without a value here
    fails until somebody classifies it."""
    from dataclasses import fields

    from vitai.config import NOT_POLICY, Config, policy_digest
    covered = [f.name for f in fields(Config) if f.name not in NOT_POLICY]
    assert set(covered) == set(MOVED), (
        "a Config field is unclassified: add it to MOVED if it is policy, or "
        "to NOT_POLICY with a reason if it is a property of the reader")
    assert set(NOT_POLICY) == {"device"}
    base = policy_digest(Config())
    seen = {}
    for name, value in MOVED.items():
        digest = policy_digest(Config(**{name: value}))
        assert digest != base, f"{name} does not reach the digest"
        assert digest not in seen, f"{name} collides with {seen.get(digest)}"
        seen[digest] = name


def test_toml_number_formatting_does_not_move_the_digest():
    """`steps_floor = 8000` and `steps_floor = 8000.0` are the same policy
    and judge identically, and they hashed differently: a formatter
    normalising the toml marked every later reconstruction incomparable with
    every earlier one. Noise in the one signal this row carries."""
    from vitai.config import load_config, policy_digest

    def written(text, tmp):
        tmp.mkdir(parents=True, exist_ok=True)
        (tmp / "vitai.toml").write_text(text, encoding="utf-8")
        return policy_digest(load_config(tmp))

    import tempfile
    from pathlib import Path
    root = Path(tempfile.mkdtemp())
    plain = written("[tripwires]\nsteps_floor = 8000\nsleep_floor_h = 7\n",
                    root / "a")
    floaty = written(
        "[tripwires]\nsteps_floor = 8000.0\nsleep_floor_h = 7.0\n",
        root / "b")
    assert plain == floaty


def test_one_config_governs_a_whole_build(tmp_path, monkeypatch):
    """The digest must describe the config the verdicts were JUDGED under.

    `Vitai.config` re-reads vitai.toml on every access, so the verdicts came
    from one read and the stamp from a later one. Edit the toml between them
    and the read model records an identity claim that is false - which is
    worse than the absence the omitted-row case is careful not to be misread
    as.

    Asserted against what `compute_verdicts` actually received, not against a
    guess at which read wins: the invariant is that they AGREE, however many
    reads the build makes.
    """
    import sqlite3

    from vitai import api
    from vitai.api import Vitai
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    toml = root / "vitai.toml"
    toml.write_text("[tripwires]\nsteps_floor = 8000\n", encoding="utf-8")

    judged = {}
    real = api.compute_verdicts

    def capture(cfg, *a, **kw):
        judged["cfg"] = cfg
        # Every later read of vitai.toml now sees something different.
        toml.write_text("[tripwires]\nsteps_floor = 9000\n", encoding="utf-8")
        return real(cfg, *a, **kw)

    monkeypatch.setattr(api, "compute_verdicts", capture)
    db = Vitai(root).build()
    con = sqlite3.connect(db)
    try:
        stamped = dict(con.execute("SELECT key, value FROM meta").fetchall())
    finally:
        con.close()

    from vitai.config import policy_digest
    assert judged["cfg"].steps_floor == 8000, "premise: the edit landed after"
    assert stamped["policy"] == policy_digest(judged["cfg"])


def test_the_read_model_carries_the_policy_it_was_built_under(tmp_path):
    """The read model IS the recorded reconstruction, so it is where the
    digest has to land."""
    import sqlite3

    from vitai.api import Vitai
    from vitai.cli import main
    root = tmp_path / "content"
    main(["init", str(root)])
    engine = Vitai(root)
    con = sqlite3.connect(engine.build())
    try:
        meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
    finally:
        con.close()
    assert meta["policy"] == engine.policy
    assert meta["contract"] == "18"


def test_a_read_model_built_without_a_policy_omits_the_row(tmp_path):
    """ABSENT rather than a placeholder. A fixed string would read as "policy
    unchanged" across two builds that were judged differently, which is the
    one wrong answer this row exists to prevent.

    Both branches, because asserting only the omission passes against code
    that never writes the row at all.
    """
    import sqlite3

    from vitai.db import build_db

    def meta(**kw):
        db = build_db(tmp_path / str(len(kw)), {}, verdicts=[], **kw)
        con = sqlite3.connect(db)
        try:
            return dict(con.execute("SELECT key, value FROM meta").fetchall())
        finally:
            con.close()

    assert set(meta()) == {"contract"}
    assert meta(policy="abc") == {"contract": "18", "policy": "abc"}
