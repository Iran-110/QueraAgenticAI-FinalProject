"""Private formatting for an explicitly selected review brief renderer.

Callers enforce request/plan bindings, selection validity and conflicts first.
Only attributed USER report/fact/check display normalizes actual CRLF. Source
text, original records, digests and selected character spans remain unchanged.
"""

from urllib.parse import quote

from agent_app.contracts import EvidenceHit, Fact, GroundedRequest
from agent_app.reasoning.grounding import _display, _user_version


def _user_display(value: str) -> str:
    return _display(value.replace("\r\n", "\n"))


def _quotation(value: str, *, user: bool = False) -> str:
    displayed = _user_display(value) if user else _display(value)
    return "\n".join("> " + line for line in displayed.split("\n"))


def _facts(values: tuple[Fact, ...]) -> str:
    return "\n".join(
        "- " + _user_display(f"{fact.name}: {fact.value}").replace("\n", "\n  ") for fact in values
    )


def format_review_brief(
    request: GroundedRequest,
    *,
    decision: str,
    question: str | None,
    quotations: tuple[tuple[EvidenceHit, int, int], ...],
    plan_selected_ids: set[str],
    scopes: dict[str, str],
    prior_conflict: bool,
    selected_user_facts: tuple[Fact, ...] = (),
) -> tuple[str, str, str]:
    """Return new draft/summary/rationale without mutating validated input data."""
    case = request.case
    version = _user_version(case)
    displayed_version = _user_display(version) if version is not None else "unknown"
    proposed = (
        "Proposed next step: a maintainer could reproduce the recorded report using any "
        "supplied code and the current USER-reported Streamlit version "
        + displayed_version
        + ", then compare the reproduction result with the supplied source scopes."
        if version is not None
        else "Proposed next step: a maintainer could reproduce the recorded report using any "
        "supplied code once the affected Streamlit version is confirmed, then compare the "
        "reproduction result with the supplied source scopes."
    )
    displayed_ids = {hit.chunk_id for hit, _start, _end in quotations}
    inventory = []
    for hit in request.evidence.hits:
        status = (
            "plan-selected"
            if hit.chunk_id in plan_selected_ids
            else "displayed conflict-required (not plan-selected)"
            if hit.chunk_id in displayed_ids
            else "merely supplied (not selected)"
        )
        inventory.append(
            "- Chunk "
            + _display(hit.chunk_id)
            + "; source "
            + _display(hit.source_id)
            + "; type="
            + hit.source_type
            + "; revision="
            + _display(hit.source_commit if hit.source_commit is not None else "not supplied")
            + "; scope="
            + scopes[hit.chunk_id]
            + "; versions="
            + _display(", ".join(hit.applicable_versions) or "unknown")
            + "; source span="
            + _display(hit.source_span or "not supplied")
            + "; status="
            + status
            + ".\n"
            + "  [Supplied source]("
            + quote(hit.source_url, safe=":/?&=.%#")
            + ")"
        )
    source_quotations = "\n\n".join(
        "Selected/displayed quotation from chunk "
        + _display(hit.chunk_id)
        + f", characters [{start},{end}); scope="
        + scopes[hit.chunk_id]
        + ":\n"
        + "[Supplied source]("
        + quote(hit.source_url, safe=":/?&=.%#")
        + ")\n"
        + _quotation(hit.excerpt[start:end])
        for hit, start, end in quotations
    )
    gaps = []
    for gap in request.gaps:
        gaps.append(
            "- "
            + gap.kind
            + " gap "
            + _display(gap.name)
            + ": "
            + _display(gap.description)
            + "\n  Caller-stated necessity: "
            + _display(gap.necessity)
            + ("\n  Registered question: " + _display(gap.question) if gap.question else "")
        )
    conflicts = [
        "Current unresolved group: " + ", ".join(_display(chunk) for chunk in group)
        for group in request.conflict_groups
    ]
    if prior_conflict:
        conflicts.append("A prior caller-declared source conflict remains unresolved.")
    active_facts = tuple(
        fact for fact in case.facts if fact.status == "active" and fact.provenance_kind == "user"
    )
    checks = "\n".join(
        "- " + _user_display(check).replace("\n", "\n  ") for check in case.checks_performed
    )
    unknowns = "\n".join("- " + _display(name) for name in case.unknowns)
    summary = (
        "Review proposal only: USER records are unverified; source selection and metadata "
        "do not establish semantic support, a diagnosis, a successful fix or completed action.\n\n"
        + "Case "
        + _display(case.case_id)
        + f"; revision {case.case_revision}.\n\n"
        + "Supplied USER report/history:\n"
        + _quotation(request.user_message, user=True)
        + "\n\nActive USER-reported facts:\n"
        + (_facts(active_facts) or "None recorded.")
        + "\n\nUSER-reported checks:\n"
        + (checks or "None recorded.")
        + "\n\nCurrent unknowns:\n"
        + (unknowns or "None recorded.")
        + "\n\nSource inventory (all supplied hits):\n"
        + ("\n\n".join(inventory) or "No hits supplied.")
        + "\n\nCaller-declared USER/source gaps:\n"
        + ("\n".join(gaps) or "None declared.")
        + "\n\nUnresolved caller conflicts:\n"
        + ("\n".join(conflicts) or "None declared.")
        + (
            "\n\nSelected/displayed complete quotations:\n" + source_quotations
            if source_quotations
            else ""
        )
        + "\n\n"
        + proposed
    )
    selected_facts = _facts(selected_user_facts)
    if decision == "ask":
        draft = question
    elif decision == "answer":
        draft = (
            "Selected supplied quotations; applicability, diagnosis and fix are unverified."
            + ("\n\nSelected USER-reported facts:\n" + selected_facts if selected_facts else "")
            + ("\n\n" + source_quotations if source_quotations else "")
        )
    else:
        draft = (
            "Further maintainer investigation is proposed.\nUSER-reported Streamlit version: "
            + displayed_version
            + "."
            + ("\n\nSelected USER-reported facts:\n" + selected_facts if selected_facts else "")
            + "\n\n"
            + proposed
        )
    rationale = (
        "The core rendered a review brief from the supplied USER report/history, current USER "
        "records, the complete supplied-source inventory and selected/displayed quotations. "
        "Reproduction is proposed and has not been performed by this renderer; semantic "
        "support, diagnosis, fix and usefulness remain unassessed."
    )
    if decision == "ask":
        rationale += (
            " The canonical caller-registered question is preserved; necessity is caller-declared."
        )
    return draft, summary, rationale
