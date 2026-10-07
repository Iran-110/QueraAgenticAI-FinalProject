# Model gateway and shared budget

Status, 2026-10-07: offline tests and controlled live checks cover the gateway. After reproducing the original decision-field failure, corrected prompts returned valid questions, a referenced answer and a repaired decision on synthetic inputs. Usage was settled in the ledger. This verifies those compatibility paths, not real support quality or RAG relevance. Account deductions have not been reconciled; no real key is required for offline demos.

## First live compatibility check

The pilot used an empty synthetic evidence bundle and a widget question with unknown version/code. It allowed one model attempt, 8,192 reserved input tokens and at most 512 output tokens. One HTTP send returned status 200 in about 4.1 seconds. Reported usage was 1,229 input and 174 output tokens; the ledger settled **USD 0.000317625** at the pinned public rates and released the unused reservation. No pending or uncertain amount remained, and the ledger did not halt.

The core returned `ModelOutputInvalid` and did not buy another attempt. The raw output was not retained, so that request's exact failed rule is unknown. The prompt was subsequently clarified to request a JSON instance, exclude Markdown, and explain the decision-dependent fields that JSON Schema alone does not express. Later diagnostic and verification checks are recorded below; routine development remains offline.

The credential, ledger and local pilot receipt stay outside Git. The receipt contains operational counts and cost estimates, not the key or raw model response. The local runner retains a USD 4.50 ceiling and USD 0.50 outside it; after this request its available ledger amount was USD 4.499682375. This is local accounting, not a fetched provider balance.

## Diagnosis and corrected live checks

Two further requests using the original prompt both produced valid JSON that violated a decision rule. The diagnostic reproduction identified `ask_question_required`: `decision="ask"` was returned without a non-null `next_question`. JSON Schema alone does not express that model-validator condition. The updated system instruction explicitly explains it, along with the question/query/draft rules for all four decisions.

The corrected prompt passed a live question check. A separate live answer on a synthetic source passed citation validation. A repair check injected one invalid scripted first response, then used exactly one live second attempt with `ask_question_required` feedback; it returned a valid question. That test made one paid request, not two. These are narrow compatibility observations, not a success-rate benchmark, real retrieval results or evidence of semantic correctness on production cases.

Across the initial pilot and these checks, **six HTTP requests** settled: 7,673 input and 1,072 output tokens, estimated total **USD 0.001973565** at pinned public rates. The designated ledger has no reserved or uncertain amount, is not halted, and has USD 4.498026435 available under its USD 4.50 ceiling. Provider billing reconciliation is still pending. No raw response or credential was written to the receipts or Git.

## Strict output validation and bounded repair

The parser accepts one bare JSON object or a validated port mapping/model. Markdown wrappers, surrounding prose, duplicate keys (including nested ones), nonstandard numeric constants and oversized text fail validation. It does not extract a JSON-looking substring or quietly discard extra fields. The `AnalysisResult` decision and authority rules remain unchanged.

`RunResult.output_issues` contains bounded allowlisted issue codes and known top-level fields. It never includes arbitrary field names, model values, raw validation messages, inputs or contexts. A successful repaired run may still include the first attempt's issues; use `status` to decide whether a preview is available. For example:

```json
{"code":"ask_question_required","field":"next_question"}
```

The engine places these diagnostics in caller-owned `ReasoningContext.output_feedback` only on attempt 2. The gateway adds them to trusted system instructions without echoing the failed response. They consume the original two-attempt allowance; they cannot trigger a third attempt. Unsupported evidence, invented user facts, stale revisions and terminal provider failures remain terminal rather than buying a repair.

Ledger identity excludes `output_feedback` and preserves the original run/case/revision/attempt serialization. Changing a hint cannot resend an already used attempt, and records created before feedback was introduced still block duplicates. This preserves accounting idempotency, not case-event replay or tracker persistence.

## Integration

`MetisReasoner` implements `Reasoner.analyze(case, user_message, evidence, *, context)`. The engine supplies `ReasoningContext` with run ID, case ID, case revision, and attempt index. The ledger uses this context to attribute attempts; source text and model output cannot choose it.

HTTPx sends a plain nonstreaming `POST` to `https://api.metisai.ir/openai/v1/chat/completions` with the shared messages and `max_tokens`. Live calls require explicit configuration and a secret key; `live_enabled` defaults to `False`, and the key uses `SecretStr`. HTTP retries, redirects, and environment proxies are disabled. The adapter requests structured text through the prompt; the engine validates it with Pydantic. Native `response_format` and tool calling are not assumed. The endpoint and `max_tokens` follow [Metis's official OpenAI wrapper example](https://docs.metisai.ir/api/wrapper/openai/), which also warns that feature coverage is incomplete.

`MetisConfig.from_env()` reads `METIS_API_KEY`, `METIS_MODEL`, and `METIS_LIVE_ENABLED`; only the exact value `true` enables live requests. It does not load a `.env` file automatically. The CLI has no live-call flag; normal development does not need a real key.

The engine still returns drafts for human review. Source-locator validation does not prove semantic faithfulness, and this gateway does not provide a tracker or permission to execute an action.

## Offline commands

From the repository root:

```bash
uv sync --locked --group dev
uv run agent-app gateway-demo --scenario success
uv run agent-app gateway-demo --scenario repair
uv run agent-app gateway-demo --scenario timeout
uv run agent-app gateway-demo --scenario budget
```

`success` sends one mock request; `repair` sends two and accounts for both. `timeout` keeps a simulated uncertain reservation; `budget` sends no request. The last two deliberately return exit code 1. Each demo uses a temporary synthetic ledger and leaves the team's real ledger alone.

Initialize the designated runner's ledger once, then inspect it offline:

```bash
uv run agent-app budget init --path runtime/budget.sqlite3 --limit-usd 4.50 --opening-spend-usd 0
uv run agent-app budget status --path runtime/budget.sqlite3
```

These commands do not contact Metis. Initialization refuses an existing file; `status` does not create a missing one. Do not replace the ledger to reset the balance. The example keeps USD 0.50 outside the runner limit as a margin for unverified billing assumptions. Its zero opening spend is valid only because the user confirmed the credit was untouched; revise it if the team has since spent credit.

## One team ledger

Use one designated runner and one shared local SQLite ledger. Independent files for different teammates cannot enforce a combined limit. SQLite transactions make reservations atomic when multiple callers use that same file; this is local accounting, not an account-wide billing API.

Initialize the ledger explicitly with a team limit no higher than USD 5 and the already incurred spend. The user confirmed that the team's USD 5 credit is untouched at this milestone; an opening spend of zero records that statement, not a balance fetched from Metis. Existing spend from embeddings, evaluations, bonus work, or other clients must be included in the shared total. The gateway accounts for its own requests; it cannot detect spending outside it automatically.

Amounts are stored as integer nanoUSD: USD 1 = 1,000,000,000 units. A reservation is committed before any network request. Valid known usage settles the reservation at the verified price; timeout or unknown usage retains it and stops further paid retry. A request that costs more than its bound halts further work instead of silently borrowing from the remaining budget. Restart does not discard outstanding reservations.

Missing or malformed usage and unknown returned models also halt new reservations globally. A timeout stops its invocation while keeping the uncertain amount charged against the available budget. There is no automatic unhalt or refund. `BudgetLedger.settle()` can reconcile a recorded reservation with verified observed usage even while halted; it does not clear the halt. Phase tags are audit labels, not separate phase budgets.

Defaults reserve 32,768 input tokens and cap output at 1,024 tokens, with a USD 0.02 per-request cap. The prompt's UTF-8 byte count plus a 1,024 framing margin must fit that input reserve. This is an operational bound to test in the live pilot, not a provider billing guarantee. Usage-based amounts are estimates at the pinned public rates; the ledger does not fetch account deductions.

The core's invocation limits remain 2 model attempts, 2 retrieval rounds, 2 queries per round, and 8 steps. They do not grant a new budget. Malformed output consumes its attempt; terminal gateway failures stop the engine rather than requesting another paid attempt.

`RunResult.model_attempts` counts reasoning-port invocations, including a preflight budget denial. It is not an actual HTTP or billed-request counter. The gateway demo reports mock HTTP requests separately; real evaluation must use gateway/ledger observations and reconcile them with provider usage and dashboard deductions.

## Price basis

The [public Metis price card](https://api.metisai.ir/api/v1/meta/providers/pricing) was checked on **2026-10-07**. These are ordinary text input/output rates in USD; the code pins a dated basis rather than fetching a new price during every call.

| Model or verified returned ID | Input per 1M tokens | Output per 1M tokens |
| --- | ---: | ---: |
| `gpt-4o-mini` | 0.165 | 0.660 |
| `gpt-4o-mini-2024-07-18` | 0.165 | 0.660 |
| `gpt-4.1-mini` | 0.440 | 1.760 |

The default candidate is `gpt-4o-mini`; this is a configuration choice, not a model-quality result. An unverified returned model ID must stop accounting rather than inherit an alias's price. In particular, the price card did not establish a dated `gpt-4.1-mini` serving ID for this implementation. Cached-token discounts and extra services are not assumed. Public prices do not establish the team's exact account bill; compare a small controlled pilot with the dashboard before broader use.

## Failure handling

| Situation | Required behavior |
| --- | --- |
| Live execution disabled, missing configuration, or unavailable ledger | Stop before sending the request |
| Reservation would exceed remaining budget | Stop before sending the request |
| Timeout, request error, or unreadable response envelope | Retain uncertain reservation; stop further paid retry in this invocation |
| Missing/malformed usage or unverified returned model ID | Retain uncertain reservation and globally halt new reservations |
| Known usage but invalid decision JSON | Account for the paid request; repair may use the remaining shared attempt allowance |
| Actual cost or token counts exceed their reserved bounds | Record known usage and globally halt further spending |

Raw keys, prompts, evidence, responses, and exception text do not belong in budget logs or traces. Keep operational IDs and counts separate from sensitive content. The offline demonstration verifies the protocol and local controls; its simulated token counts and costs must not appear in a report as paid model results.
