"""Key custody as a product surface (#107).

Synthetic keys only. The load-bearing property is not that a key round-trips -
it is that a MISTYPED phrase is reported as a typo rather than as a different
key, because the alternative is an athlete discovering their backup was bad at
the only moment it matters.
"""

import pytest

from vitai.cli import main
from vitai.conform import drill
from vitai.recovery import (ALPHABET, KEY_BYTES, from_phrase, generate,
                            normalise, rotate, setup,
                            single_point_of_failure, to_phrase)
from vitai.sync import (EnvCustody, FileCustody, MemoryTransport, blob_id,
                        plan_upload)
from helpers_cipher import ToyCipher

KEY = bytes(range(32))


# ---- generated, never derived ----------------------------------------------------

def test_a_key_comes_from_the_system_csprng():
    """Never from a device identifier or anything guessable: a key that can
    be regenerated from something knowable is not a key.

    Asserted against the SOURCE, not against the output. Sixty-four distinct
    32-byte values is a property `random.seed(0)` also has, so counting them
    could not fail for a guessable-but-varying generator - which is exactly
    the thing the rule is about.
    """
    import ast
    from pathlib import Path

    import vitai.recovery as recovery
    tree = ast.parse(Path(recovery.__file__).read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "generate")
    calls = {ast.unparse(n.func) for n in ast.walk(fn)
             if isinstance(n, ast.Call)}
    assert calls == {"secrets.token_bytes"}, calls
    assert "random" not in {n.names[0].name for n in ast.walk(tree)
                            if isinstance(n, ast.Import)}

    keys = {generate() for _ in range(64)}
    assert len(keys) == 64
    assert all(len(k) == KEY_BYTES for k in keys)


def test_generating_a_key_writes_nothing(tmp_path, monkeypatch):
    """The key is returned to be shown once. Anything that persisted it here
    would make the display-once promise false."""
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.rglob("*"))
    generate()
    to_phrase(generate())
    assert set(tmp_path.rglob("*")) == before


def test_the_cli_shows_both_forms_and_writes_neither(tmp_path, capsys,
                                                     monkeypatch):
    """Both, never either. Offering only the manager form makes the manager a
    single point of failure for a decade of health history."""
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    main(["key", "new"])
    out = capsys.readouterr().out
    assert "phrase (for paper)" in out and "password manager" in out
    assert "not be shown again" in out
    assert list(tmp_path.iterdir()) == []


# ---- the phrase is checksummed, and a typo is a typo --------------------------------

def test_a_phrase_round_trips():
    for _ in range(200):
        key = generate()
        assert from_phrase(to_phrase(key)) == (key, "")


def test_no_single_character_typo_can_ever_decode():
    """THE property, and it must be a GUARANTEE rather than a probability.

    The first version of this checksum was four characters of a truncated
    hash, which detects a typo with probability 2^-20 per candidate - so
    across the sixteen-hundred-odd mutations of one phrase, a collision
    producing a VALID DIFFERENT KEY is about one key in six hundred away. A
    review found a concrete one. The code is a BCH checksum now, which
    detects any error of up to four characters in a phrase this length,
    always.

    Checked over the CHECKSUM directly rather than through `from_phrase`, so
    it can be exhaustive without paying for the error-locating scan on every
    one of them.
    """
    from vitai.recovery import _checksum

    body_len = (KEY_BYTES * 8 + 4) // 5
    for key in (KEY, (568).to_bytes(32, "big"), bytes(32), b"\xff" * 32):
        cleaned = normalise(to_phrase(key))
        for i in range(len(cleaned)):
            for candidate in ALPHABET:
                if candidate == cleaned[i]:
                    continue
                typo = cleaned[:i] + candidate + cleaned[i + 1:]
                assert typo[body_len:] != _checksum(typo[:body_len]), (
                    f"a single-character typo at {i} produced a valid phrase")


def test_no_two_character_typo_can_decode_either():
    """The same guarantee covers up to four characters, which is what makes
    transpositions and a swapped group safe as well."""
    import random

    from vitai.recovery import _checksum

    body_len = (KEY_BYTES * 8 + 4) // 5
    cleaned = normalise(to_phrase(KEY))
    rng = random.Random(1)
    for _ in range(20000):
        i, j = rng.sample(range(len(cleaned)), 2)
        a, b = rng.choice(ALPHABET), rng.choice(ALPHABET)
        if a == cleaned[i] or b == cleaned[j]:
            continue
        typo = list(cleaned)
        typo[i], typo[j] = a, b
        typo = "".join(typo)
        assert typo[body_len:] != _checksum(typo[:body_len])


def test_a_typo_is_reported_as_a_typo_and_located():
    """Not as a wrong key. The athlete has to be able to tell a mistyped
    phrase from the wrong phrase entirely, or a fixable transcription reads
    as a lost decade."""
    phrase = to_phrase(KEY)
    for at in (2, 17, 40):
        wrong = "2" if phrase[at] != "2" else "3"
        key, problem = from_phrase(phrase[:at] + wrong + phrase[at + 1:])
        assert key is None
        assert "mistyped" in problem
        assert "the error is in group" in problem, problem


def test_the_confusable_characters_are_read_as_the_athlete_wrote_them():
    """No I, L, O or U can occur, so seeing one is always a misreading of 1,
    1, 0 or V. Rejecting it would be technically correct and unhelpful - the
    athlete wrote what they saw."""
    phrase = to_phrase(KEY)
    muddled = phrase.replace("0", "O").replace("1", "I")
    assert from_phrase(muddled)[0] == KEY


def test_spacing_and_case_do_not_matter():
    phrase = to_phrase(KEY)
    assert from_phrase(phrase.lower())[0] == KEY
    assert from_phrase(phrase.replace("-", " "))[0] == KEY
    assert from_phrase(phrase.replace("-", ""))[0] == KEY
    assert normalise("  ab-cd  ") == "ABCD"


def test_a_phrase_of_the_wrong_length_says_how_far_out_it_is():
    phrase = to_phrase(KEY)
    assert "missing" in from_phrase(phrase[:-5])[1]
    assert "too many" in from_phrase(phrase + "ABCD")[1]
    assert "nothing to read" in from_phrase("")[1]


def test_the_cli_confirms_a_phrase_or_says_what_is_wrong(tmp_path, capsys):
    capsys.readouterr()
    main(["key", "check", to_phrase(KEY)])
    assert "checks out" in capsys.readouterr().out

    phrase = to_phrase(KEY)
    wrong = "2" if phrase[6] != "2" else "3"
    with pytest.raises(SystemExit, match="mistyped"):
        main(["key", "check", phrase[:6] + wrong + phrase[7:]])


def test_the_cli_says_what_is_wrong_with_an_empty_phrase(monkeypatch):
    """It prompts rather than requiring an argument now, so nothing typed is
    a normal thing to happen and gets a normal answer."""
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    with pytest.raises(SystemExit, match="nothing to read"):
        main(["key", "check"])


# ---- setup cannot complete without a drill ----------------------------------------

def test_setup_proves_recovery_before_there_is_anything_to_lose(tmp_path):
    """A restore drill run while the record is empty costs nothing and is the
    only evidence the loop closes."""
    custody = FileCustody(tmp_path / "key")
    got = setup([custody], MemoryTransport(), ToyCipher())
    assert got["ok"] is True
    assert got["phrase"] and got["key"]
    assert custody.verify() is True


def test_setup_fails_when_the_drill_does(tmp_path):
    """Not "warns and proceeds". The drill is the whole point, and a setup
    that completes without one has certified nothing."""
    class Amnesiac(MemoryTransport):
        def get(self, blob_id):
            return None

    got = setup([FileCustody(tmp_path / "key")], Amnesiac(), ToyCipher())
    assert got["ok"] is False
    assert got["key"] is None and got["phrase"] is None
    assert got["problems"]


def test_setup_fails_when_no_backend_accepts_the_key():
    got = setup([EnvCustody("NOTHING", {})], MemoryTransport(), ToyCipher())
    assert got["ok"] is False
    assert any("not a copy" in p or "no custody" in p for p in got["problems"])


def test_a_read_only_backend_counts_only_if_it_holds_this_key(tmp_path):
    """A key already in the environment is a legitimate copy. One holding a
    DIFFERENT key is not, and treating it as one would report two copies
    where there is one."""
    holding = EnvCustody("K", {"K": KEY.hex()})
    got = setup([holding], MemoryTransport(), ToyCipher(), key=KEY)
    assert got["ok"] is True

    stale = EnvCustody("K", {"K": bytes(32).hex()})
    assert setup([stale], MemoryTransport(), ToyCipher(),
                 key=KEY)["ok"] is False


def test_one_copy_of_an_irrecoverable_key_is_a_warning(tmp_path):
    """A manager whose master password is itself unrecorded is one forgotten
    password away from a decade of health history, and the athlete will not
    think of it unless something says so."""
    custody = FileCustody(tmp_path / "key")
    got = setup([custody], MemoryTransport(), ToyCipher())
    assert got["warnings"]
    assert "exactly one place" in got["warnings"][0]


def test_two_copies_earn_no_warning(tmp_path):
    a = FileCustody(tmp_path / "a")
    b = FileCustody(tmp_path / "b")
    assert setup([a, b], MemoryTransport(), ToyCipher())["warnings"] == []


def test_no_backend_at_all_is_the_loudest_case():
    assert "nothing sealed under it" in single_point_of_failure([])[0]


# ---- rotation re-encrypts the whole set -------------------------------------------

def test_rotation_re_encrypts_every_blob_and_removes_the_old_ones():
    """Feasible precisely because the record is a few MB - the payoff for the
    log-not-database decision, showing up somewhere unexpected."""
    transport, cipher = MemoryTransport(), ToyCipher()
    names = ["weight.jsonl", "daily.laptop.jsonl"]
    contents = {n: f"rows for {n}".encode() for n in names}
    for name in names:
        ident, blob = plan_upload(KEY, name, contents[name], cipher)
        transport.put(ident, blob)

    new = generate()
    got = rotate(KEY, new, names, transport, cipher)
    assert got["ok"] and got["rotated"] == 2

    from vitai.sync import plan_download
    for name in names:
        assert transport.get(blob_id(KEY, name)) is None, "old blob remains"
        blob = transport.get(blob_id(new, name))
        assert plan_download(new, name, blob, cipher) == contents[name]


def test_a_half_finished_rotation_leaves_the_old_key_working():
    """Deleting as it goes and then failing halfway leaves a blob set
    encrypted under two keys, one of which the athlete has been told to
    discard."""
    transport, cipher = MemoryTransport(), ToyCipher()
    ident, blob = plan_upload(KEY, "weight.jsonl", b"rows", cipher)
    transport.put(ident, blob)

    got = rotate(KEY, generate(), ["weight.jsonl", "absent.jsonl"],
                 transport, cipher)
    assert got["ok"] is False
    assert transport.get(ident) is not None, "the old blob was deleted anyway"
    assert "keep it until this succeeds" in got["detail"]


def test_rotating_to_the_same_key_is_refused():
    got = rotate(KEY, KEY, ["weight.jsonl"], MemoryTransport(), ToyCipher())
    assert got["ok"] is False and "same as the old" in got["problems"][0]


def test_the_rotated_set_still_passes_a_drill(tmp_path):
    """End to end: rotate, then prove the new key recovers the record."""
    transport, cipher = MemoryTransport(), ToyCipher()
    ident, blob = plan_upload(KEY, "weight.jsonl", b"rows", cipher)
    transport.put(ident, blob)
    new = generate()
    assert rotate(KEY, new, ["weight.jsonl"], transport, cipher)["ok"]

    custody = FileCustody(tmp_path / "key")
    custody.store(new)
    assert drill({"weight.jsonl": b"rows"}, new, cipher, transport,
                 custody)["ok"]


# ---- the engine recommends no vendor -----------------------------------------------

def test_nothing_here_names_a_password_manager():
    """#107 requires any referral relationship disclosed inline at the point
    of recommendation. The simplest way to have nothing to disclose is to
    make no recommendation: the engine describes what a custody backend must
    do and names no product, so convenience cannot nudge toward a paid one.
    """
    from pathlib import Path

    import vitai.recovery as recovery
    import vitai.sync as sync
    for module in (recovery, sync):
        text = Path(module.__file__).read_text().lower()
        for vendor in ("bitwarden", "vaultwarden", "1password", "lastpass",
                       "dashlane", "keepass"):
            assert vendor not in text, f"{module.__name__} names {vendor}"


# ---- what the review of this feature found ------------------------------------------

def test_a_backend_that_accepts_the_key_and_loses_it_is_not_a_copy(tmp_path):
    """`store` not raising was counted as a copy, so a silent no-op reported
    two copies where there was one - and suppressed the single-point-of-
    failure warning, which is the one thing this owes the athlete."""
    class Liar(MemoryTransport):
        def store(self, key):
            pass

        def retrieve(self):
            return bytes(32)

        def verify(self):
            return True

    got = setup([FileCustody(tmp_path / "key"), Liar()], MemoryTransport(),
                ToyCipher())
    assert got["ok"] is False
    assert any("not a copy" in p for p in got["problems"])


def test_rotating_nothing_is_not_success():
    """Reporting success told the athlete to discard the old key while every
    blob was still sealed under it."""
    got = rotate(KEY, generate(), [], MemoryTransport(), ToyCipher())
    assert got["ok"] is False
    assert "keep the old key" in got["problems"][0]


def test_a_transport_that_raises_produces_a_report_not_a_traceback():
    """This is the path whose whole promise is "keep the old key until this
    succeeds", and a crash keeps no promise."""
    class Unreliable(MemoryTransport):
        def put(self, blob_id, blob):
            raise OSError("the disk is full")

    transport, cipher = MemoryTransport(), ToyCipher()
    ident, blob = plan_upload(KEY, "weight.jsonl", b"rows", cipher)
    transport.put(ident, blob)
    broken = Unreliable()
    broken._blobs = transport._blobs
    got = rotate(KEY, generate(), ["weight.jsonl"], broken, cipher)
    assert got["ok"] is False
    assert any("could not be re-encrypted" in p for p in got["problems"])
    assert transport.get(ident) is not None


def test_setup_removes_its_own_drill_blob():
    """It was left in the production transport for ever, to be carried
    through every future rotation or to sit there sealed under a retired
    key."""
    transport = MemoryTransport()
    import tempfile
    from pathlib import Path
    got = setup([FileCustody(Path(tempfile.mkdtemp()) / "key")], transport,
                ToyCipher())
    assert got["ok"] is True
    assert transport.list() == []


def test_a_failed_setup_says_the_key_is_already_on_disk(tmp_path):
    """The athlete got "failed", no phrase, and an undisplayed key file that
    nothing mentioned."""
    class Amnesiac(MemoryTransport):
        def get(self, blob_id):
            return None

    got = setup([FileCustody(tmp_path / "key")], Amnesiac(), ToyCipher())
    assert got["ok"] is False
    assert any("already written" in p for p in got["problems"])


def test_the_cli_reads_the_phrase_from_stdin(monkeypatch, capsys):
    """Passing it as an argument writes the key itself into shell history
    and shows it in `ps` - a poor way to treat a secret in a module whose
    premise is that nobody else can read it."""
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(to_phrase(KEY) + "\n"))
    capsys.readouterr()
    main(["key", "check"])
    assert "checks out" in capsys.readouterr().out


def test_the_cli_says_so_when_a_phrase_arrives_as_an_argument(capsys):
    capsys.readouterr()
    main(["key", "check", to_phrase(KEY)])
    assert "shell history" in capsys.readouterr().err
