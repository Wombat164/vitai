# otto: what the numbers do

Measured off the committed corpus.

## Sessions

| type | when | how it arrives | count |
| --- | --- | --- | --- |
| row | Tuesday and Thursday, 18:30 | read off the console by eye, photographed, `capture: photo` | 77 |
| cycle | Saturday and Sunday, 09:15 | off the watch, `capture: connector` | 64 |

The ride draw is independent per weekend day rather than one ride per weekend,
so 22 of his 42 weekends carry two.

Every erg row carries an `artifact` reference and every artifact carries a
`captured_at` equal to the session's start plus its duration - he photographs
the console at the end of the piece. No ride carries either. That contrast is
the fixture.

## Weight

Sundays only, fasted, fifteen minutes after he gets up - so the time
varies with the sleep row rather than being pinned, which is what stops the
weigh-in landing before he woke. Regression slope -1.05 kg over the record, which
is slower than the noise on any single weigh-in.

## Measurements

Waist by tape in August, November, February and May: 96.0, 95.0, 94.5, 93.5.
Body fat by DEXA once, on 2030-01-15: 24.8%.

Four tape readings are a trend. One scan is a point. Both are in the record
and the record says which is which.

## Artifacts

77 live plus one removed, so 78 rows. Sizes between 180 kB and 620 kB. Every
one is `image/jpeg` and `kind: photo`.

The images themselves are not in this corpus. Each address is a SHA-256 of a
label rather than of a file - a real content address in shape, stable across
regeneration, with no bytes behind it.
