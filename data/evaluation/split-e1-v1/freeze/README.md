# split-e1-v1 freeze (E1/E2)

Frozen by mhg on 2026-10-17, after a human review of each part (assistant-informed:
each card showed the assistant's recommendation). Later changes need new versions;
none of these files is edited in place.

| file | what it freezes |
| --- | --- |
| `rubric-frozen-v1.json` | `e2-rubric-v1`: the base draft and the v1 changes, pinned by hash. Human review only; no LLM judge. |
| `split-manifest-frozen-v1.json` | 31 families (16 dev, 15 test) and the index exclusion. The draft `../split-manifest.json` stays byte-identical. |
| `exposure-frozen-v1.json` | 19 Issues read during core/RAG development; none is in a test family. |
| `corpus-frozen-v1.json` | The evaluation corpus declaration: 1,228 final-index sources and 95 excluded Issues. Its raw SHA becomes `native_scope.corpus_manifest_sha256`. |
| `freeze-record-v1.json` | Pins all of the above plus the dev-only vocabulary, the dev question coverage report and both native registrations. |

The exclusion grows from 90 to 95 Issues: five supplemental core-dev reports from
C4i (4713, 5618, 6415, 7206, 9487). No Issue, comment or outcome is indexed, so
this does not change index content; it makes the exclusion cover every exposed Issue.
13 excluded Issues are old reservations with no family; they stay excluded
conservatively and are not claimed to have been read.

The vocabulary is the one registered list of user-gap questions the core may ask;
it is written from dev cases only. Test-only gap names are never added, so those
test ask branches have no registered question; the final report lists this.

## Rebuild (Hassan)

Use new output names so the current v1/v2 receipts and pins stay intact:

```bash
uv run python scripts/prepare_final_corpus_inputs.py --split-manifest data/evaluation/split-e1-v1/freeze/split-manifest-frozen-v1.json --exclusion-out experiments/final_corpus_v1/exclusion-v2.json
uv run python scripts/build_final_index.py --exclusion experiments/final_corpus_v1/exclusion-v2.json --destination runtime/final-corpus-v2 --receipt experiments/final_corpus_v1/build-receipt-v3.json
```

A local dry run of the first command, plus an in-memory build, accepted the frozen manifest:
95 excluded Issues, 1,228 sources and 1,827 chunks; the snapshot ID changes because
the exclusion is part of the index manifest.

## Still open

Native gold v3 with the five pins from the rebuild, `case.family_id`, origin and a
coverage witness per fixture; the `frozen_final_v1` packet and its preflight; the
code/prompt/model/config freeze; and C5 before any live run.
