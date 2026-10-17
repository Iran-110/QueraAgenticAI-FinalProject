# C4m / E2z — development vocabulary and historical rubric identity

Offline software controls only. No paid requests, held-out execution, semantic
quality score or experimental-default promotion.

- [Protocol before changes](protocol-v1.json), commit `fdd6207`.
- [Historical workbench baseline](historical-workbench-baseline-v1.json): all
  seven supported exposed-dev campaigns, complete canonical results. Hashes
  include absolute original input paths; compare using the same paths.
- [Default question baseline](support-vocabulary-baseline-v1.json), committed
  before the optional configuration: seven synthetic states,21 request/message/
  rendered digests. Existing two-question configuration remains immutable.
- [Decisions, integration and owner handoff](../../docs/evaluation-readiness.fa.md).
- [Before/after comparison](comparison-v1.json),
  [final local verification](verification-v1.json),
  [native-copy acceptance and packing diagnostics](native-acceptance-v1.json).
- [Historical rubric verification](historical-workbench-verification-v1.json),
  [vocabulary verification](support-vocabulary-verification-v1.json).

The rubric guard prevents attaching new or altered rubric bytes to an old
registered ID. Regressions initially had14passes/48failures:21wrong-byte
acceptances and27already-rejected cases with different rejection diagnostics.
After the guard,62/62pass. All seven valid complete workbench hashes stay exact.
No historical rubric, fixture, gold, scope or receipt was changed or rescored.

The new optional `config/user-gap-support-dev-v1.json` contains the original two
reviewed user questions plus two approved development code questions.25offline
controls cover explicit-current unknowns, active USER facts/correction, retired
and EVIDENCE facts, canonical version questions, rejection of unregistered
questions and unchanged default bytes. Availability is not a new model choice
or proof of question necessity/usefulness. No held-out-derived names or aliases
are added, and the generic final-test vocabulary is not frozen by this packet.

PR72 contributes exposed-dev retrieval receipts; its original artifacts remain
unchanged. The current receipt script is corrected to use a disposable index
copy and physical hashes of the original. The old receipt's unchanged claim
must not be upgraded from manifest/logical custody to historical physical
custody. See [R4b methods and limits](../r4b_version_ranking/README.md).

Reproduce focused software controls from the repository root, without a key:

```bash
uv run pytest tests/test_support_user_gap_vocabulary.py \
  tests/test_review_rubric_binding.py tests/test_r4b_version_ranking.py
```

On frozen source `5bbb133`,5589development tests pass with one intentional
deselection: `test_split_e1_manifest_covers_every_registered_fixture` opens all
final held-out fixtures. A read guard observed zero held-out read attempts in
the passing run. This is not a claim that the omitted final-artifact test ran.
Ruff364files, three offline demos, HTTP/SQLite457/457 including restart and the
16dev/23turn scripted runner273/273 pass. The team-reported31/533 full split
result was not repeated here. No paid model or final test was run.

The first full local harness additionally blocked the repository `.env`, which
Chroma's settings import tries to load. That prevented native fixture setup:
5348passed,14failed,227errors. The original XML/log and
[preparation correction](test-preparation-amendment-v1.json) are retained; only
that extra environment restriction was removed, with held-out guards and the
explicit deselection preserved. No runtime behavior or assertion was changed
to make this attempt pass. Credential values were not printed or committed.

Fresh native final-hit metadata/order matches all24historical state-arm rows;
one candidate-order difference is retained rather than claiming every native
candidate byte reproduced. Availability remains1/5→3/5 and prior labels yield
off_topic8→5; those labels are Hassan-confirmed development judgments, not an
independent final quality review. C5 stays halted with all three uncertain
holds and every closed experiment identity preserved. Hosted CI/freshWindows/
browser/semantic usefulness results are not claimed.
