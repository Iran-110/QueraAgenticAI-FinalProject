"""Uniform whole-record permutation through existing real HTTP/SQLite guards."""

import json

import httpx
import pytest
import test_enum_evidence as existing_acceptance

from agent_app.evaluation.runner import load_fixture
from agent_app.llm.config import MetisConfig
from agent_app.reasoning.source_selection import COMPLEMENTARY_SOURCE_POLICY
from agent_app.testing.enum_evidence import CASE_PATHS, PACKET_PATH, ROOT, load_source_packet
from agent_app.testing.enum_evidence import fixture_retriever_factory as original_factory
from agent_app.testing.source_order import fixture_retriever_factory as order_factory


@pytest.mark.parametrize("mode", ["original_order", "rotate_left_one"])
def test_uniform_order_keeps_current_sources_through_repair_correction_restart_and_retry(
    tmp_path, monkeypatch, mode
):
    original_config = existing_acceptance._config
    original_gateway = existing_acceptance.MetisGroundedPlanner
    bodies, logs = [], []
    packet = load_source_packet(ROOT / PACKET_PATH)
    fixtures = {case: load_fixture(ROOT / path) for case, path in CASE_PATHS.items()}
    fixed = original_factory(packet, fixtures, [])
    initial = fixtures["dev-case-c"].data["turns"][0]
    expected = existing_acceptance._retrieve(
        fixed, {"case_id": "dev-case-c", "arm": "fixed_guide_added"}, initial
    )
    expected_hits = [hit.model_dump(mode="json") for hit in expected.hits]
    rotated = expected_hits[1:] + expected_hits[:1] if mode == "rotate_left_one" else expected_hits

    def config():
        return MetisConfig.model_validate(
            {
                **original_config().model_dump(warnings=False),
                "grounded_source_selection_reminder": True,
                "grounded_complementary_sources": False,
            }
        )

    def factory(packet, fixtures, records):
        logs.append(records)
        supplied = order_factory(packet, fixtures, records)

        def adapt(job, turn):
            return supplied(
                {
                    **job,
                    "arm": mode,
                    "evidence_order": mode,
                    "evidence_condition": "fixed_guide_added",
                    "complementary_sources": False,
                    "job_id": "synthetic-order-sqlite",
                },
                turn,
            )

        return adapt

    class ObservedTransport(httpx.BaseTransport):
        def __init__(self, underlying):
            self.underlying = underlying

        def handle_request(self, request):
            body = json.loads(request.content)
            bodies.append(body)
            assert COMPLEMENTARY_SOURCE_POLICY not in body["messages"][0]["content"]
            payload = json.loads(body["messages"][1]["content"])
            hits = payload["request"]["evidence"]["hits"]
            assert hits == rotated
            assert sorted(json.dumps(h, sort_keys=True) for h in hits) == sorted(
                json.dumps(h, sort_keys=True) for h in expected_hits
            )
            assert payload["source_references"] == [
                {"source_index": i, "chunk_id": hit["chunk_id"]} for i, hit in enumerate(hits)
            ]
            return self.underlying.handle_request(request)

        def close(self):
            self.underlying.close()

    def gateway(configuration, ledger, *, transport):
        assert configuration.grounded_complementary_sources is False
        return original_gateway(configuration, ledger, transport=ObservedTransport(transport))

    monkeypatch.setattr(existing_acceptance, "_config", config)
    monkeypatch.setattr(existing_acceptance, "fixture_retriever_factory", factory)
    monkeypatch.setattr(existing_acceptance, "MetisGroundedPlanner", gateway)
    existing_acceptance.test_actual_http_gateway_keeps_complete_current_sources_and_rejects_old_approval(
        tmp_path, packet, fixtures, "fixed_guide_added"
    )
    assert len(bodies) == 4
    assert all(row["same_complete_record_set"] for group in logs for row in group)
    assert all(row["evidence_order"] == mode for group in logs for row in group)
    assert all(row["actual_search"] is False for group in logs for row in group)
