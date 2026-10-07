# Core decision-quality development probes

These eight preregistered probes test the current core with fixed evidence pools. They are development material, not the project's formal 15-dev / 15-test split, a final benchmark, or a measurement of RAG relevance. Three first-body reports anchor the set; their variants are correlated rather than independent cases.

The case definitions were written before running a model on them. Keep this version intact when comparing prompts or policies. Add a new fixture version if expectations or inputs change after inspecting results, and distinguish that exploratory set in the report.

## Sources and provenance

- GitHub first-body snapshot: 2026-10-06, fetched earlier outside this repository. Only symptoms, supplied code and reported environment/diagnostic observations are paraphrased here. Comments, resolutions, proposed workarounds, reporter root-cause hypotheses and closure status do not supply labels.
- Reports: [#8061](https://github.com/streamlit/streamlit/issues/8061), [#12782](https://github.com/streamlit/streamlit/issues/12782), [#16914](https://github.com/streamlit/streamlit/issues/16914). Their original creation times and URLs appear in the JSON. The input does not contain author accounts, emails or full threads.
- Official docs: frozen [commit `695e6ce2fb1b23afc6df66b40420ab0013ad72fd`](https://github.com/streamlit/docs/tree/695e6ce2fb1b23afc6df66b40420ab0013ad72fd), committed 2026-10-01. Every official evidence hit includes a pinned file URL, commit and source span. Generated API spans identify a version-specific JSON pointer and normalized parameter/behavior section.
- The Session State concept excerpt is Markdown line 186 in the 2026 snapshot. It has no version-specific applicability claim. It explains a new connection losing state but cannot establish the cause of a historical dataframe report.
- Synthetic material uses an explicit synthetic source ID and `example.org` URL. It is never assigned official provenance. The injection probe also retains the clean official form constraint.

The older callback report states 1.27.2 while the available API docstring is 1.27.0. This deliberate uncertainty allows a cautious answer, question or escalation. It does not prove behavior on a patch version or a historical fix. The controlled 1.64.0 callback variant instead supplies matching API metadata. Similarly, an alleged regression remains a reporter observation, not a confirmed root cause or fix label.

## Probe inventory

| Probe | Type | Intended distinction |
| --- | --- | --- |
| `real-loop-callback` | Real report #8061 | Visible callback closure pattern with a nearby historical API version |
| `variant-loop-current-version` | Controlled #8061 variant | Matching 1.64.0 callback evidence and a concrete binding suggestion |
| `real-fragment-default-partial-repro` | Real report #12782 | A working reduced example is not a failing minimal reproduction |
| `variant-fragment-missing-version` | Controlled #12782 variant | Source metadata must not fill missing user version facts |
| `variant-fragment-version-correction` | Controlled #12782 variant | Active 1.49.1 correction takes priority over superseded 1.50.0 and mismatched retrieval |
| `real-dataframe-session-loss` | Real report #16914 | Known session-loss consequence differs from an unconfirmed cause; unrelated form evidence adds no diagnosis |
| `synthetic-source-injection` | Synthetic | Retrieved authority claims cannot approve or execute a case change |
| `synthetic-exhausted-evidence` | Synthetic | Complete supplied facts and exhausted sources call for proposed escalation rather than invented fixes or repeated questions |

Each probe contains two explicitly fixed evidence bundles. A first refinement reaches the second pool; there is no implicit access to a complete corpus. Empty second pools make the source boundary explicit. There is no tracker mutation, reproduction execution or live retrieval in these fixtures.

## Review and comparison

`case_state` and `bundles` use the project's existing `CaseState` and `EvidenceBundle` contracts. `expectations.acceptable_decisions` concerns the final result, after any bounded retrieval refinement. An `error` or exhausted attempt allowance is not a successful decision merely because malformed output was rejected.

Required/forbidden terms and expectation flags are reviewer aids, not automatic measures of factuality, useful questions or grounded claims. A keyword can appear in a denial, and a good explanation can use different wording. Review the actual proposed answer, question or escalation against the linked source and the supplied active facts. Check claim support, version applicability, uncertainty, question value, already completed checks and any invented authority separately. Record disagreements rather than silently retuning labels.

Report automatic final-decision agreement, validation/safety failures, retrieval/model attempts and ledger-estimated cost separately. Keep real-report results separate from controlled and synthetic stress results. With three real anchors and one small run per configuration, comparisons are exploratory and cannot establish a general model-quality improvement or justify another agent on their own.

Live experiments use the existing gateway and durable runner ledger. They need a separately bounded experiment budget; routine fixture and harness tests remain offline. No key, ledger, raw response or original dataset belongs in this directory.

## Registered run

`protocol.json` locks the exact fixture hash, model, policies, token limits and USD 0.16 cap before the first comparison request. The baseline includes the common fact-authority clarification and runtime fixes; it is not an unchanged-main comparison. Policy order rotates across cases. Provider sampling defaults are shared, with one pass per case/policy and no claim of deterministic model output.

Validate without a key or paid request:

```bash
uv run --no-sync python -m agent_app.reasoning.experiments
```

Only the designated ledger runner, after explicit authorization for the registered batch, executes:

```bash
uv run --no-sync --env-file .env python -m agent_app.reasoning.experiments --live
```

The runner uses the existing ledger rather than creating or resetting one. At pinned prices each request reserves USD 0.00321024; at most 48 requests across 24 observations would reserve USD 0.15409152. Actual known usage replaces a reservation before output validation. The experiment checks its remaining cap before every attempt, including repairs. Any pending/uncertain accounting stops the entire batch, with no automatic replay.

Private start receipts, validated proposals for qualitative review, safe attempt diagnostics and cost records are saved under ignored `runtime/decision-quality/<experiment-id>` with restricted permissions. Invalid raw responses, provider bodies and credentials are never retained. An existing directory prevents automatic restart; request IDs also remain stable across workflow hints. The separate experiment cap assumes one sequential designated runner; the atomic shared ledger still enforces its own total limit. Independent laptop ledgers cannot coordinate team spending.

Automatic acceptance and allowed-decision agreement are reported separately from source-backed semantic review. The public report uses aggregate counts and paraphrased findings. Independent review here is assisted qualitative review rather than a human expert benchmark.

## Quarantine for future retrieval and final evaluation

`reserved_issue_ids` reserves #8061, #12782 and #16914 plus the conservatively linked family candidate #8901. Exclude their complete first bodies, comments, outcomes and confirmed duplicate families from future RAG and final held-out evaluation. Variants of an anchor remain in that anchor's development family.

The local family-review catalog links #16914 to #8901. A link does not prove a duplicate, so #8901 is provisionally quarantined until a reviewer resolves the relationship. Other linked/duplicate family members must be reviewed and excluded before claiming leak-free evaluation. This JSON is a reservation declaration; enforcement in corpus construction remains the data/evaluation owners' work.
