"""The dependency gate catches what it is for and spares what it is not.

Two of CLAUDE.md's non-negotiables were declared and unchecked: stdlib-only,
and the build being network-free. The second had just been WIDENED (#264, from
a flat "no network" that three settled decisions already contradicted), and a
rule that has just been widened is the one most in need of a check, because the
widening is what creates room to drift into.

These tests run against synthetic packages rather than only against this repo,
because this repo passes and so exercises none of the failure paths - which is
the shape of a gate that is green because it is inert.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dependency_gate as gate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _pkg(tmp_path, modules: dict[str, str]) -> Path:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    for name, body in modules.items():
        (pkg / f"{name}.py").write_text(body, encoding="utf-8")
    return pkg


def test_the_live_engine_is_clean():
    """The gate passes on this repo, so a finding is a new one."""
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "dependency_gate.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_clean_package_has_no_findings(tmp_path):
    pkg = _pkg(tmp_path, {
        "db": "from . import schema\nimport json\n",
        "schema": "import datetime\n",
    })
    assert gate.analyse(pkg, build_entry="db", allow={}) == []


# ---- 1. stdlib only ---------------------------------------------------------

def test_it_catches_a_third_party_import(tmp_path):
    pkg = _pkg(tmp_path, {"db": "import requests\n"})
    found = gate.analyse(pkg, build_entry="db", allow={})
    assert any("third-party module 'requests'" in f for f in found)


def test_it_catches_a_third_party_from_import(tmp_path):
    pkg = _pkg(tmp_path, {"db": "from pydantic import BaseModel\n"})
    found = gate.analyse(pkg, build_entry="db", allow={})
    assert any("third-party module 'pydantic'" in f for f in found)


def test_it_spares_intra_package_imports(tmp_path):
    """A sibling module is not a third-party package, however it is spelled."""
    pkg = _pkg(tmp_path, {
        "db": "from . import schema\nfrom .schema import KEYS\nimport vitai\n",
        "schema": "KEYS = ()\n",
    })
    assert gate.analyse(pkg, build_entry="db", allow={}) == []


def test_it_spares_dunder_future(tmp_path):
    pkg = _pkg(tmp_path, {"db": "from __future__ import annotations\n"})
    assert gate.analyse(pkg, build_entry="db", allow={}) == []


# ---- 2. network capability is confined --------------------------------------

def test_it_catches_an_unlisted_network_import(tmp_path):
    pkg = _pkg(tmp_path, {"db": "import socket\n"})
    found = gate.analyse(pkg, build_entry="db", allow={})
    assert any("network-capable socket" in f for f in found)


def test_subprocess_counts_as_network_capable(tmp_path):
    """A shelled-out CLI reaches the network as effectively as a socket."""
    pkg = _pkg(tmp_path, {"db": "import subprocess\n"})
    found = gate.analyse(pkg, build_entry="db", allow={})
    assert any("network-capable subprocess" in f for f in found)


def test_an_allowlisted_module_is_spared(tmp_path):
    pkg = _pkg(tmp_path, {
        "db": "import json\n",
        "infer": "import urllib.request\n",
    })
    found = gate.analyse(pkg, build_entry="db", allow={"infer": "opt-in, fenced"})
    assert found == []


def test_a_stale_allowlist_entry_is_a_finding(tmp_path):
    """A fence recorded where there is no longer a gate reads as protection."""
    pkg = _pkg(tmp_path, {
        "db": "import json\n",
        "infer": "import json\n",
    })
    found = gate.analyse(pkg, build_entry="db", allow={"infer": "opt-in, fenced"})
    assert any("no longer imports anything network-capable" in f for f in found)


def test_an_allowlist_entry_naming_no_module_is_a_finding(tmp_path):
    pkg = _pkg(tmp_path, {"db": "import json\n"})
    found = gate.analyse(pkg, build_entry="db", allow={"ghost": "gone"})
    assert any("not a module in the package" in f for f in found)


# ---- 3. the build closure stays offline -------------------------------------

def test_it_catches_the_build_closure_reaching_capability(tmp_path):
    """The check that carries the rule: confinement alone is not enough."""
    pkg = _pkg(tmp_path, {
        "db": "from . import schema\n",
        "schema": "from . import infer\n",
        "infer": "import urllib.request\n",
    })
    found = gate.analyse(pkg, build_entry="db", allow={"infer": "opt-in, fenced"})
    assert any("build closure reaches 'infer'" in f for f in found)


def test_capability_outside_the_build_closure_is_fine(tmp_path):
    """`vitai infer` may hold it; the build simply must not reach it."""
    pkg = _pkg(tmp_path, {
        "db": "from . import schema\n",
        "schema": "import json\n",
        "api": "from . import db\nfrom . import infer\n",
        "infer": "import urllib.request\n",
    })
    found = gate.analyse(pkg, build_entry="db", allow={"infer": "opt-in, fenced"})
    assert found == [], "api may reach inference; only the build path may not"


def test_transitive_reach_is_caught_not_just_direct(tmp_path):
    pkg = _pkg(tmp_path, {
        "db": "from . import a\n",
        "a": "from . import b\n",
        "b": "from . import infer\n",
        "infer": "import socket\n",
    })
    found = gate.analyse(pkg, build_entry="db", allow={"infer": "opt-in, fenced"})
    assert any("build closure reaches 'infer'" in f for f in found)


def test_a_missing_build_entry_is_a_finding(tmp_path):
    """A gate whose entry point vanished must fail, not silently check nothing."""
    pkg = _pkg(tmp_path, {"schema": "import json\n"})
    found = gate.analyse(pkg, build_entry="db", allow={})
    assert any("build entry 'db' is not a module" in f for f in found)


def test_an_empty_package_is_a_finding(tmp_path):
    """Pointed at nothing, the gate reports rather than passing vacuously."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    assert gate.analyse(pkg, build_entry="db", allow={}) != []


# ---- the live configuration is meaningful -----------------------------------

def test_the_live_allowlist_holds_the_inference_module():
    """If this changes, the fence moved, and that should be a visible edit."""
    assert set(gate.NETWORK_ALLOW) == {"inference"}
    assert gate.NETWORK_ALLOW["inference"].strip()


def test_the_live_build_entry_exists():
    assert (ROOT / "src" / "vitai" / f"{gate.BUILD_ENTRY}.py").exists()
