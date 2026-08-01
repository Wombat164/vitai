# vitai brand

## Verbal identity

### The one-liner

> **The AI health coach you own.**

Use everywhere a single sentence must carry the product: repo description,
package summary, app-store subtitle. Every word is load-bearing: *AI* (LLM-
native, not rules), *health* (broader than fitness: medical, injuries,
nutrition, life), *coach* (it judges and advises, not just tracks), *you own*
(the record is yours, plain text, forever).

### The hero line

> **Your health, on the record.**

Double meaning by design: "on the record" as in verifiable, quotable truth -
and literally *on the record*, the plain-text record you own. Hero subline:

> A record you own. An engine you can audit. A coach that knows your whole
> story.

### The catchphrase

> **Progress you can prove.**

The deterministic engine's promise in three words. Verdicts, not vibes: the
rate line, the adherence count, the zone discipline - computed, rebuildable,
yours. This is also the seam to the future game layer: currency minted only
from proven progress.

### The engineering motto (kept from the founding deployment)

> **Sparse and continuous beats rich and abandoned.**

The operational rule everything obeys: three minutes a week, never skip -
shrink instead.

### The mark narrative

> One stroke, four truths: the **v** of vitai, the **root** of all your
> health data, the **check** of a goal met, the **rise** of a life improving.
> The dot is tomorrow's data point.

### The elevator pitch

Most health apps own your data, hide their logic, and give everyone the same
advice. vitai inverts all three. Your record is plain text in a private git
repo - every workout, weigh-in, injury and doctor's visit, yours forever.
A deterministic engine turns it into numbers you can audit: weight-rate
verdicts, training load, tripwires. And an AI coach reads the whole story -
your history, your constraints, your medical gates, your motivation - and
coaches *you*, not a demographic. Progress you can prove, in a record no
vendor can take away.

### Voice principles (how vitai speaks)

1. **Verdict first.** Lead with the answer; evidence follows. "ON TARGET"
   before the why.
2. **Never moralise.** A red day is arithmetic, not a character flaw. Guilt
   is the relapse mechanism; vitai never deploys it.
3. **The engine wins.** When model and math disagree, say so and side with
   the math. No hedging, no invented numbers.
4. **Respect settled decisions.** Re-litigating the athlete's evidenced
   choices is a voice violation, not diligence.
5. **Plain words.** kg, weeks, sessions. Jargon only where it earns its
   keep (CTL/TSB for athletes who asked).

### Naming system

- **vitai** - the platform: record + engine + coach. Always lowercase.
- **goalden** - reserved name for the game layer (casual F2P where the only
  pay2win currency is your real, engine-verified goal attainment). Teaser
  lines banked for later: "Earn it by living it." / "The grind is outside."
- **loadline** - the client application: browsers on desktop, Capacitor on
  Android and iOS. A CLIENT of vitai, never a replacement; the engine stays
  general and MIT, and other clients could exist. Always lowercase in prose.

  Load is the central word in training (training load, load management,
  progressive overload), and a loadline is the mark on a hull showing the
  maximum safe loading depth. So it names both the quantity the engine
  computes and the limit it declines to program past. Chosen from gym and
  nautical vocabulary on purpose: a name that never invites a medical reading
  is a name that never has to answer for one.

## The mark (master: `vitai-mark.svg`)

One continuous stroke - baseline stub, deep notch, tall rise - plus a detached
dot floating above the peak. Four deliberate readings, all true at once:

1. **v** - the initial of vitai.
2. **Root sign** - the root of all your health data (the record underneath
   everything).
3. **Check mark** - goals achieved (the seam to the goal/game layer).
4. **Rising graph** - the ascending arm plus the dot as the next data point:
   health improving. The dot is also the "i" dot and the AI spark.

Geometry (viewBox 64): path `M6 26 H16 L27 52 L40 8`, stroke 7, round
caps/joins, gradient teal->lime along x 24->42 (crossover on the ascending
arm; the whole left arm stays teal). Dot at (52,9) r5, solid lime, ABOVE the
peak's height so the trajectory reads upward. The lockup embeds the exact
same geometry translated (+8,+14) - never redraw it by eye.

Keep the silhouette: no extra segments (a post-peak "shoulder" was tried and
reviewed away - it killed both the v-reading and 24px legibility). The mark
must stay distinctive at 24px; verify with a NEAREST-upscale of a 24px render.

## Palette

| Role | Hex |
|---|---|
| Teal (vitality start) | `#0EA5A0` |
| Lime (vitality end / dot / "i") | `#84CC16` |
| Ink (wordmark "vit") | `#0F172A` |
| Light background | `#F8FAF9` |
| Social-card outer tint | `#DDEEE2` |

## Wordmark

Lowercase `vitai`, Outfit SemiBold (600), 44px master size, letter-spacing 1.
"vit" in ink; the AI seam is per-letter solid color: **"a" teal, "i" lime**
(quantized gradient endpoints).

WHY solid, not a gradient: outlined glyph paths each carry their own
translate/scale transform, so a shared `userSpaceOnUse` gradient resolves in
glyph-local coordinates and produces per-letter color banding (verified in
render; browsers do the same). Do not reintroduce a gradient across outlined
text.

## Variants

- **Monochrome** (`vitai-mark-mono.svg`): single file using `currentColor` -
  serves black, white, and any grey by context/CSS color. Use for print,
  engraving, favicons in mono contexts, and anywhere color is unavailable.
- **Greyscale**: the color mark degrades safely - teal (~luma 119) and lime
  (~162) stay distinct, so the gradient reads as a dark-to-light ramp
  (verified render: `vitai-mark-greyscale.png`).
- **Unknown backgrounds - the halo**: `vitai-lockup.svg` carries a faint
  light glow-outline behind the ink glyphs (a `<use>` of the `#vit-ink`
  group: stroke `#F8FAF9` width 40 glyph-units, opacity 0.5, 1.2 blur,
  painted underneath). Invisible on light backgrounds; on dark ones "vit"
  reads as a fine ghost outline instead of vanishing. Where the background
  IS known to be dark, prefer the true dark lockup. In markdown that can
  theme-switch (GitHub README), use `<picture>` with
  `prefers-color-scheme: dark` -> `vitai-lockup-dark.svg`.
  NOTE: the halo is a post-outline addition - after re-outlining the text,
  re-add the `<use>` + `#halo` filter block (see git history of
  `vitai-lockup.svg`).
- **Dark mode** (`vitai-lockup-dark.svg`, source `vitai-lockup-dark.text.svg`):
  ink swaps `#0F172A` -> `#F1F5F9`; teal/lime accents and the mark are
  unchanged (both hold on dark). Reference dark background `#0B1220`.
  The dark lockup is generated from the light one by that single fill swap -
  keep it that way (sed, not a redraw).
- **Alt palettes** (`vitai-alt-palettes.svg`, preview sheet, NOT shipped
  identity): `ember` `#F43F5E`->`#F59E0B` (energy/sunrise) and `night`
  `#6366F1`->`#22D3EE` (clinical/dark-first). Canonical stays vitality
  teal->lime; alts are reserved for sub-brands (e.g. the future game layer)
  or special contexts - never mix palettes in one surface.

## Files

| File | Role |
|---|---|
| `vitai-mark.svg` | master mark (favicon/app-icon source) |
| `vitai-wordmark.svg` / `vitai-lockup.svg` | SHIPPED, text outlined to paths (portable everywhere) |
| `vitai-wordmark.text.svg` / `vitai-lockup.text.svg` | live-text sources - edit THESE, then re-outline |
| `vitai-social.png` | 1280x640 GitHub social preview |
| `vitai-mark-mono.svg` | monochrome mark (`currentColor`) |
| `vitai-lockup-dark.svg` (+ `.text.svg`) | dark-mode lockup |
| `vitai-alt-palettes.svg` | alt-palette preview sheet (internal) |
| `Outfit-600.ttf` | the outlining face (fontsource static) |

## Regenerate

```bash
SKILL=~/.claude/skills/brand-cycle
cp vitai-lockup.text.svg vitai-lockup.svg
uv run --with fonttools python $SKILL/scripts/outline_text.py --svg vitai-lockup.svg \
    --font "outfit=Outfit-600.ttf" --font "inter=Outfit-600.ttf"
uv run --with cairosvg python $SKILL/scripts/render.py vitai-lockup.svg vitai-lockup.png -W 512 --bg "#F8FAF9"
uv run --with cairosvg,pillow,numpy python $SKILL/scripts/social_card.py \
    --lockup vitai-lockup.svg --out vitai-social.png --bg-inner "#F8FAF9" --bg-outer "#DDEEE2"
```

Text changes require re-outlining (paths do not reflow). If glyph positions
change, recompute advance widths with fonttools (see git history) - the
per-letter `<text>` x positions are real Outfit metrics, not eyeballed.

GitHub social preview has NO API: upload `vitai-social.png` manually in repo
Settings -> General -> Social preview.

## Changelog

- 2026-07-28: founded. v1 had a post-peak shoulder notch and a lime-dominant
  gradient; two-perspective review (design + technical) drove the simplified
  silhouette, teal rebalance, per-letter wordmark accent, and outlined text.
