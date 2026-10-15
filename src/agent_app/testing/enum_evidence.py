"""Answer-informed, fixed Enum evidence controls; never a RAG ingestion path.

The official guide is intentionally excluded from the real corpus. This packet
only measures what the existing core selects when those documented passages are
explicitly supplied to an exposed development case. No search is performed.
"""

import hashlib
import itertools
import json
from copy import deepcopy
from pathlib import Path

from agent_app.contracts import (
    CaseState,
    EvidenceBundle,
    EvidenceHit,
    GroundedPlan,
    OutputFeedback,
    OutputIssue,
    ReasoningContext,
    RetrievalRequest,
    UserTurn,
)
from agent_app.llm.config import MetisConfig
from agent_app.llm.metis import configured_grounded_messages
from agent_app.orchestration.turns import propose_user_turn
from agent_app.reasoning.catalog import caller_catalog
from agent_app.reasoning.grounding import (
    GroundingRejected,
    render_grounded_plan,
    source_content_sha256,
)
from agent_app.reasoning.resource_guidance import _render_resources
from agent_app.reasoning.source_capacity import source_capacity

ROOT = Path(__file__).resolve().parents[3]
PACKET_PATH = Path("experiments/core_enum_evidence_v1/source-packet-v1.json")
ARMS = ("fixed_baseline", "fixed_guide_added")
SOURCE_FILE = "content/develop/concepts/app-design/custom-classes.md"
SOURCE_ID = "docs:" + SOURCE_FILE
SOURCE_URL = "https://docs.streamlit.io/develop/concepts/design/custom-classes"
SOURCE_COMMIT = "695e6ce2fb1b23afc6df66b40420ab0013ad72fd"
RAW_SHA256 = "b1c5a760e61d213f294297fae055bae52e25b0d296761fd1c533cf282246b8c6"
PINNED_URL = f"https://github.com/streamlit/docs/blob/{SOURCE_COMMIT}/{SOURCE_FILE}"
EVIDENCE_PATH = "data/evaluation/dev-three-v1/evidence-v1.json"
CASE_PATHS = {
    "dev-case-a": "data/evaluation/dev-three-v1/cases/pilot-12782-v1.json",
    "dev-case-b": "data/evaluation/dev-three-v1/cases/icon-9770-v1.json",
    "dev-case-c": "data/evaluation/dev-three-v1/cases/enum-8129-v1.json",
}
SECTIONS = (
    (
        "separate-module",
        1637,
        3780,
        "414347d4b9eef71e0b7d2711a84f4037eea0e98870e09b7f5c3c531610019039",
    ),
    (
        "enum-and-widget-coercion",
        12538,
        15157,
        "91538e2afe431f10f17ce6e0ca3a6c996007e5db90a39abe3d3276f132c7e349",
    ),
)
BOUNDARIES = {
    "answer_informed_exposed_dev": True,
    "official_guide_is_answer_linked": True,
    "corpus_ingestion_allowed": False,
    "real_RAG_index_changed": False,
    "held_out_test_eligible": False,
    "final_evaluation": False,
    "actual_search": False,
    "version_scope": "Current conceptual guide; installed1.31.0/1.31.1 applicability unconfirmed.",
    "source_text_is_untrusted_not_action_authority": True,
}


class EnumEvidenceRejected(ValueError):
    def __init__(self):
        super().__init__("EnumEvidencePacketRejected")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    return _sha(json.dumps(value, sort_keys=True, ensure_ascii=False).encode())


def _raw_source(text):
    return {
        "source_id": SOURCE_ID,
        "source_file": SOURCE_FILE,
        "source_url": SOURCE_URL,
        "pinned_source_url": PINNED_URL,
        "source_commit": SOURCE_COMMIT,
        "raw_utf8_sha256": RAW_SHA256,
        "raw_utf8_bytes": 15170,
        "raw_unicode_codepoints": 15158,
        "raw_text": text,
    }


def _records(text):
    records = []
    for name, start, end, digest in SECTIONS:
        hit = EvidenceHit(
            chunk_id=f"fixture-enum-guide-{name}-v1",
            source_id=SOURCE_ID,
            excerpt=text[start:end],
            source_url=PINNED_URL,
            source_type="doc",
            source_commit=SOURCE_COMMIT,
            applicable_versions=(),
            source_span=f"unicode_codepoint[{start}:{end}); raw_utf8_sha256={RAW_SHA256}",
        )
        records.append(
            {
                "section_id": name,
                "span": {"unit": "unicode_codepoint", "start": start, "end": end},
                "excerpt_utf8_sha256": digest,
                "normalized_evidence_sha256": source_content_sha256(hit),
                "hit": hit.model_dump(mode="json"),
            }
        )
    return records


def _fixture_pin(root, case_id, relative):
    raw = (root / relative).read_bytes()
    data = json.loads(raw)
    source = data["evidence_source"]
    if (
        source["path"] != EVIDENCE_PATH
        or data["case"]["case_id"] != case_id
        or _sha((root / EVIDENCE_PATH).read_bytes()) != source["sha256"]
    ):
        raise EnumEvidenceRejected()
    return {
        "fixture_path": relative,
        "fixture_sha256": _sha(raw),
        "fixture_id": data["fixture_id"],
        "evidence_path": EVIDENCE_PATH,
        "evidence_sha256": source["sha256"],
        "bundles_used": source["bundles_used"],
        "turn_bundle_refs": {turn["id"]: turn["evidence_bundle"] for turn in data["turns"]},
    }


def build_packet(source_path: Path, *, root: Path = ROOT):
    """Build a self-contained research packet without changing any existing data."""
    raw = Path(source_path).read_bytes()
    if _sha(raw) != RAW_SHA256:
        raise EnumEvidenceRejected()
    text = raw.decode("utf-8")
    packet = {
        "schema_version": 1,
        "packet_id": "core-enum-evidence-source-v1",
        "boundaries": dict(BOUNDARIES),
        "raw_source": _raw_source(text),
        "source_records": _records(text),
        "baseline_inputs": {
            case_id: _fixture_pin(root, case_id, relative)
            for case_id, relative in CASE_PATHS.items()
        },
    }
    return validate_packet(packet)


def validate_packet(packet):
    """Reject altered source text, normalized excerpts, scope or packet shape."""
    try:
        if (
            type(packet) is not dict
            or set(packet)
            != {
                "schema_version",
                "packet_id",
                "boundaries",
                "raw_source",
                "source_records",
                "baseline_inputs",
            }
            or type(packet["schema_version"]) is not int
            or packet["schema_version"] != 1
            or packet["packet_id"] != "core-enum-evidence-source-v1"
            or packet["boundaries"] != BOUNDARIES
            or any(type(packet["boundaries"][k]) is not type(v) for k, v in BOUNDARIES.items())
        ):
            raise EnumEvidenceRejected()
        text = packet["raw_source"]["raw_text"]
        if (
            type(text) is not str
            or len(text) != 15158
            or len(text.encode()) != 15170
            or _sha(text.encode()) != RAW_SHA256
            or packet["raw_source"] != _raw_source(text)
            or packet["source_records"] != _records(text)
            or len(packet["source_records"]) != 2
            or set(packet["baseline_inputs"]) != set(CASE_PATHS)
        ):
            raise EnumEvidenceRejected()
        for record, (_, start, end, expected) in zip(
            packet["source_records"], SECTIONS, strict=True
        ):
            if _sha(text[start:end].encode()) != expected:
                raise EnumEvidenceRejected()
            hit = EvidenceHit.model_validate(record["hit"])
            if hit.excerpt != text[start:end] or hit.applicable_versions:
                raise EnumEvidenceRejected()
        for case_id, pin in packet["baseline_inputs"].items():
            if (
                type(pin) is not dict
                or set(pin)
                != {
                    "fixture_path",
                    "fixture_sha256",
                    "fixture_id",
                    "evidence_path",
                    "evidence_sha256",
                    "bundles_used",
                    "turn_bundle_refs",
                }
                or pin["fixture_path"] != CASE_PATHS[case_id]
                or pin["evidence_path"] != EVIDENCE_PATH
                or type(pin["fixture_id"]) is not str
                or type(pin["bundles_used"]) is not list
                or type(pin["turn_bundle_refs"]) is not dict
                or len(pin["turn_bundle_refs"]) != 2
                or any(name not in pin["bundles_used"] for name in pin["turn_bundle_refs"].values())
                or any(
                    type(pin[name]) is not str
                    or len(pin[name]) != 64
                    or any(c not in "0123456789abcdef" for c in pin[name])
                    for name in ("fixture_sha256", "evidence_sha256")
                )
            ):
                raise EnumEvidenceRejected()
        return deepcopy(packet)
    except (KeyError, TypeError, ValueError, AttributeError, UnicodeError):
        raise EnumEvidenceRejected() from None


def load_source_packet(path: Path):
    return validate_packet(json.loads(Path(path).read_bytes()))


class _FixedEvidenceSupplier:
    def __init__(self, bundle, records, identity):
        self.bundle = bundle.model_copy(deep=True)
        self.records = records
        self.identity = identity
        self.calls = 0

    def search(self, request: RetrievalRequest) -> EvidenceBundle:
        request = RetrievalRequest.model_validate(request.model_dump())
        if self.calls >= 2 or request.snapshot_id != self.bundle.snapshot_id:
            raise EnumEvidenceRejected()
        self.calls += 1
        self.records.append(
            {
                **self.identity,
                "fixed_supplier_call": self.calls,
                "actual_search": False,
                "requested_queries": list(request.queries),
                "requested_top_k": request.top_k,
                "snapshot_id": request.snapshot_id,
                "returned_chunk_ids": [hit.chunk_id for hit in self.bundle.hits],
                "returned_bundle_sha256": _digest(self.bundle.model_dump(mode="json")),
            }
        )
        return self.bundle.model_copy(deep=True)


def fixture_retriever_factory(packet, fixtures, records):
    """Bind the current registered fixture turn, not query text or future replies."""
    packet = validate_packet(packet)
    by_case = {fixture.case["case_id"]: deepcopy(fixture) for fixture in fixtures.values()}
    if set(by_case) != set(CASE_PATHS):
        raise EnumEvidenceRejected()
    for case_id, fixture in by_case.items():
        root = fixture.path.resolve().parents[4]
        pin = packet["baseline_inputs"][case_id]
        if (
            fixture.path.resolve() != (root / CASE_PATHS[case_id]).resolve()
            or _fixture_pin(root, case_id, CASE_PATHS[case_id]) != pin
            or fixture.sha256 != pin["fixture_sha256"]
            or fixture.data != json.loads(fixture.path.read_bytes())
        ):
            raise EnumEvidenceRejected()
        original = json.loads((root / EVIDENCE_PATH).read_bytes())["evidence_bundles"]
        if set(fixture.bundles) != set(pin["bundles_used"]) or any(
            fixture.bundles[name] != EvidenceBundle.model_validate(original[name])
            for name in fixture.bundles
        ):
            raise EnumEvidenceRejected()
    added = tuple(EvidenceHit.model_validate(record["hit"]) for record in packet["source_records"])

    def supply(job, turn):
        try:
            arm, case_id = job["arm"], job["case_id"]
            fixture = by_case[case_id]
            pin = packet["baseline_inputs"][case_id]
            registered_turn = next(t for t in fixture.data["turns"] if t["id"] == turn["id"])
            if (
                arm not in ARMS
                or turn["evidence_bundle"] != pin["turn_bundle_refs"][turn["id"]]
                or turn["visible"] != registered_turn["visible"]
            ):
                raise EnumEvidenceRejected()
            bundle = fixture.bundles[turn["evidence_bundle"]].model_copy(deep=True)
            guide_added = case_id == "dev-case-c" and arm == "fixed_guide_added"
            if guide_added:
                bundle = EvidenceBundle.model_validate(
                    {**bundle.model_dump(), "hits": (*bundle.hits, *added)}
                )
            identity = {
                "arm": arm,
                "case_id": case_id,
                "fixture_id": fixture.data["fixture_id"],
                "turn_id": turn["id"],
                "guide_added": guide_added,
            }
            return _FixedEvidenceSupplier(bundle, records, identity), bundle.snapshot_id
        except (KeyError, TypeError, ValueError, StopIteration):
            raise EnumEvidenceRejected() from None

    return supply


def offline_boundary_report(packet, fixtures, *, source_capacity_enabled):
    """Retain every C subset, including the actual unrenderable combination.

    These direct current-context measurements are complemented by intercepted
    HTTP tests, which also include the service's complete USER history. No model
    transport or ledger is involved in this exact renderer/prompt accounting.
    """
    if type(source_capacity_enabled) is not bool:
        raise EnumEvidenceRejected()
    supplier = fixture_retriever_factory(packet, fixtures, [])
    fixture = next(f for f in fixtures.values() if f.case["case_id"] == "dev-case-c")
    config = MetisConfig(
        api_key="public-synthetic-enum-boundary-control",
        response_mode="grounded_plan",
        input_token_reserve=32768,
        max_output_tokens=1024,
        grounded_decision_contracts=True,
        grounded_source_selection_reminder=True,
        grounded_compact_plan=True,
        grounded_json_object=True,
        grounded_source_gap_handoff=True,
        grounded_source_gap_investigation=True,
        grounded_source_capacity=source_capacity_enabled,
    )
    state = CaseState(case_id="dev-case-c")
    rows, prompt_rows = [], []
    violations = 0
    for turn in fixture.data["turns"]:
        state = propose_user_turn(
            state,
            UserTurn(
                case_id=state.case_id,
                expected_revision=state.case_revision,
                turn_id=turn["id"],
                source_ref="USER:" + turn["id"],
                **turn["visible"],
            ),
        ).candidate
        for arm in ARMS:
            retriever, _ = supplier({"arm": arm, "case_id": state.case_id}, turn)
            request = caller_catalog(state, turn["visible"]["message"], retriever.bundle)
            bound = (
                source_capacity(request, source_gap_handoff=True, source_gap_investigation=True)
                if source_capacity_enabled
                else 8
            )
            bound = 8 if bound is None else bound
            for repair in (False, True):
                context = ReasoningContext(
                    run_id="offline-enum-source-boundary",
                    case_id=state.case_id,
                    case_revision=state.case_revision,
                    attempt_index=2 if repair else 1,
                    remaining_model_attempts=0 if repair else 1,
                    remaining_retrieval_rounds=0 if repair else 1,
                    can_refine=not repair,
                    output_feedback=OutputFeedback(issues=(OutputIssue(code="invalid_shape"),))
                    if repair
                    else None,
                )
                messages = configured_grounded_messages(config, request, context)
                size = len(json.dumps(messages, ensure_ascii=False).encode()) + 1024
                payload = json.loads(messages[1]["content"])
                unchanged = payload["request"] == request.model_dump(mode="json")
                if size > 32768 or not unchanged:
                    violations += 1
                prompt_rows.append(
                    {
                        "turn_id": turn["id"],
                        "arm": arm,
                        "repair": repair,
                        "full_message_utf8_bytes_plus_guard": size,
                        "input_limit": 32768,
                        "full_request_unchanged": unchanged,
                        "advertised_max_sources": payload["decision_contracts"]["rules"]["answer"][
                            "sources"
                        ]["maxItems"],
                    }
                )
            resources = _render_resources(
                request, source_gap_handoff=True, source_gap_investigation=True
            )
            for count in range(len(request.evidence.hits) + 1):
                for indices in itertools.combinations(range(len(request.evidence.hits)), count):
                    selected = [request.evidence.hits[i] for i in indices]
                    permitted = count <= bound
                    row = {
                        "turn_id": turn["id"],
                        "arm": arm,
                        "selected_indexes": list(indices),
                        "selected_chunk_ids": [hit.chunk_id for hit in selected],
                        "advertised_max_sources": bound,
                        "within_advertised_source_count": permitted,
                        "decisions": {},
                    }
                    for decision in ("answer", "escalate"):
                        if decision == "answer" and not selected:
                            row["decisions"][decision] = {
                                "status": "ineligible_empty_answer",
                                "renderer_invoked": False,
                            }
                            continue
                        plan = GroundedPlan(
                            context_sha256=request.context_sha256,
                            decision=decision,
                            sources=tuple(
                                {
                                    "chunk_id": hit.chunk_id,
                                    "content_sha256": source_content_sha256(hit),
                                }
                                for hit in selected
                            ),
                        )
                        try:
                            output = render_grounded_plan(
                                request,
                                plan,
                                source_gap_handoff=True,
                                source_gap_investigation=True,
                                ask_source_background=True,
                                concise_user_draft=True,
                            )
                            result = {
                                "status": "rendered",
                                "renderer_invoked": True,
                                "user_draft_chars": len(output.user_draft),
                                "maintainer_summary_chars": len(output.maintainer_summary),
                                "rationale_chars": len(output.rationale),
                            }
                        except GroundingRejected as error:
                            quotes = sum(resources["source_chars"][i] for i in indices)
                            if selected:
                                quotes += 2 * (len(selected) - 1) + 2
                            result = {
                                "status": "rejected",
                                "renderer_invoked": True,
                                "error_code": error.code,
                                "maintainer_summary_chars": resources["bases"][decision][1]
                                + quotes,
                                "length_method": "exact existing renderer resource accounting",
                            }
                            if permitted:
                                violations += 1
                        row["decisions"][decision] = result
                    rows.append(row)
    failures = sum(
        result["status"] == "rejected" for row in rows for result in row["decisions"].values()
    )
    return {
        "schema_version": 1,
        "report_id": "core-enum-evidence-offline-boundary-v1",
        "source_capacity": source_capacity_enabled,
        "accepted": violations == 0,
        "actual_sends": 0,
        "actual_search": False,
        "human_usefulness": None,
        "is_model_quality_score": False,
        "measurement_scope": "Direct current context; actual HTTP/USER-history checked separately.",
        "guide_rows": len([row for row in rows if row["arm"] == "fixed_guide_added"]),
        "all_subset_rows": len(rows),
        "actual_renderer_rejections": failures,
        "permitted_bound_violations": violations,
        "max_observed_summary_chars": max(
            result.get("maintainer_summary_chars", 0)
            for row in rows
            for result in row["decisions"].values()
        ),
        "prompts": prompt_rows,
        "subset_outcomes": rows,
    }
