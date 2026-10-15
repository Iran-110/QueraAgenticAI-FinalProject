# C2j — validate version-reply boundaries before serialization

Pure offline software regression; no model, retrieval or held-out quality claim.
Delivery: [PR69](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/69);
its status is the publication reference. Consume the merged `origin/main`.
The existing recursive detacher now validates the two intake helpers' original
typed inputs before serialization can drop bypassed extra/private state.

- [Prospective protocol](protocol-v1.json) and [16 valid baseline rows](valid-baseline-v1.json)
  were committed at`ee719d3` before implementation.
- [Comparison](comparison-v1.json): the same55 test identities yield29 failures/
  26passes before and55passes after. Of the old failures,27 accepted invalid
  objects and2 rejected later with a different code; they are not29 actions or
  model-quality failures. Ten invalid controls already rejected correctly.
- Every valid prepared turn/full transition retains exact canonical JSON/SHA;
  original input graphs remain unchanged. All39 invalid-boundary controls now
  reject before extraction with the existing content-free InvalidInput code.
- [Verification](verification-v1.json):5479pytest, Ruff357files, three offline
  demos, HTTP/SQLite457/457 including restart. Separate assistant review repeats
  67focused controls without blockers. External XML/full HTTP/demo receipts are
  SHA-bound in verification; no original receipt is overwritten.
- [Behavior and integration limits](../../docs/intake-validation.fa.md).

Only intake.py's two helper boundaries change. Shared validator/contracts,
version extraction, caller authority, tracker dedup/revision and all teammate
modules remain unchanged. This is not authentication, an HTTP exploit fix,
fresh-session recovery or universal internal-boundary validation. Hosted CI,
fresh Windows/browser runs and model/RAG quality are not claimed. Halt, three
uncertain holds, all closed IDs, ledger bytes and19current protected pins stay
unchanged; no paid API call or real credential read.

Reproduce from the repository root:

```bash
uv run pytest tests/test_intake_boundary_validation.py tests/test_intake.py \
  tests/test_approved_reply_intake.py
```
