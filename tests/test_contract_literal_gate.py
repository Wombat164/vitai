"""The contract-literal gate catches what it is for and spares what it is not.

The gate exists because `CONTRACT_VERSION` moved 23 -> 24 -> 25 in one day and
each move broke the same six assertions in five files - none of which had
anything to do with the change that bumped it. A contract assertion holds that
the read model CARRIES its contract, not that the number is any value.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import contract_literal_gate as gate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _scan(tmp_path, body: str):
    p = tmp_path / "test_sample.py"
    p.write_text(body, encoding="utf-8")
    return gate.scan_file(p)


def test_the_live_test_suite_is_clean():
    """The gate passes on this repo, so a violation is a new one."""
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "contract_literal_gate.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_it_catches_a_subscript_comparison(tmp_path):
    assert _scan(tmp_path, 'def t(meta):\n    assert meta["contract"] == "24"\n')


def test_it_catches_a_sql_read_comparison(tmp_path):
    body = ('def t(con):\n'
            '    assert con.execute("SELECT value FROM meta WHERE key=\'contract\'"'
            ').fetchone()[0] == "25"\n')
    assert _scan(tmp_path, body)


def test_it_catches_a_dict_on_the_far_side_of_a_comparison(tmp_path):
    body = 'def t(meta):\n    assert meta() == {"contract": "24", "policy": "abc"}\n'
    assert _scan(tmp_path, body)


def test_it_spares_a_comparison_against_the_constant(tmp_path):
    body = ('from vitai.db import CONTRACT_VERSION\n'
            'def t(meta):\n    assert meta["contract"] == CONTRACT_VERSION\n')
    assert _scan(tmp_path, body) == []


def test_it_spares_a_fixture_row_that_carries_a_contract_field(tmp_path):
    """The false positive that shaped the rule.

    `emissions` stores `contract` as a FIELD, and its tests build rows naming
    contract "5" and "21" as spoofed payloads - checking that a row arriving
    through the generic append door and naming its own contract is refused.
    Rewriting those to CONTRACT_VERSION would delete the attack the test makes.
    """
    body = ('def t(v):\n'
            '    row = {"date": "2030-05-06", "contract": "5", "surface": "spoofed"}\n'
            '    v.append("emissions", row)\n')
    assert _scan(tmp_path, body) == []


def test_it_spares_an_unrelated_numeric_string(tmp_path):
    body = 'def t():\n    assert reps == "12"\n'
    assert _scan(tmp_path, body) == []
