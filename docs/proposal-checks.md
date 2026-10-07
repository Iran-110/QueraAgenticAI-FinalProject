# Optional proposal checks

The core can reject a few specific proposal contradictions before returning a
preview. These checks are **explicit development opt-ins**. The default remains
the baseline prompt with existing authority and syntax validation. No extra
reasoning agent or code execution is introduced.

## Caller-owned questions and intent

`ProposalRequirements` binds a manually curated question catalog and a
fresh-widget-value requirement to one case and revision. Pass it through
`SupportEngine.run(..., proposal_requirements=requirements)`. Configure the engine
with `proposal_checks=True` to enforce it. The `grounded_rules` prompt is a
separate explicit opt-in that requires this catalog in `ReasoningContext`.
The experimental `compiled_rules` policy additionally encodes registered
question pairs and supplied citation IDs in the model-visible schema and decision
metadata. It is separate so the measured earlier `grounded_rules` option remains
available. The gateway still sends ordinary prompted text; no native provider
schema enforcement is assumed, and the core's runtime checks remain authoritative.

```python
from agent_app.contracts import ProposalRequirements, QuestionTarget
from agent_app.orchestration import SupportEngine

requirements = ProposalRequirements(
    case_id=case.case_id,
    case_revision=case.case_revision,
    question_targets=(
        QuestionTarget(
            name="callback_helper_body",
            question="Could you share the complete callback helper body?",
        ),
    ),
    require_fresh_widget_value=False,
)
engine = SupportEngine(
    retriever, reasoner, snapshot_id=snapshot_id, proposal_checks=True
)
preview = engine.run(case, user_message, proposal_requirements=requirements)
```

The snippet assumes caller-supplied adapters and a genuinely absent helper. It
does not infer missing facts from arbitrary prose. Rebuild requirements whenever
the authoritative revision changes. Stale/unrelated catalogs and targets naming
active user facts fail before adapters run. Evidence facts do not establish what
the user knows. Each reasoner attempt receives independent deep copies of the
catalog and feedback so adapter-side mutation cannot change enforcement.

For an `ask` decision, checks require one registered `missing_info` name and its
exact registered `next_question`. An empty catalog registers no available
question; it **does not prove that all possible user details are known**. The
caller must add a genuinely useful new target when appropriate. Restrictive
curation can exclude a useful clarification and must be evaluated.

The question check validates those two structured fields. It does not prove that
the free-text user draft, rationale or maintainer summary asks no other question
or preserves every observation. The prompt requests consistent drafts, but
whole-proposal human/source review remains necessary. UI owners should render
the structured question deliberately rather than assuming arbitrary draft text
has this guarantee.

## Source-grounded callback checks

The checker parses bounded, labeled Python fences without running them. It can
detect an explicit keyword absent from a complete applicable callable signature,
an own-widget Session State value passed at construction time when the caller
explicitly requires the newly selected value, and a narrowly provable callback
parameter-binding mismatch.

Signature checks require one active user-supplied exact Streamlit version,
matching generated docstring identity/version/JSON pointer, a pinned official
documentation URL, and an explicit unshadowed module import. Conflicting,
incomplete or ambiguous sources/imports are skipped. Metadata agreement is not
independent verification that a retrieved record is authentic.

Fresh-value checking additionally requires the reviewed widget-timing excerpt at
documentation commit `695e6ce2fb1b23afc6df66b40420ab0013ad72fd`, used alongside the
exact 1.64.0 API record. The concept excerpt is an unversioned snapshot; this
guard does not infer historical applicability. Only recognized direct own-key
reads in literal callback arguments are covered. Dynamic code, opaque helpers,
other keys, inline/unlabeled snippets and general runtime behavior remain
outside the guarantee.

Callback arity additionally requires an exact-version signature and explicit
callback `args`/`kwargs` documentation from the reviewed official JSON snapshot.
Within one complete fence, a single direct module-level registration must resolve
to a preceding unique undecorated synchronous function. Literal list/tuple
arguments and string-keyed dictionaries are bound statically against required,
defaulted, positional-only, keyword-only and variadic parameters. Missing/excess
arguments and duplicate positional/keyword binding can produce
`callback_arity_mismatch`; defaults, a valid stable-key argument and intentional
old-value arguments remain valid. This check does not require fresh-value intent.

The proof subset is conservative: opaque argument containers or eager expressions,
aliases, mutation, nested/conditional registrations, decorators, non-name
assignment targets and other non-inert top-level statements cause abstention.
Even an additional `st.write(...)` call in the same fence is outside this subset.
Separate fences are not combined. Prose-only advice to remove an argument is not
checked. No finding is a correctness certificate for the code or the full draft.

A previous-value snapshot can be intentional. Leave
`require_fresh_widget_value=False` for that task; construction-time state capture
is not universally wrong. The core never derives this flag from retrieved
instructions or model output.

Findings use allowlisted codes: `invalid_api_keyword`, `callback_value_captured`,
`callback_arity_mismatch`,
`ask_target_required`, `ask_unregistered_target`, `ask_question_mismatch`. They
consume the existing repair allowance; refinement and repair together still
permit at most two model attempts. Authority/evidence violations remain terminal
and are checked first. No bad output, source text or sensitive field value is
echoed into diagnostic feedback. Requirements grant no action permission and
provide no durable tracker state or approval enforcement.

## Registered comparison

The [fresh synthetic fixtures](../experiments/decision_quality/README-guards-v4.md)
and three-condition protocol compare the current shape policy, caller metadata
with a focused prompt, and the same inputs/prompt with deterministic enforcement.
The [review procedure](../experiments/decision_quality/review-guards-v4.json)
separates schema acceptance, exact question conformance and whole-proposal
semantic quality. These are development probes with hand-authored catalogs,
including a deliberate previous-value control; the final held-out split stays
excluded.

The [offline whole-proposal challenges](../experiments/decision_quality/README-semantic-v6.md)
replay authored proposals, including deliberate semantic failures that pass these
narrow checks. They separate detector scope from developer semantic labels and
do not measure fresh model quality.
