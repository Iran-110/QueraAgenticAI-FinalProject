"""Trusted named engine settings; no user/model-selected options or live authority."""


def validate_retrieval_profile(value, *, top_k=5):
    """Validate an exact registered profile before constructing a reasoning port."""
    if type(value) is not str or value not in {
        "native",
        "candidate_relevance_v1",
        "candidate_version_prefilter_v1",
    }:
        raise ValueError("RetrievalProfileInvalid")
    if value != "native" and (type(top_k) is not int or top_k != 5):
        raise ValueError("RetrievalProfileInvalid")
    return value


def retrieval_profile_options(value, *, top_k=5):
    """Return detached fixed policy; native preserves the exact legacy call shape.

    Candidate relevance is advice about the currently confirmed installation, so
    its exact USER-version scope overrides the application's comparison scope.
    The engine retains ownership of final limits and complete-record packing.
    """
    validate_retrieval_profile(value, top_k=top_k)
    if value == "native":
        return {}
    options = {
        "retrieval_candidate_multiplier": 5,
        "evidence_utf8_budget_bytes": 12000,
        "repair_repeated_queries": True,
        "evidence_scope": "exact_user_version",
    }
    if value == "candidate_version_prefilter_v1":
        options["retrieval_version_prefilter"] = True
    return options
