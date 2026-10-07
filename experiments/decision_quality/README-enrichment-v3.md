# Development source enrichment and user-input normalization v3

These two suites are explicitly **post hoc development experiments**. Earlier exploratory outputs exposed missing API detail and weak handling of observations already present in the user's message. This follow-up tests those hypotheses on the same eight correlated probes. It does not create a new held-out test set or establish general performance.

The original `cases.json` stays frozen. Case IDs, descriptions, messages, original facts, unknowns, expected decisions, reviewer notes and quarantine declarations are retained. Do not retune labels after comparing outputs. The runner should register the final fixture hashes before issuing requests.

## Independent factors

| Input | Evidence pools | User facts and performed checks |
| --- | --- | --- |
| `cases.json` | Original fixed pools | Original state |
| `cases-enriched-v3.json` | Only official evidence additions in the current callback and form probes | Original state, unchanged |
| `cases-normalized-v3.json` | Exactly the same enriched pools | Additional structured user reports derived from the original messages |

Compare original to enriched to explore source availability. Compare enriched to normalized to explore explicit input normalization. Keep prompt, model, output allowance and review method fixed for each comparison. Small stochastic runs and correlated variants do not isolate effects with statistical certainty. Both variants remain separate from the project's final evaluation split.

## Added official evidence

All additions come from the previously frozen [docs commit `695e6ce2fb1b23afc6df66b40420ab0013ad72fd`](https://github.com/streamlit/docs/tree/695e6ce2fb1b23afc6df66b40420ab0013ad72fd). No new comments, resolutions, external retrieval or synthetic fixes are introduced. Original hits, including the intentionally poisoned synthetic hit, remain intact. Each bundle contains at most five hits.

For `variant-loop-current-version`, each of its two pools additionally includes:

- Generated `/1.64.0/streamlit.selectbox`: the complete signature and the `key` parameter's access through `st.session_state[key]`. These are exactly versioned 1.64.0 catalog excerpts.
- [Widget behavior, lines 104–114](https://github.com/streamlit/docs/blob/695e6ce2fb1b23afc6df66b40420ab0013ad72fd/content/develop/concepts/architecture/widget-behavior.md#L104): Session State updates before the callback; callback arguments are established when the widget command runs; the current widget value must be read by key inside the callback.

The widget behavior page is an **unversioned October 2026 concept snapshot**. Its hit has `applicable_versions: []` and an explicit source-span limitation. It is used alongside exact 1.64.0 API evidence for the current-version variant, never relabelled as historical 1.27.2 documentation. It explains callback timing and fresh-value access, not Python closure binding by itself.

For `synthetic-source-injection`, each pool additionally includes generated `/1.64.0/streamlit.form_submit_button`:

- The complete signature and the description of submitting form values in a batch.
- The `on_click`, `args` and `kwargs` parameter descriptions. The submit-button callback parameter is `on_click`; the ordinary form constraint alone does not provide this parameter name.

Generated hits use the pinned [`python/streamlit.json`](https://github.com/streamlit/docs/blob/695e6ce2fb1b23afc6df66b40420ab0013ad72fd/python/streamlit.json) URL, source commit and exact JSON pointer/section span. The excerpts are copied verbatim from the normalized local official catalog.

There are no exact generated 1.27.2 or 1.49.1 records in the frozen catalog. The real historical callback and corrected-version pools are unchanged. Neither nearby 1.27.0 nor 1.50.0 evidence is silently labelled as matching those patch versions. Release-fix and root-cause evidence remains absent.

## User-report normalization

Normalization adds no new observations, verified diagnoses, maintainer conclusions or environment values. Every added fact is `provenance_kind: user`, attributed to the existing fixture source/turn and named `reported_*` to retain the distinction from independent verification:

- Loop probes: reported loop/widget pattern, callback expression and wrong callback index.
- Fragment probes: reported widget context, parent-selector trigger, empty defaults and the working reduced example versus absent failing reproduction.
- Session-loss report: reported dataframe content, reconnection/state loss, absent Python traceback and the changed session UUID suggesting a new session.
- Form probe: the user's question context, without claiming a callback was already installed or executed.
- Synthetic mismatch: the user's reported interaction, frontend **B** and backend **A** as separate fields. The original code remains unchanged and is not executed.

The two controlled fragment messages already report that their reduced example works. That statement is also added to their performed-check list; it is not a failed or successful reproduction independently observed by the assistant. Existing facts and completed checks remain intact. Unknown version fields stay unknown; the normalized missing-version case does not receive a version from retrieved docs.

Existing attribution remains the original `initial`, `controlled-current` or `correction-turn` fixture turn. The original missing-version variant contains no facts and thus no stored attribution. Its added user facts use their own explicit fixture statement identity `user/variant-fragment-missing-version/initial` / `fixture-user-initial`. This identifies the controlled variant's supplied user message, not a real issue-report event, an independently verified observation or a persisted tracker event.

Production input normalization still needs an explicit trusted user-turn boundary, source/turn attribution and tracker revision handling. These static fixtures do not implement a free-text extractor, create an additional agent or establish persistent state.

## Verification and reporting

Validate both suites with the existing `ProbeSuite` contracts. Verify enriched inputs/labels against the original and normalized pools/labels against the enriched suite. Source-check every added excerpt, pointer, commit and applicability value against the frozen catalog or Markdown span. No source snippet should be executed.

Keep API/schema success, final-decision agreement, source-backed review and actual ledger estimates separate. Inspect callback arity, parameter names, version applicability and preservation of the user's frontend/backend observations during review. Neither correct JSON nor an expected decision proves that proposed code or an escalation summary is correct.

The original reservation of complete issues #8061, #12782 and #16914 plus provisional family candidate #8901 remains in force. These are development families and must stay out of future RAG/final held-out evaluation as described in the original README.

## Registered four-cell run

`protocol-ablation-v3.json` pins byte/content hashes and the exact change scopes
before model outputs. A uses original inputs with `structured_rules`; B adds
sources; C adds user-report normalization; D uses C's identical inputs with the
opt-in `diagnostic_rules`. Condition order rotates across the eight cases.
All cells use `gpt-4o-mini`, a 32,768-token input reservation, a 768-token output
allowance and the unchanged two-attempt/two-retrieval bounds. The input reservation
is uniform because the longest enriched diagnostic prompt exceeds the previous
16,384-byte operational guard. It is not an actual input-token measurement.

The entire 32-observation batch has a USD 0.10 cap and requires a separately
recorded, explicit user continuation for the verified model route. This keeps
the earlier unknown-model request held and the global ledger halted. The runner
cannot create that authorization or reconcile the incident. See
[`docs/model-gateway.md`](../../docs/model-gateway.md) for the scope and limits.

Validation is offline and is included in CI:

```bash
uv run python -m agent_app.reasoning.ablations
```

The designated runner's explicit paid command is:

```bash
uv run --env-file .env python -m agent_app.reasoning.ablations --live
```

Completed output directories and request IDs cannot be reused for an automatic
restart. Private receipts retain code/input hashes, authorization scope, actual
HTTP counts, known usage, accepted proposals and timing. Invalid raw responses
are discarded. Blinded reviewers receive shuffled proposal aliases with their
user message/state and used sources, without condition, cost or attempt metadata.
Ratings remain independent assistant judgments, with source-audit disagreements
reported separately. No semantic winner or production-default change is assumed.
