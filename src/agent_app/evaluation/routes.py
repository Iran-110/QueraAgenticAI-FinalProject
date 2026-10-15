"""Registered route integrity and selection; no model input or semantic judge."""

from dataclasses import dataclass

from agent_app.contracts import ProposalHandoff
from agent_app.orchestration.handoff import validate_handoff
from agent_app.orchestration.intake import STREAMLIT_VERSION_QUESTION
from agent_app.reasoning.grounding import render_grounded_plan, source_content_sha256

MAX_ROUTE_NODES = 64
MAX_ROUTES = 256
DECISIONS = {"answer", "ask", "escalate"}


class ConditionalRoutesRejected(ValueError):
    def __init__(self):
        super().__init__("ConditionalRoutesRejected")


def _need(value):
    if not value:
        raise ConditionalRoutesRejected()


def _text(value):
    return type(value) is str and bool(value.strip()) and len(value) <= 20_000


@dataclass(frozen=True)
class Route:
    source: str
    target: str | None
    decision: str
    question_target: str | None = None
    question: str | None = None


@dataclass(frozen=True)
class RouteGraph:
    node_ids: tuple[str, ...]
    routes: tuple[Route, ...]
    allow_source_background: bool = False
    concise_user_draft: bool = False

    @classmethod
    def from_fixture(cls, data, *, allow_source_background=False, concise_user_draft=False):
        """Validate every branch locally before constructing any live factory.

        Review declarations and graph eligibility are not authenticated human
        judgment. Gold is used only by the local fixture runner, never adapters.
        """
        try:
            _need(type(allow_source_background) is bool)
            _need(type(concise_user_draft) is bool)
            _need(data.get("registered_before_first_run") is True)
            turns = data["turns"]
            _need(type(turns) is list and 1 <= len(turns) <= MAX_ROUTE_NODES)
            ids = [turn["id"] for turn in turns]
            _need(all(_text(name) for name in ids) and len(ids) == len(set(ids)))
            positions = {name: position for position, name in enumerate(ids)}
            source_turns = dict(zip(ids, turns, strict=True))
            coverage = data["evaluation"]["coverage"]
            _need(
                type(coverage["turn_ids"]) is list
                and len(coverage["turn_ids"]) == len(ids)
                and set(coverage["turn_ids"]) == set(ids)
            )
            definitions = coverage["routes"]
            _need(type(definitions) is list and 1 <= len(definitions) <= MAX_ROUTES)
            routes, seen, outgoing = [], set(), {name: set() for name in ids}
            for definition in definitions:
                _need(
                    type(definition) is dict
                    and set(definition) == {"from_turn", "to_turn", "guard"}
                )
                source, target, guard = (
                    definition["from_turn"],
                    definition["to_turn"],
                    definition["guard"],
                )
                _need(type(guard) is dict and set(guard) <= {"decision", "question_target"})
                decision, name = guard["decision"], guard.get("question_target")
                _need(source in positions and decision in DECISIONS)
                _need(
                    target is None
                    or (target in positions and positions[target] > positions[source])
                )
                identity = (source, decision, name)
                _need(identity not in seen)
                seen.add(identity)
                question = None
                if decision == "ask":
                    _need(_text(name))
                    gaps = source_turns[source]["gold"]["gaps"]
                    matching = [
                        gap for gap in gaps if gap.get("kind") == "user" and gap.get("name") == name
                    ]
                    _need(
                        len(matching) == 1
                        and _text(matching[0].get("question"))
                        and _text(matching[0].get("necessity"))
                    )
                    question = matching[0]["question"].strip()
                    if target is not None:
                        current = source_turns[source].get("case_id", data["case"]["case_id"])
                        next_turn = source_turns[target]
                        _need(next_turn.get("case_id", data["case"]["case_id"]) == current)
                        if next_turn["visible"].get("reply_to_approved_question"):
                            _need(
                                name == STREAMLIT_VERSION_QUESTION.name
                                and question == STREAMLIT_VERSION_QUESTION.question
                            )
                        elif name != STREAMLIT_VERSION_QUESTION.name:
                            visible = next_turn["visible"]
                            reported = {fact["name"] for fact in visible.get("reported_facts", [])}
                            _need(name in reported or name in visible.get("unknowns", []))
                else:
                    _need(name is None and "question_target" not in guard)
                routes.append(Route(source, target, decision, name, question))
                outgoing[source].add(decision)
            for name, turn in source_turns.items():
                allowed = turn["gold"]["acceptable_decisions"]
                _need(type(allowed) is list and bool(allowed) and all(_text(x) for x in allowed))
                _need(
                    len(allowed) == len(set(allowed))
                    and set(allowed) <= DECISIONS
                    and outgoing[name] == set(allowed)
                )
            reached = {ids[0]}
            for route in sorted(routes, key=lambda row: positions[row.source]):
                if route.source in reached and route.target is not None:
                    reached.add(route.target)
            _need(reached == set(ids))
            return cls(tuple(ids), tuple(routes), allow_source_background, concise_user_draft)
        except ConditionalRoutesRejected:
            raise
        except (TypeError, KeyError, ValueError, AttributeError, RecursionError):
            raise ConditionalRoutesRejected() from None

    def _question_display_matches(self, route, analysis, proposal):
        if analysis.get("user_draft") == route.question:
            return True
        if (
            self.allow_source_background is not True
            or route.question_target == STREAMLIT_VERSION_QUESTION.name
        ):
            return False
        try:
            handoff = validate_handoff(ProposalHandoff.model_validate(proposal["review_handoff"]))
            request = handoff.grounded_request
            if (
                request is None
                or handoff.analysis.model_dump(mode="json") != analysis
                or handoff.proposal_id != proposal["proposal_id"]
                or handoff.case.case_id != proposal["case_id"]
                or handoff.case.case_revision != proposal["case_revision"]
            ):
                return False
            hits = {hit.chunk_id: hit for hit in request.evidence.hits}
            selected = dict.fromkeys(link.chunk_id for link in handoff.analysis.evidence_links)
            reconstructed = render_grounded_plan(
                request,
                {
                    "context_sha256": request.context_sha256,
                    "decision": "ask",
                    "question_name": route.question_target,
                    "sources": [
                        {"chunk_id": chunk, "content_sha256": source_content_sha256(hits[chunk])}
                        for chunk in selected
                    ],
                },
                ask_source_background=True,
                **({"concise_user_draft": True} if self.concise_user_draft else {}),
            )
            # A canonical prefix alone is not enough. Human-edited or arbitrary
            # text must not unlock a future authored reply or alter old routes.
            return (
                reconstructed.user_draft == analysis["user_draft"]
                and reconstructed.next_question == route.question
            )
        except (TypeError, KeyError, ValueError, AttributeError, RecursionError):
            return False

    def select(self, source, step, view):
        """Select only an actual current proposal, then bind any reply to release.

        A terminal pending question is a completed selected path. A continuation
        requires its exact approved/released question, including any human edit.
        Unknown wording is a fixture coverage gap, not proof of model failure.
        """
        proposal = step.get("edited_proposal") or step.get("proposal")
        if not proposal or not proposal.get("proposal_id"):
            return None
        if proposal.get("case_id") != view.get("case_id") or proposal.get(
            "case_revision"
        ) != view.get("case_revision"):
            return None
        decision = proposal.get("decision")
        current = view.get("pending")
        awaiting = view.get("awaiting_reply")
        if decision == "ask":
            analysis = proposal.get("analysis", {})
            if awaiting:
                if not (
                    awaiting.get("proposal_id") == proposal["proposal_id"]
                    and awaiting.get("case_id") == view.get("case_id")
                    and awaiting.get("case_revision") == view.get("case_revision")
                    and awaiting.get("question") == analysis
                    and any(
                        entry.get("text") == analysis.get("user_draft")
                        for entry in step.get("released_outputs", [])
                    )
                ):
                    return None
            elif current != proposal:
                return None
            candidates = [
                route
                for route in self.routes
                if route.source == source
                and route.decision == "ask"
                and analysis.get("missing_info") == [route.question_target]
                and analysis.get("next_question") == route.question
                and self._question_display_matches(route, analysis, proposal)
            ]
            if len(candidates) != 1:
                return None
            route = candidates[0]
            if route.target is not None and not awaiting:
                return None
            return route
        candidates = [
            route for route in self.routes if route.source == source and route.decision == decision
        ]
        return candidates[0] if len(candidates) == 1 else None
