# maja: what the record says that is not so

## maja-L-01: "I hit my protein every single day this week"

Journal, 2030-03-11, `kind: claim`.

Her own daily rows for that week include days below 130 g, which is the lower
bound of the band she declared. She is not being dishonest; she is
remembering the days she logged carefully and not the ones she did not.

**Expected behaviour.** The engine observes the record and reports what it
holds. The claim and the rows are both hers and both stay. It must not correct
her, and it must not quietly drop the claim because the numbers disagree with
it.

**What would be wrong.** Any output that treats the journal line as data - for
example counting it toward compliance - or that treats the disagreement as a
finding about her rather than about the record.
