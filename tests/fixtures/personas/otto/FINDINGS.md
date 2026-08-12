# otto: what this corpus is designed to break

Findings below were exposed by otto@1 (see persona.toml;
docs/persona-doctrine.md requires findings to record the persona version that
exposed them).

## Under test

1. **A photographed value is not a connector value.** Erg sessions carry
   `capture: photo`, a `read_by`, and an `artifact` reference; rides carry
   `capture: connector` and none of those. Expected: the two are
   distinguishable in any output that reports provenance, and the artifact is
   reachable from the row. This is the first record in the corpus with any
   artifacts, so nothing previously exercised either half.

2. **A removal is not data loss.** The photo of 2030-04-16 was deleted because
   a bystander was in it. The row survives, `removed` is true, and `reason`
   says why. Expected: reported as removed with its reason, never as missing,
   and never silently absent. 77 live rows and one removed.

3. **A shared instrument nobody calibrates.** The club ergometer is used by
   several people and its drag factor is wherever the last person left it. Its
   capability row says distance is a proxy for that setting. Expected: figures
   off it are not treated as comparable with figures off any other machine,
   and the proxy qualification travels with any derived number.

4. **One scan is a point, not a trend.** There is exactly one DEXA reading.
   Expected: no direction, no rate, and no comparison with the tape readings,
   which measure a different thing by a different procedure.

5. **Two instruments for one region of the body.** Waist by tape at home, body
   composition by scan at a clinic. Each row names its origin and its
   protocol. Expected: the record can say which is which without a reader
   inferring it from the value.

6. **A claim the record cannot settle.** He says the club erg reads long.
   Every erg row he has came off that machine. Expected: reported as
   untestable from this record rather than as unsupported - the two are
   different statements and only one of them is true here.

7. **A content address with no bytes behind it.** This corpus ships no images.
   Every artifact row carries a well-formed `sha256:` address computed from a
   label. Expected: nothing in the engine requires the bytes to exist in order
   to read, validate, or report the row, and nothing claims to have seen them.
