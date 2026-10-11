"""Mutation controls prove the reusable adapter protocol rejects real port defects."""

from decimal import Decimal

from agent_app.contracts import EvidenceBundle
from agent_app.testing import retrieval_acceptance as acceptance


class TransformingRetriever:
    def __init__(self, probe, transform):
        self.delegate = acceptance.fixture_factory(probe)
        self.transform = transform

    def search(self, request):
        return self.transform(self.delegate.search(request))


def transformed_factory(transform):
    def factory(probe):
        return TransformingRetriever(probe, transform)

    return factory


def rejected(factory, expected_check, *, include_pilot=False):
    receipt = acceptance.run_acceptance(factory, include_pilot=include_pilot)
    assert receipt["accepted"] is False
    assert receipt["checks"][expected_check] is False
    assert receipt["checks_passed"] < receipt["checks_total"]
    assert receipt["quality_claim"] is False
    assert receipt["production_index_or_embedding_tested"] is False
    assert receipt["real_model_tested"] is False
    assert receipt["actual_cost_usd"] == 0
    return receipt


def test_reference_and_transparent_factory_pass_same_port_checks_without_quality_claim():
    reference = acceptance.run_acceptance(include_pilot=False)
    wrapped = acceptance.run_acceptance(
        transformed_factory(lambda bundle: bundle), include_pilot=False
    )
    assert reference["accepted"] is wrapped["accepted"] is True
    assert reference["checks"] == wrapped["checks"]
    assert all(reference["checks"].values())
    assert reference["checks_passed"] == reference["checks_total"]
    assert reference["mode"] == "reference_fixture_adapter"
    assert wrapped["mode"] == "candidate_adapter_with_fixture_backend"
    assert reference["quality_claim"] is wrapped["quality_claim"] is False
    assert reference["production_index_or_embedding_tested"] is False
    assert reference["real_model_tested"] is False
    assert reference["actual_cost_usd"] == 0


def test_dynamic_factory_without_source_file_returns_inspectable_receipt():
    namespace = {"fixture_factory": acceptance.fixture_factory, "__name__": "dynamic_adapter"}
    exec(
        compile(
            "def factory(probe):\n    return fixture_factory(probe)\n",
            "<stdin>",
            "exec",
        ),
        namespace,
    )
    receipt = acceptance.run_acceptance(namespace["factory"], include_pilot=False)
    assert receipt["accepted"] is True
    assert receipt["factory"]["source_sha256"] is None
    assert receipt["factory"]["source_available"] is False
    assert receipt["factory"]["name"] == "factory"
    assert all(receipt["checks"].values())


def test_callable_factory_instance_is_supported_without_raw_inspection_errors():
    class CallableFactory:
        def __call__(self, probe):
            return acceptance.fixture_factory(probe)

    receipt = acceptance.run_acceptance(CallableFactory(), include_pilot=False)
    assert receipt["accepted"] is True
    assert receipt["factory"]["name"] == "CallableFactory"
    assert receipt["factory"]["source_sha256"] is not None
    assert receipt["factory"]["source_available"] is True
    assert all(receipt["checks"].values())


def test_reference_factory_composes_with_actual_sqlite_before_fault_controls():
    receipt = acceptance.run_acceptance()
    assert receipt["accepted"] is True
    assert all(case["status"] == "passed" for case in receipt["cases"])
    pilot = receipt["pilot"]
    assert len(pilot["turns"]) == 4
    assert pilot["total_retrieval_calls"] == pilot["total_scripted_reasoner_calls"] == 5
    assert pilot["adapter_constructions"] == 4
    assert pilot["checks"]["old_release_evidence_absent_from_current_handoff"] is True
    assert pilot["checks"]["old_event_replay_no_new_ports_or_actions"] is True
    assert pilot["quality_claim"] is pilot["held_out_test"] is False
    assert pilot["real_model_calls"] == 0
    assert Decimal(pilot["api_cost_usd"]) == 0


def test_alternative_hit_ranking_and_query_order_are_accepted():
    class ReverseRankRetriever:
        def __init__(self, probe):
            self.delegate = acceptance.fixture_factory(probe)

        def search(self, request):
            result = self.delegate.search(
                request.model_copy(update={"queries": tuple(reversed(request.queries))})
            )
            return result.model_copy(update={"hits": tuple(reversed(result.hits))})

    receipt = acceptance.run_acceptance(ReverseRankRetriever)
    assert receipt["accepted"] is True
    assert all(receipt["checks"].values())
    assert receipt["pilot"]["checks"]["refinement_consumes_two_queries_within_budget"] is True
    assert receipt["quality_claim"] is False


def test_valid_source_from_another_query_is_rejected_without_prescribing_ranking():
    fixture = acceptance.load_fixture()
    extra = next(
        hit for hit in fixture["hits"] if hit["chunk_id"] == "multiselect-149-signature-v8"
    )
    known_query = next(
        s["request"]["queries"]
        for s in fixture["scenarios"]
        if s["id"] == "known-version-release-source"
    )

    class CrossQuerySource:
        def __init__(self, probe):
            self.delegate = acceptance.fixture_factory(probe)

        def search(self, request):
            bundle = self.delegate.search(request)
            if request.queries == tuple(known_query):
                return bundle.model_copy(
                    update={
                        "hits": (acceptance.EvidenceHit.model_validate(extra),) + bundle.hits[1:]
                    }
                )
            return bundle

    rejected(CrossQuerySource, "known_version:metadata")


def test_dropping_existing_commit_and_locator_is_rejected():
    def drop_metadata(bundle):
        return bundle.model_copy(
            update={
                "hits": tuple(
                    hit.model_copy(update={"source_commit": None, "source_span": None})
                    for hit in bundle.hits
                )
            }
        )

    rejected(transformed_factory(drop_metadata), "single:metadata")


def test_consuming_only_first_query_is_rejected():
    class FirstQueryOnly:
        def __init__(self, probe):
            self.delegate = acceptance.fixture_factory(probe)

        def search(self, request):
            return self.delegate.search(request.model_copy(update={"queries": request.queries[:1]}))

    rejected(FirstQueryOnly, "multi:queries_consumed")


def test_duplicate_chunk_ids_are_rejected_at_bundle_validation():
    def duplicate(bundle):
        if bundle.hits:
            return bundle.model_copy(update={"hits": (*bundle.hits, bundle.hits[0])})
        return bundle

    receipt = rejected(transformed_factory(duplicate), "multi:completed")
    case = next(case for case in receipt["cases"] if case["id"] == "multi")
    assert case == {
        "id": "multi",
        "status": "failed",
        "error_code": "AdapterAcceptanceFailed",
    }


def test_ignoring_requested_global_cap_is_rejected():
    class UnboundedRetriever:
        def __init__(self, probe):
            self.delegate = acceptance.fixture_factory(probe)

        def search(self, request):
            return self.delegate.search(request.model_copy(update={"top_k": 50}))

    rejected(UnboundedRetriever, "cap:global_top_k")


def test_reported_snapshot_drift_is_rejected():
    rejected(
        transformed_factory(
            lambda bundle: bundle.model_copy(update={"snapshot_id": "unrelated-snapshot"})
        ),
        "single:snapshot",
    )


def test_inventing_version_for_unknown_metadata_is_rejected():
    def invent_version(bundle):
        return bundle.model_copy(
            update={
                "hits": tuple(
                    hit.model_copy(update={"applicable_versions": ("1.50.0",)})
                    if not hit.applicable_versions
                    else hit
                    for hit in bundle.hits
                )
            }
        )

    rejected(transformed_factory(invent_version), "unknown:metadata")


def test_valid_but_changed_excerpt_is_rejected_by_content_oracle():
    def change_quote(bundle):
        return bundle.model_copy(
            update={
                "hits": tuple(
                    hit.model_copy(update={"excerpt": hit.excerpt[:-1]}) for hit in bundle.hits
                )
            }
        )

    rejected(transformed_factory(change_quote), "boundary:exact_excerpt")


def test_boundary_source_origin_and_unknown_version_cannot_be_rewritten():
    def change_boundary_origin(bundle):
        return bundle.model_copy(
            update={
                "hits": tuple(
                    hit.model_copy(
                        update={
                            "source_url": "https://example.org/unrelated-origin",
                            "source_id": "unrelated-origin",
                            "source_commit": "invented-commit",
                            "applicable_versions": ("1.50.0",),
                        }
                    )
                    if hit.chunk_id == "synthetic:excerpt-boundary"
                    else hit
                    for hit in bundle.hits
                )
            }
        )

    rejected(transformed_factory(change_boundary_origin), "boundary:exact_excerpt")


def test_silent_clipping_of_oversized_backend_record_is_rejected():
    def clipping_factory(probe):
        original = probe.backend.search

        def clipped_search(query, *, top_k, filters=None):
            rows = original(query, top_k=top_k, filters=filters)
            return [{**row, "excerpt": row["excerpt"][:20_000]} for row in rows]

        probe.backend.search = clipped_search
        return acceptance.fixture_factory(probe)

    rejected(clipping_factory, "oversize:stop_before_model")


def test_backend_failure_cannot_be_swallowed_as_empty_success():
    class SwallowingRetriever:
        def __init__(self, probe):
            self.delegate = acceptance.fixture_factory(probe)
            self.snapshot_id = probe.snapshot_id

        def search(self, request):
            try:
                return self.delegate.search(request)
            except Exception:
                return EvidenceBundle(snapshot_id=self.snapshot_id, queries_used=request.queries)

    receipt = rejected(SwallowingRetriever, "failure:stop_before_model")
    assert acceptance.PRIVATE_SENTINEL not in str(receipt)


def test_reusing_first_bundle_on_refinement_fails_actual_sqlite_pilot():
    class CachedFirstRetriever:
        def __init__(self, probe):
            self.delegate = acceptance.fixture_factory(probe)
            self.first = None

        def search(self, request):
            current = self.delegate.search(request)
            if self.first is None:
                self.first = current
                return current
            return current.model_copy(update={"hits": self.first.hits})

    receipt = rejected(CachedFirstRetriever, "core_pilot:completed", include_pilot=True)
    assert all(
        case["status"] == "passed" for case in receipt["cases"] if case["id"] != "core_pilot"
    )
    assert receipt["cases"][-1] == {
        "id": "core_pilot",
        "status": "failed",
        "error_code": "AdapterAcceptanceFailed",
    }
