# Metis model gateway

This module implements the reasoning port and shared local budget accounting.
Live calls are disabled by default. The gateway demo uses HTTPx `MockTransport`,
synthetic evidence, and simulated usage; it spends no API credit and does not
verify compatibility or billing on the team's Metis account.

The adapter uses one nonstreaming chat-completion request with the shared prompt;
the engine validates the returned decision with `AnalysisResult`. It does not assume
native JSON-schema output support or add HTTP retries. Each attempt carries the
core's `ReasoningContext`; model text cannot choose its ledger attribution.

Use one designated runner and one SQLite ledger for the whole team's USD 5
budget. Reserve before the request, settle known usage afterward, and retain the
reservation on uncertain failures. Other modules must use this boundary rather
than creating independent clients, budget files, or credentials.

Operator commands, dated prices, failure handling, and integration limits are in
[the model gateway guide](../../../docs/model-gateway.md).

Optional `METIS_GROUNDED_SOURCE_CAPACITY=true` requires
`METIS_GROUNDED_DECISION_CONTRACTS=true`. It only tightens existing prompt schema
count bounds for measurable, conflict-free requests; it does not authorize live
calls or select evidence. Default remains false: the small paired native-index
study showed no route/answer-quality gain. See [behavior and limitations](../../../docs/source-capacity.fa.md).
