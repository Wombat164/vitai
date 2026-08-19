#!/usr/bin/env bash
#
# Route D: apply the ALPHA / DOMAIN MODEL partition to vitai's open issues.
#
# The partition, the rule that produced it and the evidence behind it live in
# `docs/route-d-alpha-vs-domain-model.md`. This script is only the applier: it
# holds the verdicts as data so that the document and the labels cannot drift
# apart, and it does nothing else.
#
#   scripts/route_d_labels.sh --dry-run   print every action, change nothing
#   scripts/route_d_labels.sh --apply     create the labels and apply them
#
# It REFUSES to run without one of those flags. Applying a judgement to 77
# issues is an operator decision, and a script that does it when invoked by
# accident is the wrong shape for that decision.
#
# Snapshot: 78 open issues on 2026-08-19, vitai at 9fb0564, contract 54.
# An issue closed since the snapshot is skipped with a note rather than
# labelled, and an issue opened since it is reported as unclassified - a
# partition that silently ignores what it has not seen is worse than one that
# says so.

set -euo pipefail

REPO="${REPO:-Wombat164/vitai}"

# ---------------------------------------------------------------------------
# The verdicts. Rule codes are the ones defined in the document:
#   A1 named consumer  A2 wrong answer  A3 published surface  A4 differentiator
# DOMAIN MODEL is the default: absent a named consumer, an issue is not on the
# alpha path.
# ---------------------------------------------------------------------------

ALPHA=(
  61    # A4  photo capture as a first-class input (loadline#63/#87/#90)
  372   # A1  forward band for weight (loadline#65)
  378   # A4  where an artifact's bytes may travel (loadline#90)
  381   # A1  weight_rate silent exactly when it changes (work order track 1)
  386   # A3  26 fields exempted from coverage (loadline#85, loadline#67)
  393   # A2  four MyFitnessPal activity strings declared in neither spelling
  399   # A3  publish a display symbol (raised by vitai-lens)
  400   # A2  the alias 'pulse' resolves to a field the record will not vouch for
  402   # A1  estimates should carry earned error bands (loadline#79)
  404   # A1  a protocol declares its uncertainty budget (loadline#64, #79)
  419   # A3  the consumer-facing data-model reference is five datasets behind
)

DOMAIN=(
  23 28 30 31 56 62 83 84 85 87 93 95 101 102 106 109 118 119 120 123
  129 130 138 141 144 148 155 156 167 168 169 171 173 174 192 193 194 195 197 198
  203 213 214 215 218 220 224 225 226 227 230 231 232 233 236 237 251 260 261 262
  263 358 361 417 420 436
)

# Deliberately unlabelled: the work order is the instrument, not the subject.
EXCLUDE=(25)

L_ALPHA="ALPHA"
L_DOMAIN="DOMAIN MODEL"
C_ALPHA="0E8A16"       # green: on the path
C_DOMAIN="5319E7"      # purple: good work, off the path
D_ALPHA="On the path to the capture nobody else can do (see docs/route-d-alpha-vs-domain-model.md)"
D_DOMAIN="Good work that is not on the alpha path (see docs/route-d-alpha-vs-domain-model.md)"

# ---------------------------------------------------------------------------

MODE=""
case "${1:-}" in
  --dry-run) MODE="dry" ;;
  --apply)   MODE="apply" ;;
  *)
    cat >&2 <<USAGE
usage: $(basename "$0") --dry-run | --apply

  --dry-run   print every action, change nothing
  --apply     create the two labels and apply them to ${#ALPHA[@]} + ${#DOMAIN[@]} issues

Read docs/route-d-alpha-vs-domain-model.md before --apply.
USAGE
    exit 2
    ;;
esac

command -v gh >/dev/null || { echo "gh is not on PATH" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "gh is not authenticated" >&2; exit 1; }

run() {
  if [ "$MODE" = "dry" ]; then
    printf '  would run: %s\n' "$*"
  else
    "$@"
  fi
}

# --- guard: the verdict lists must be disjoint and free of duplicates -------
dupes=$(printf '%s\n' "${ALPHA[@]}" "${DOMAIN[@]}" "${EXCLUDE[@]}" | sort -n | uniq -d)
if [ -n "$dupes" ]; then
  echo "REFUSING: issue appears in more than one bucket: $dupes" >&2
  exit 1
fi

echo "repo: $REPO"
echo "mode: $MODE"
echo "verdicts: ${#ALPHA[@]} ALPHA, ${#DOMAIN[@]} DOMAIN MODEL, ${#EXCLUDE[@]} excluded"
echo

# --- the labels -------------------------------------------------------------
echo "== labels =="
for spec in "$L_ALPHA|$C_ALPHA|$D_ALPHA" "$L_DOMAIN|$C_DOMAIN|$D_DOMAIN"; do
  IFS='|' read -r name colour desc <<<"$spec"
  if gh label list --repo "$REPO" --limit 200 --json name -q '.[].name' | grep -Fxq "$name"; then
    echo "  '$name' exists, leaving it alone"
  else
    echo "  creating '$name'"
    run gh label create "$name" --repo "$REPO" --color "$colour" --description "$desc"
  fi
done
echo

# --- what is actually open right now ---------------------------------------
OPEN_NOW=$(gh issue list --repo "$REPO" --state open --limit 300 --json number -q '.[].number' | sort -n)

apply_bucket() {
  local label="$1"; shift
  echo "== $label =="
  local n
  for n in "$@"; do
    if ! grep -qx "$n" <<<"$OPEN_NOW"; then
      echo "  #$n closed since the 2026-08-19 snapshot, skipping"
      continue
    fi
    echo "  #$n"
    run gh issue edit "$n" --repo "$REPO" --add-label "$label"
  done
  echo
}

apply_bucket "$L_ALPHA"  "${ALPHA[@]}"
apply_bucket "$L_DOMAIN" "${DOMAIN[@]}"

# --- anything the snapshot never saw ---------------------------------------
KNOWN=$(printf '%s\n' "${ALPHA[@]}" "${DOMAIN[@]}" "${EXCLUDE[@]}" | sort -n)
UNSEEN=$(comm -23 <(printf '%s\n' "$OPEN_NOW") <(printf '%s\n' "$KNOWN") || true)
if [ -n "$UNSEEN" ]; then
  echo "== UNCLASSIFIED: opened since the snapshot, no verdict, nothing applied =="
  for n in $UNSEEN; do
    printf '  #%-5s %s\n' "$n" "$(gh issue view "$n" --repo "$REPO" --json title -q .title)"
  done
  echo
  echo "Classify these by the rule in docs/route-d-alpha-vs-domain-model.md and"
  echo "add them to this script, rather than labelling them by hand: the script"
  echo "is where the document's verdicts are kept honest."
fi

if [ "$MODE" = "dry" ]; then
  echo "dry run: nothing was changed."
fi
