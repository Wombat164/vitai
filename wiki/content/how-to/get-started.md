---
title: Get started
---

## Install and stamp a content repo

```bash
pip install -e .        # from a clone; PyPI release pending
vitai init ~/health
cd ~/health
git init && git remote add origin <YOUR PRIVATE REMOTE>
```

Keep the content repo **private** - it will hold your real record. If it
syncs through a cloud-drive folder, keep the git repo outside the synced
path (live `.git` dirs corrupt under drive sync); a private git remote is
the sync.

## Fill the narrative files

- `profile.md` - physiology, history, constraints, medical gates.
- `plan.md` - the working plan; section 0 is always the open actions.
- `vitai.toml` - your thresholds: rate-of-loss phases, easy-HR cap,
  resting-HR baseline, steps floor, pain gate.
- `CLAUDE.md` - operating instructions for the AI that picks this up
  (settled decisions, sensitivities). The `vitai-onboard` skill fills all
  of these through an interview plus your uploaded data.

## The weekly loop (about 3 minutes)

```bash
# append the week's lines to data/*.jsonl, then:
vitai validate && vitai build
git add -A && git commit -m "week of $(date +%Y-%m-%d)" && git push
```

Read `derived/weekly.md`: judge on the rate line, walk the tripwires.
Never edit a data line - append a correction with `"supersedes"`.
