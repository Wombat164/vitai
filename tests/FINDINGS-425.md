# #425, as measured before the fix (unfinished work in progress)

State: INVESTIGATION COMPLETE, FIX NOT STARTED. `tests/test_pending_classification.py`
encodes the finding and fails against this engine.

## What the issue assumed, and what is actually true

#425 reasons that an importer's rows carry no `recorded_at`, so any guard
asking `_later` classifies every incoming row AMBIGUOUS, and concludes the
correction path is broken. Measured:

- `append_many` **stamps before it guards**. Rows are stamped inside it and
  only then is `_corrections_that_would_not_apply` consulted, so the WRITE path
  works. Verified: a declared correction appended over a held row retires it
  (one live row, 3091); an undeclared restatement leaves two claims and
  resolution picks the later.
- The hole is that **nothing public can ask before the write**, and the private
  function that looks like the answer refuses legal input:

```
UNDECLARED  engine pre-append refusals: none
DECLARED    engine pre-append refusals: ["a correction naming '2030-05-01/mfp-export'
            would retire nothing ... this write is stamped None ..."]
```

So the path the issue points at as the one that works - `supersedes`, a
correction that declares itself - is refused before the append that accepts it.

## The intended answer (not yet implemented)

- **Option 1 is already there and works**: declare the correction with
  `supersedes`. Confirmed by execution.
- **Option 3 is the honest remainder**: an UNDECLARED restatement is not a
  correction to this engine and cannot be classified as one before the write;
  say so rather than let a caller infer it from a clock.
- **Option 2's insight is right, its cost is not**: do not defer the refusal
  until after stamping and leave partial state. The engine knows exactly what
  stamp it will assign (`now_stamp(now, after=high_water)` over this device's
  file), so model it and answer before the write. Same answer, no partial
  write.
- **No contract move expected.** No new field: `supersedes` already is the
  intent field.

## Peer behaviour, still to verify

The guard exists for "a row another writer stamped ahead of this one". Modelling
this device's stamp must not silence that - the last test in the new file is the
control for it and is currently skipped.
