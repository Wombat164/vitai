# Changelog fragments

**Do not edit `CHANGELOG.md` in a pull request.** Add a file here instead.

## Why this exists

Every pull request appended its entry under the same `### Added` or `### Fixed`
heading at the top of `CHANGELOG.md`, so any two open at once conflicted on the
same lines - always additively, always trivially, and always needing a human to
say "keep both".

It happened four times in two days: #339 against #340, #341 against #344, and
#345 against main. Every one was resolved by keeping both entries in landing
order, which is a decision a text file should not need a person for. The cost
is not the minute it takes; it is that a conflict on a merge nobody needs to
think about teaches everyone to resolve conflicts without reading them.

The `## [Unreleased]` section carries the marks of it: several `### Fixed`
headings inside one release block, because appending a new section is easier
than merging into an existing one when the file is contended.

## The convention

One file per change, named `<issue>.<category>.md`:

    changelog.d/342.fixed.md
    changelog.d/171.added.md

`<issue>` is the issue the pull request closes. `<category>` is one of
`added`, `changed`, `deprecated`, `removed`, `fixed`, `security` - the Keep a
Changelog set, because that is the format `CHANGELOG.md` declares.

One issue per pull request is already the rule here, so two branches cannot
name the same file unless they are working the same issue in the same
category - and if they are, the conflict is real and worth having.

The file holds the entry exactly as it should appear, as one or more markdown
list items:

    - **A correction is compared against the line it retires** (#342). Two
      lines could disagree about a field's origin and both survive, because
      nothing compared a superseding line against the one it replaced.

## Between releases, these files ARE the unreleased log

`CHANGELOG.md` is not updated per merge. Read `changelog.d/` for what has
landed since the last release; it is the same information, one file per entry
instead of one contended block.

At release, a maintainer runs

    python scripts/changelog_gate.py --assemble

which folds every fragment into the `## [Unreleased]` section under its
heading, in issue order, and deletes the fragments it consumed. That is one
person, once, with no branch open against them - which is the difference.

`python scripts/changelog_gate.py` on its own checks the fragments and is wired
into CI.
