# Fresh synthetic decision-guard development probes v4

`cases-guards-v4.json` registers nine newly authored synthetic support messages,
fixed source pools and reviewer expectations before any new model outputs. The
scenarios follow failure mechanisms identified during earlier development, so
they are **post hoc synthetic development probes**, not a held-out benchmark or
an estimate of real user performance. They do not reuse real report bodies or
their outcomes. The stale-argument and correct-key cases deliberately share a
mechanism and should not be counted as independent observations.

No final evaluation cases, issue comments, maintainer resolutions or previous
accepted model outputs were used to author these inputs. Existing fixtures and
their labels remain unchanged. The runner must pin this file's final hash before
requests and keep expected decisions and reviewer notes outside model input.

## Registered scenarios and reviewer aids

| Probe suffix | Final decision aid | Main distinction to inspect |
| --- | --- | --- |
| `own-widget-stale-args` | Answer | Value in `args` is established at construction; passing a key and reading inside the callback must preserve handler arity. There is no loop closure. |
| `own-widget-pass-key-control` | Answer | The supplied key/read-inside pattern is already correct. Do not change it into construction-time value passing or invent a reported failure. |
| `form-submit-exact-parameter` | Answer | Exact 1.64.0 `form_submit_button` evidence supplies `on_click`, with a handler that reads the keyed submitted value. The draft has not been executed. |
| `missing-widget-helper` | Ask | The affected widget is hidden in a named custom helper. Its implementation is genuinely absent, while environment details are already supplied. |
| `known-environment-callback-display` | Answer | The documented callback prefix explains output position and temporary lifetime. Version, browser and console information do not need to be requested again. |
| `unknown-installed-version` | Ask | The installed Streamlit version is explicitly unknown. Retrieved 1.64.0 API metadata cannot become an installed-version fact. |
| `corrected-version-working-reduction` | Ask | Active 1.64.0 supersedes the prior 1.63.0 report. Preserve the already working isolated example and request the genuinely absent failing application path. |
| `reproduced-front-back-mismatch` | Escalate | Complete callback code already passes a key and reads inside invocation. Preserve reported frontend **Lima** versus backend **Oslo** and acknowledge that the sources supply no cause or fix. |
| `previous-value-snapshot-control` | Answer | The user deliberately wants the construction-time value in `args` as an old-value snapshot, while reading the current value inside the callback. Preserve that intent. |

These are review aids rather than keyword grading rules. `required_terms` and
`forbidden_terms` are empty. A decision matching the table does not prove that
the response is useful, source-backed or technically correct. Review handler
arity, value-read timing, exact parameter names, preserved observations and the
purpose of any follow-up question. The engine may use its existing bounded
retrieval refinement before the final decision; refinement is not an additional
expected final decision.

The two ask cases with missing implementation distinguish a truly absent helper
or failing path from facts already supplied. A fresh version question is valid
only in the unknown-version probe. The mismatch remains a synthetic user report
and must not be presented as an executed reproduction or confirmed Streamlit
defect.

The additional old-value snapshot control was registered before outputs. A
construction-time argument is not inherently an error: it is unsuitable when
the user needs the newly changed value through that argument, but can be the
explicitly intended previous-value snapshot. This case is independently written
and complements the two fresh-value controls; the related mechanisms still do
not establish statistical independence.

## Registered caller requirements

`requirements-guards-v4.json` is a separate trusted caller input keyed by probe
ID. Each entry binds one `case_id` and `case_revision` to a canonical question
catalog and a `require_fresh_widget_value` intent flag. It is not retrieved
evidence, model output or an oracle naming the expected decision.

Question catalogs contain only genuinely missing user details:

- `missing-widget-helper`: the absent `draw_choice_panel` implementation and
  relevant surrounding region-selector code.
- `unknown-installed-version`: the installed Streamlit version that the user
  explicitly has not checked.
- `corrected-version-working-reduction`: the missing options-builder/failing
  full-app path, or a minimal failing example containing that path.

Canonical English questions are fixed before outputs. All target names occur in
the corresponding supplied `unknowns`. Installed version, browser, completed
checks, complete supplied code and already reported backend/frontend values do
not become question targets. Source gaps and missing maintainer diagnoses are
not user-information targets.

The other catalogs are empty. An empty catalog registers no clarification for
this experiment; it does **not** assert that every possible user detail is known
or that clarification could never help. Caller curation constrains the model's
available questions and may prevent useful questions outside the catalog. The
comparison must disclose this constraint rather than treating it as automatic
understanding of arbitrary user messages.

The fresh-value flag is true only for `own-widget-stale-args` and
`own-widget-pass-key-control`, where the caller specifically requires the newly
selected value. It is false for the deliberate `previous-value-snapshot-control`
and for tasks about callback parameter names, display position, missing code,
environment or support-report routing. This flag scopes a guard to caller intent;
it is not a blanket prohibition on Session State expressions in callback
arguments or a guarantee that unchecked code is correct.

These catalogs are hand-authored development fixtures. They do not implement a
free-text production extractor, infer user authorization from evidence, grant
tool/action approval or establish durable tracker state. Only trusted caller
inputs may provide them, and their case/revision binding must remain valid.
Record the requirements-file hash separately before the run so reviewers can
audit the control-plane input independently from the user message and evidence.

## Source and attribution boundaries

All excerpts use the already frozen official documentation commit
[`695e6ce2fb1b23afc6df66b40420ab0013ad72fd`](https://github.com/streamlit/docs/tree/695e6ce2fb1b23afc6df66b40420ab0013ad72fd)
and the local source snapshot dated 2026-10-06. Nine unique excerpts were checked
verbatim against the provided normalized official catalogs:

- Generated 1.64.0 `streamlit.selectbox` signature, callback/argument behavior and
  keyed Session State access.
- Generated 1.64.0 `streamlit.form` callback constraint and
  `streamlit.form_submit_button` signature, batching behavior and callback
  parameters.
- Generated 1.64.0 `streamlit.multiselect` default and `streamlit.fragment`
  rerun behavior.
- [Widget behavior, lines 104–114](https://github.com/streamlit/docs/blob/695e6ce2fb1b23afc6df66b40420ab0013ad72fd/content/develop/concepts/architecture/widget-behavior.md#L104):
  update/callback/rerun order, callback display behavior and the distinction
  between arguments established at construction and state read during invocation.

Generated hits carry the exact 1.64.0 applicability value and JSON pointer. The
concept excerpt remains an **unversioned October 2026 snapshot** with empty
`applicable_versions`; it is never relabelled as historical documentation. The
superseded 1.63.0 user report has no fabricated exact matching source. For the
unknown-version case, exact current API records are available only as evidence
about that documented version, not about the user's installation.

Each case has two fixed identical evidence pools with at most four hits. This
allows bounded retrieval without pretending that an actual retrieval adapter
ranked or discovered these sources. The snapshot ID is
`core-quality-guards-v4`. Generated source URLs pin `python/streamlit.json`;
Markdown URLs pin the concept file and span.

Every origin field is `null` and every case kind is `synthetic`. Facts use
`user/synthetic-guards-v4/<probe-id>` with an explicit `synthetic-initial` turn;
the correction probe preserves `synthetic-prior` and
`synthetic-correction`. Performed checks are statements attributed to the
synthetic user message, not assistant verification. The supplied source snippets
and user code were never executed. No free-text fact extractor, persistent
tracker or additional agent is implemented by these fixtures.

The existing development-family reservations (#8061, #8901, #12782 and #16914)
and provisional family quarantine are retained as exclusions. No new real
report family is consumed by this synthetic suite. All reservations still apply
to future retrieval and formal evaluation construction.

## Offline validation

From the repository root:

```bash
uv run --no-sync python -c 'from pathlib import Path; from agent_app.reasoning.probes import load_suite; suite = load_suite(Path("experiments/decision_quality/cases-guards-v4.json")); print(len(suite.cases))'
```

Validation checks the existing `ProbeSuite` contracts, unique IDs, fixed snapshot
and top-k boundaries. Source verification additionally checked exact excerpt
membership, source commits, JSON pointers and version applicability against the
local official catalogs. These checks make no API calls and execute no embedded
source or user snippet. Paid execution requires a separately registered
comparison protocol and the designated gateway/ledger authorization; this suite
does not grant it.
