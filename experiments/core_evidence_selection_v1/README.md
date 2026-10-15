# C4k/E2x — offline evidence-selection controls and read-only C5 review

**No API calls, default promotion, semantic-quality or held-out claim.**

- [Protocol before implementation](protocol-v1.json), commit `2348eb8`.
- [Original16 default context/messages/render digests](default-baseline-v1.json).
- [Post-hoc exposed-dev failure inventory](failure-inventory-v1.json):12 traceable
  observations and8 regression groups, not oracle input to the selection helpers.
- [Advisory method registered before its implementation](selection-method-v1.json).
- [Original first replay](first-replay-v1.json) and
  [explicit preflight/test-preparation amendment](preflight-amendment-v1.json).
- [Corrected replay V2](replay-v2.json):62/62 checks,16 byte-identical defaults,
  whole-source partitions,64 actual engine normal/repair/refinement contexts.
- [Three-incident read-only cost audit](c5-readonly-audit-v1.json),
  [audit script](c5-readonly-audit-v1.py),
  [Persian cost interpretation](c5-readonly-report.fa.md):36/36 local custody
  checks; original ledger unchanged; costs still uncertain and halt retained.
- [Behavior, integration and limitations](../../docs/evidence-selection.fa.md).
- [Local verification](verification-v1.json):5344pytest, Ruff352files, three
  offline demos and [HTTP/SQLite457/457](http-sqlite-v1.json). Separate assistant
  repeated110targeted tests and reviewed fixed P2s; no independent human score,
  new browser/Windows run or hosted-CI success is claimed.

Source code with complete sections/advisory/replay is `7e20cf4`; the separate C5
packet is `245eaf8`. Runtime/default factories and teammate modules are unchanged.
All new selection is opt-in and all reported projections are authored offline.
Delivery is [PR #65](https://github.com/Iran-110/QueraAgenticAI-FinalProject/pull/65),
merged to main as `efaf02a` after final local verification and separate review:
[merge receipt](merge-review-v1.json). Hosted CI remains billing-blocked, not passing.

Ten retained claim plans include7 original finals and3 binding rejections.21 raw
claim attempts were never retained and cannot be reconstructed. All7 valid plans
project structurally, including the original93-character canonical question;
their median draft grows1459→5073characters. The21 unavailable claim outputs
comprise20 representation rejections and one provider failure, not21 proven JSON
syntax errors. Enum's sole retained guide final
grows1459→5962 and includes its omitted module body/edit-reload span. This is NOT
an improved model choice, shorter answer, useful fix or semantic-accuracy score.
Complete but irrelevant text and sibling/cross-source caveat omissions remain
possible. Shortlist lexical scores are advisory and human usefulness stays null.

All prior corpus/index/exclusions, fixtures/gold/manifests, model receipts and
closed identities remain untouched. The answer-linked guide stays fixture-only.
C5 remains unresolved; no reserve/settle/release or live grant is created here.

Reproduce from repository root with a fresh output path:

```bash
uv run pytest tests/test_claim_sections.py tests/test_evidence_selection.py \
  tests/test_evidence_selection_replay.py
uv run python -m agent_app.testing.evidence_selection_replay \
  --output /tmp/evidence-selection-new.json
```

The cost script reads the designated private local artifacts and ledger only;
it is intentionally not a provider endpoint or portable live runner.
