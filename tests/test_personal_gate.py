"""The gate that keeps personal data out of a public repo (#64).

It had caught a real leak, so it worked - but it was a WORD MATCHER guarding a
project whose most sensitive artifacts are numeric. `TOKEN_RE.findall("51.1583")`
returns nothing, so a coordinate, a postcode, a phone number and a house number
were all structurally incapable of being caught.

Everything here is synthetic. The coordinates below are round numbers in the
North Sea and the usernames are invented.
"""

import importlib.util
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parents[1] / "scripts" / "personal_gate.py"
_spec = importlib.util.spec_from_file_location("personal_gate", GATE)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def findings(path: str, text: str) -> list[str]:
    return gate.numeric_findings(Path(path), text)


# ---- what the word matcher could not see ---------------------------------------

def test_a_committed_track_is_seen_at_all():
    """`.gpx` was not in TEXT_EXT, so the gate skipped the file on its suffix
    and never opened it. A GPX is the single most home-locating artifact this
    project produces: a few hundred timestamped coordinates starting at the
    athlete's front door."""
    for ext in (".gpx", ".tcx", ".fit"):
        assert ext in gate.TEXT_EXT, ext


def test_a_coordinate_outside_a_synthetic_path_is_caught():
    found = findings("src/vitai/places.py", "home = 52.00000, 4.00000")
    assert any("coordinate-shaped" in f for f in found)


def test_a_track_file_outside_a_synthetic_path_is_caught():
    gpx = '<gpx><trkpt lat="52.00000" lon="4.00000"/></gpx>'
    assert findings("morning-run.gpx", gpx)


def test_a_named_coordinate_with_few_decimals_is_caught():
    """A file can name coordinates without enough decimal places to trip the
    precision pattern."""
    assert findings("data/where.json", '{"latitude": 52.00, "longitude": 4.00}')


def test_code_that_HANDLES_coordinates_is_not_a_leak():
    """`lat: float` is code; `lat="52.0"` is data. A gate that cannot tell
    them apart fires on its own engine, and a gate that fires on its own
    engine gets switched off - which is the same outcome as no gate."""
    assert findings("src/vitai/route.py", "    lat: float\n    lon: float") == []
    assert findings("src/vitai/route.py", "lat=sum(p.lat for p in seg)") == []


def test_svg_path_data_is_not_geodata():
    """Vector path data is a dense list of decimals and nothing to do with
    places. Its word tokens are still scanned."""
    assert findings("assets/logo.svg", "M 12.34567 8.90123 L 4.56789") == []


# ---- absolute home paths, which no deny list would have caught ------------------

@pytest.mark.parametrize("leak", [
    "PATH = '/home/someone/projects/vitai'",
    "PATH = '/Users/Someone/Projects/vitai'",
    r"PATH = 'C:\Users\Someone\Projects'",
    r"PATH = 'C:\\Users\\Someone\\Projects'",
])
def test_an_absolute_home_path_is_caught(leak):
    """The exact shape of accidental leak the gate exists to stop - it appears
    in tracebacks, notebooks and hard-coded paths - and it slipped through
    because a username is a word nobody thought to deny.

    Structural, so it catches ANY username rather than the ones somebody
    remembered to hash. The escaped form matters too: a Windows path written
    in a Python or JSON literal is a leak in exactly the same way.
    """
    found = findings("src/vitai/config.py", leak)
    assert any("home-directory path" in f for f in found), leak


def test_an_ordinary_relative_path_is_not_a_leak():
    assert findings("src/vitai/config.py",
                    "TRACKS = 'tracks/2026/16044209432.tcx'") == []


# ---- scope -----------------------------------------------------------------------

def test_synthetic_paths_may_carry_coordinates():
    """`tests/` and `examples/` are declared synthetic by repo policy."""
    assert findings("tests/test_route.py", "lat=52.00000") == []
    assert findings("examples/generate_demo.py", "lat = 52.00000") == []


def test_only_the_generators_own_tracks_are_allowed():
    """A track is checked by WHERE IT IS, everywhere - including under the
    synthetic prefixes. Copying a real GPX into a fixture directory is the
    realistic accident, and a blanket exemption for `examples/` waves it
    through."""
    gpx = '<gpx><trkpt lat="52.00000" lon="4.00000"/></gpx>'
    assert findings("examples/demo/tracks/canal-loop-2030-06-16.gpx", gpx) == []
    assert findings("examples/demo/tracks/a-real-run.gpx", gpx)
    assert findings("tests/fixtures/a-real-run.tcx", gpx)


def test_a_binary_track_is_caught_without_reading_it():
    """FIT stores coordinates as binary int32 semicircles, so a real `.fit`
    yields no digits to match and would pass at the repository root. The
    check is on the path, not on what can be read out of the bytes."""
    assert findings("data/2026-07-28.fit", "\x00\x01binary\x02")


def test_a_three_decimal_tcx_coordinate_is_caught():
    """TCX writes `<LatitudeDegrees>51.158</LatitudeDegrees>` - no `=` or `:`
    for the name pattern, and too few decimals for the precision pattern."""
    assert findings("data/where.xml",
                    "<LatitudeDegrees>52.158</LatitudeDegrees>")


def test_the_gate_exempts_itself():
    """It necessarily contains the patterns it hunts for."""
    assert gate.synthetic(Path("scripts/personal_gate.py"))


def test_the_real_repository_passes():
    """The gate must be clean on the tree it guards, or it gets switched off.
    This is also the regression that would catch a future commit adding a real
    track or a hard-coded home path."""
    assert gate.main() == 0


# ---- the coordinate rule had two false-positive classes --------------------

def test_a_doi_is_not_a_place():
    """`10.1007/s10472-011-9241-8` matches the coordinate pattern exactly, and
    a repo that argues from papers produces one every time it cites. Excluded
    structurally rather than by exempting every citation forever."""
    assert not gate._coordinate_shaped(
        "docs/x.md", "Staworko, Chomicki 2012, DOI 10.1007/s10472-011-9241-8")
    assert not gate._coordinate_shaped(
        "docs/x.md", "see 10.14778/1920841.1921008 for the divergence rule")


def test_a_doi_does_not_shelter_a_coordinate_beside_it():
    """The premise. Blanking the DOI must not blank the line."""
    assert gate._coordinate_shaped(
        "docs/x.md", "DOI 10.1145/1265530.1265535 and the start was 51.5074")


def test_the_rule_still_catches_a_place():
    for line in ("home is at 51.5074, -0.1278",
                 "lat 51.15831 lon 4.42631",
                 "the run started at -33.86880"):
        assert gate._coordinate_shaped("docs/x.md", line), line


def test_an_exempt_string_is_scoped_and_re_triggers():
    """Hashed rather than listed by file, for the same reason
    `boundary_gate.py` hashes its own: sparing a FILE silently spares whatever
    is written into it next."""
    import hashlib
    from pathlib import Path
    where, digest = next(iter(gate.EXEMPT_COORD_SHAPED))
    lines = Path(where).read_text(encoding="utf-8").splitlines()
    line = next(row for row in lines
                if hashlib.sha256(" ".join(row.split()).encode()).hexdigest()
                == digest)
    assert not gate._coordinate_shaped(where, line)
    # the same words in another file inherit nothing
    assert gate._coordinate_shaped("docs/elsewhere.md", line)
    # and an edit puts it back in front of a reviewer
    assert gate._coordinate_shaped(where, line + " 51.5074")


def test_every_coordinate_exemption_records_why_and_still_matches():
    """An exemption whose justification is not written down is
    indistinguishable from an oversight, and one whose line no longer exists
    is an exemption nobody can review."""
    import hashlib
    from pathlib import Path
    assert gate.EXEMPT_COORD_SHAPED
    for (where, digest), reason in gate.EXEMPT_COORD_SHAPED.items():
        assert len(reason) > 20, (where, reason)
        live = {hashlib.sha256(" ".join(row.split()).encode()).hexdigest()
                for row in
                Path(where).read_text(encoding="utf-8").splitlines()}
        assert digest in live, f"{where}: no live line hashes to {digest}"
