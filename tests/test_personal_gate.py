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
