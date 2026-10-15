"""Same fixed source condition for both fresh prompt-treatment identities."""

from agent_app.testing.enum_evidence import EnumEvidenceRejected
from agent_app.testing.enum_evidence import fixture_retriever_factory as fixed_factory

ARMS = ("current_selection", "complementary_selection")
EVIDENCE_CONDITION = "fixed_guide_added"


def fixture_retriever_factory(packet, fixtures, records):
    """Preserve trial identity while adapting the immutable parent's supplier.

    Only the trusted method selects the common condition. Neither source content
    nor query text can select an arm, change the fixed evidence or acquire future
    fixture messages. This supplier logs calls; it is not actual RAG search.
    """
    source_records = []
    fixed = fixed_factory(packet, fixtures, source_records)

    def supply(job, turn):
        if (
            type(job) is not dict
            or job.get("arm") not in ARMS
            or type(job.get("complementary_sources")) is not bool
            or job["complementary_sources"] != (job["arm"] == ARMS[1])
            or job.get("evidence_condition") != EVIDENCE_CONDITION
            or type(job.get("job_id")) is not str
            or not job["job_id"]
        ):
            raise EnumEvidenceRejected()
        # Capture only trusted scalar identity now; later caller mutation must
        # not relabel observations of an already bound source supplier.
        trial_identity = {
            "arm": job["arm"],
            "job_id": job["job_id"],
            "evidence_condition": EVIDENCE_CONDITION,
            "complementary_sources": job["complementary_sources"],
        }
        supplier, snapshot = fixed({**job, "arm": EVIDENCE_CONDITION}, turn)

        class TrialSupplier:
            def search(self, request):
                before = len(source_records)
                bundle = supplier.search(request)
                for observation in source_records[before:]:
                    records.append(
                        {
                            **observation,
                            **trial_identity,
                        }
                    )
                return bundle

        return TrialSupplier(), snapshot

    return supply
