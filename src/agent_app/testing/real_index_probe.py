"""Run exposed development conversations with verified native Chroma retrieval.

The existing finite-scope model driver controls accounting and future fixture
turns. This module replaces only the retriever. Scripted answers, fixture bundles
and evaluator labels never become model evidence or source-selection filters.
"""

import hashlib
import re
from copy import deepcopy
from pathlib import Path

from agent_app.contracts import RetrievalRequest
from agent_app.retrieval.adapter import ChromaRetrieverAdapter
from agent_app.retrieval.offline_index import open_verified_index
from agent_app.retrieval.pilot_corpus import MANIFEST_NAME
from agent_app.retrieval.retriever import StreamlitRetriever
from agent_app.testing.quality_probe import run_quality_batch


class RealIndexProbeRejected(ValueError):
    def __init__(self):
        super().__init__("RealIndexProbeRejected")


class _IndexBinding:
    def __init__(self, registered):
        try:
            if type(registered) is not dict or set(registered) != {
                "path",
                "snapshot_id",
                "manifest_sha256",
            }:
                raise ValueError
            if (
                not isinstance(registered["manifest_sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", registered["manifest_sha256"]) is None
                or type(registered["snapshot_id"]) is not str
            ):
                raise ValueError
            self.path = Path(registered["path"]).resolve()
            self.snapshot_id = registered["snapshot_id"]
            self.manifest_sha256 = registered["manifest_sha256"]
            self._manifest_pin()
            self.client, snapshot = open_verified_index(self.path)
            if snapshot != self.snapshot_id:
                raise ValueError
            self.verify()
            corpus = self.client.manifest["corpus"]
            self.receipt = {
                "path": str(self.path),
                "snapshot_id": snapshot,
                "manifest_sha256": self.manifest_sha256,
                "protocol": corpus["protocol"],
                "embedding": deepcopy(corpus["config"]["embedding"]),
                "source_ids": [source["source_id"] for source in corpus["sources"]],
                "source_count": len(corpus["sources"]),
                "chunk_count": len(corpus["chunks"]),
                "source_pins": deepcopy(corpus["source_pins"]),
                "exclusions": deepcopy(corpus["exclusions"]),
            }
        except Exception:
            raise RealIndexProbeRejected() from None

    def _manifest_pin(self):
        if (
            hashlib.sha256((self.path / MANIFEST_NAME).read_bytes()).hexdigest()
            != self.manifest_sha256
        ):
            raise RealIndexProbeRejected()

    def verify(self):
        try:
            self._manifest_pin()
            self.client.verify()
        except Exception:
            raise RealIndexProbeRejected() from None


class _ObservedIndexedRetriever:
    def __init__(self, binding, job, turn, records):
        binding.verify()
        self.binding, self.job, self.turn, self.records = binding, job, turn, records
        self.round = 0
        self.adapter = ChromaRetrieverAdapter(
            "",
            snapshot_id=binding.snapshot_id,
            core_retriever=StreamlitRetriever(
                "", snapshot_id=binding.snapshot_id, client=binding.client
            ),
        )

    def search(self, request):
        self.round += 1
        record = {
            "job_id": self.job["job_id"],
            "arm": self.job["arm"],
            "case_id": self.job["case_id"],
            "turn_id": self.turn["id"],
            "logical_retrieval_round": self.round,
            "requested": None,
            "executed": None,
            "evidence": None,
            "error_code": None,
        }
        self.records.append(record)
        try:
            request = RetrievalRequest.model_validate(request.model_dump(warnings=False))
            if request.filters:
                # These model trials measure the ordinary unfiltered ranking.
                # Source/version-filtered membership checks belong to acceptance.
                raise RealIndexProbeRejected()
            record["requested"] = request.model_dump(mode="json")
            bounded = RetrievalRequest.model_validate(
                {**request.model_dump(), "top_k": min(5, request.top_k)}
            )
            record["executed"] = bounded.model_dump(mode="json")
            self.binding.verify()
            evidence = self.adapter.search(bounded)
            self.binding.verify()
            record["evidence"] = evidence.model_dump(mode="json")
            return evidence
        except Exception:
            record["error_code"] = "RealIndexRetrievalRejected"
            raise RealIndexProbeRejected() from None


def _validated_bindings(indexes):
    if (
        type(indexes) is not dict
        or not indexes
        or any(type(arm) is not str or not arm.strip() for arm in indexes)
    ):
        raise RealIndexProbeRejected()
    return {arm: _IndexBinding(registered) for arm, registered in indexes.items()}


def validate_index_bindings(indexes):
    """Verify native storage and pins before credentials or provider allocation."""
    return {
        arm: {
            "path": str(binding.path),
            "snapshot_id": binding.snapshot_id,
            "manifest_sha256": binding.manifest_sha256,
        }
        for arm, binding in _validated_bindings(indexes).items()
    }


def run_real_index_batch(
    protocol,
    batch,
    fixtures,
    definitions,
    ledger,
    config,
    before,
    indexes,
    *,
    underlying=None,
    checkpoint=None,
):
    """Preflight exact index bindings, then reuse the bounded HTTP model driver.

    Raw bundles are recorded before the engine's explicit exact-user-version
    scope. The actual enriched/post-scope GroundedRequest remains in attempts.
    Model routes and source support require a separate semantic review.
    """
    if (
        batch.get("kind") != "real_index"
        or type(indexes) is not dict
        or not indexes
        or type(batch.get("jobs")) is not list
        or not batch["jobs"]
        or any(
            type(job) is not dict
            or job.get("arm") not in indexes
            or "catalog_overrides" in job
            or "conflict_groups" in job
            for job in batch["jobs"]
        )
    ):
        raise RealIndexProbeRejected()
    # This runs before run_quality_batch creates any HTTP provider transport.
    bindings = _validated_bindings(indexes)
    index_receipts = {arm: deepcopy(binding.receipt) for arm, binding in bindings.items()}
    records = []

    def factory(job, turn):
        binding = bindings[job["arm"]]
        return _ObservedIndexedRetriever(binding, job, turn, records), binding.snapshot_id

    def observed_checkpoint(value):
        if checkpoint:
            checkpoint(
                {
                    **value,
                    "actual_retrievals": deepcopy(records),
                    "index_bindings": deepcopy(index_receipts),
                }
            )

    receipt = run_quality_batch(
        protocol,
        batch,
        fixtures,
        definitions,
        ledger,
        config,
        before,
        underlying=underlying,
        checkpoint=observed_checkpoint if checkpoint else None,
        retriever_factory=factory,
    )
    return {
        **receipt,
        "actual_retrievals": records,
        "index_bindings": index_receipts,
        "retrieval_mode": "verified_native_chroma_lexical_hash_top5_exact_user_version",
        "fixed_fixture_evidence_used": False,
        "held_out_test": False,
        "human_reviewed": False,
    }
