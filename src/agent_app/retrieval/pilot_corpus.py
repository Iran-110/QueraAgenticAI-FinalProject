"""A bounded, hash-pinned documentation corpus; never a final evaluation split."""

import hashlib
import json
import math
import re
import struct
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from agent_app.contracts import EvidenceHit

PROTOCOL = "docs-only-local-pilot-v1"
DEV_COVERAGE_PROTOCOL = "docs-only-dev-coverage-v1"
DOCS_COMMIT = "695e6ce2fb1b23afc6df66b40420ab0013ad72fd"
MARKDOWN_SOURCE_IDS = frozenset(
    {
        "docs:content/develop/concepts/architecture/session-state.md",
        "docs:content/develop/concepts/architecture/widget-behavior.md",
        "docs:content/develop/api-reference/caching-and-state/session_state.md",
        "docs:content/develop/api-reference/widgets/button.md",
        "docs:content/develop/api-reference/widgets/text_input.md",
    }
)
API_VERSIONS = frozenset({"1.49.0", "1.50.0", "1.64.0"})
API_FUNCTIONS = frozenset({"streamlit.button", "streamlit.rerun", "streamlit.text_input"})
_SOURCE_IDS = MARKDOWN_SOURCE_IDS | {
    f"docstring:{version}:{function}" for version in API_VERSIONS for function in API_FUNCTIONS
}
# A separate closed profile adds four existing official seed records. These are
# explicit identities, not a larger Cartesian version/function matrix.
DEV_COVERAGE_SOURCE_PINS = {
    "docstring:1.39.0:streamlit.button": {
        "text_sha256": "348e29001cbb5d5a31a59a546e06555ea8f3fd11a4ccda070709105e8fae3482",
        "characters": 2698,
        "canonical_source_url": "https://docs.streamlit.io/develop/api-reference/widgets/st.button",
    },
    "docstring:1.50.0:streamlit.fragment": {
        "text_sha256": "f5186d0216ca2932aeb2ead36999ede476cc57acbcf36389d859b3e70fb12772",
        "characters": 2352,
        "canonical_source_url": "https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment",
    },
    "docstring:1.49.0:streamlit.multiselect": {
        "text_sha256": "070b426e56bd72a0e19ba8ccc5c3282d26f95b5212adfee37f3fde31acb7bc76",
        "characters": 4832,
        "canonical_source_url": "https://docs.streamlit.io/develop/api-reference/widgets/st.multiselect",
    },
    "docstring:1.50.0:streamlit.multiselect": {
        "text_sha256": "070b426e56bd72a0e19ba8ccc5c3282d26f95b5212adfee37f3fde31acb7bc76",
        "characters": 4832,
        "canonical_source_url": "https://docs.streamlit.io/develop/api-reference/widgets/st.multiselect",
    },
}
DEV_COVERAGE_REQUIRED_ISSUE_IDS = frozenset(
    {
        268,
        1085,
        1155,
        1185,
        1644,
        2069,
        2379,
        2584,
        3533,
        3854,
        4164,
        4256,
        4884,
        5305,
        5368,
        5498,
        6320,
        8061,
        8129,
        8180,
        8901,
        9031,
        9259,
        9342,
        9455,
        9770,
        10089,
        10102,
        11012,
        11115,
        12396,
        12506,
        12629,
        12782,
        13147,
        13953,
        14717,
        16242,
        16281,
        16661,
        16727,
        16732,
        16914,
        17030,
        17112,
        17215,
    }
)
# Final profile: every seed scope page (product docs and release notes) and every
# versioned API record, pinned by count and a hash of the sorted identity list.
# Issues, comments, outcomes and answer-linked documents never enter it.
FINAL_PROTOCOL = "docs-api-release-final-v1"
RELEASE_NOTES_PREFIX = "content/develop/quick-references/release-notes/"
ALWAYS_DENIED_DOCUMENT_PATHS = frozenset({"content/develop/concepts/app-design/custom-classes.md"})
FINAL_SOURCE_COUNT = 1228
FINAL_SOURCE_SET_SHA256 = "a3866f33a4944bd3ef6faf23e6bb867adda471977fa04291355b80fae2968b16"
_FINAL_EXCLUDED = {"issue", "comment", "evaluation", "fixture"}
_API_FUNCTION = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*\Z")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
CHUNK_CHARACTERS = 4_000
EMBEDDING_DIMENSIONS = 256
COLLECTION_NAMES = ("streamlit_docs", "streamlit_issues")
MANIFEST_NAME = "pilot-manifest.json"
_EXCLUDED = {"issue", "comment", "release_note", "evaluation", "fixture"}
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_PACKAGE_PATHS = {
    "START_HERE.fa.txt",
    "development_exposure.json",
    "schemas.json",
    "sources/data_inventory.md",
    "sources/docs_catalog.jsonl",
    "sources/docs_issue_links.json",
    "sources/docs_manifest.json",
    "sources/docs_scope_candidates.jsonl",
    "sources/docstrings_scope_candidates.jsonl",
    "sources/github-snapshot-2026-10-06/catalog/comment_records.jsonl",
    "sources/github-snapshot-2026-10-06/catalog/family_review_candidates.json",
    "sources/github-snapshot-2026-10-06/catalog/issue_records.jsonl",
    "sources/github-snapshot-2026-10-06/profile.json",
    "sources/github-snapshot-2026-10-06/selection.json",
}


class PilotCorpusRejected(ValueError):
    """A fixed diagnostic, without source text or filesystem details."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lexical_embedding(text: str) -> list[float]:
    """v1: casefolded Unicode word counts in unsigned SHA-256 buckets, L2 normalized.

    Persist float32 values explicitly. This inexpensive lexical projection exercises
    real index operations offline; it makes no semantic retrieval-quality claim.
    """
    vector = [0.0] * EMBEDDING_DIMENSIONS
    tokens = re.findall(r"\w+", text.casefold()) or ["<empty>"]
    for token in tokens:
        bucket = int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:8], "big")
        vector[bucket % EMBEDDING_DIMENSIONS] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return list(struct.unpack("<256f", struct.pack("<256f", *(value / norm for value in vector))))


def embedding_sha256(vector: list[float]) -> str:
    return sha256(struct.pack("<256f", *vector))


@dataclass(frozen=True)
class PilotCorpus:
    """Immutable canonical serialization; callers receive detached manifest views."""

    snapshot_id: str
    _payload_json: str

    @property
    def manifest(self) -> dict[str, Any]:
        return {"snapshot_id": self.snapshot_id, "corpus": json.loads(self._payload_json)}

    @classmethod
    def from_manifest(cls, manifest: dict[str, Any]) -> "PilotCorpus":
        try:
            payload = manifest["corpus"]
            encoded = canonical_json(payload)
            snapshot = "docs-pilot-" + sha256(encoded.encode("utf-8"))
            if manifest["snapshot_id"] != snapshot:
                raise ValueError
            final = payload["protocol"] == FINAL_PROTOCOL
            if not final:
                _profile_source_ids(payload["protocol"])
            if payload["schema_version"] != 1:
                raise ValueError
            if payload["config"] != {
                "chunk_characters": CHUNK_CHARACTERS,
                "embedding": {
                    "kind": "lexical_hash_v1",
                    "dimensions": EMBEDDING_DIMENSIONS,
                    "quality_claim": False,
                },
                "collection_names": list(COLLECTION_NAMES),
            }:
                raise ValueError
            chunks = payload["chunks"]
            if not chunks or len({chunk["chunk_id"] for chunk in chunks}) != len(chunks):
                raise ValueError
            for chunk in chunks:
                document = chunk["document"]
                metadata = chunk["metadata"]
                if not isinstance(document, str) or not 0 < len(document) <= CHUNK_CHARACTERS:
                    raise ValueError
                if sha256(document.encode("utf-8")) != chunk["text_sha256"]:
                    raise ValueError
                if embedding_sha256(lexical_embedding(document)) != chunk["embedding_sha256"]:
                    raise ValueError
                allowed_types = {"doc", "release_note"} if final else {"doc"}
                if (
                    metadata["source_type"] not in allowed_types
                    or metadata["chunk_id"] != chunk["chunk_id"]
                ):
                    raise ValueError
                if chunk["span"]["end"] - chunk["span"]["start"] != len(document):
                    raise ValueError
                if chunk["span"]["unit"] != "unicode_codepoint":
                    raise ValueError
                _validate_hit(document, metadata)
            if final:
                _validate_final_sources(payload)
            else:
                _validate_sources(payload)
        except (KeyError, TypeError, ValueError):
            raise PilotCorpusRejected("PilotManifestRejected") from None
        return cls(snapshot, encoded)


def _validate_hit(document: str, metadata: dict[str, Any]) -> None:
    EvidenceHit(
        chunk_id=metadata["chunk_id"],
        source_id=metadata["source_id"],
        excerpt=document,
        source_url=metadata["source_url"],
        source_type=metadata["source_type"],
        source_commit=metadata["source_commit"],
        source_span=metadata["source_span"],
        applicable_versions=tuple(json.loads(metadata["applicable_versions"])),
    )


def _chunk_id(source: dict[str, Any], start: int, end: int, chunk_sha: str) -> str:
    identity = sha256(canonical_json(source).encode("utf-8"))
    version = source["applicable_versions"][0] if source["applicable_versions"] else "pinned"
    return f"doc:{version}:{identity[:24]}:{start}:{end}:{chunk_sha[:16]}"


def _profile_source_ids(protocol: str) -> frozenset[str]:
    if protocol == PROTOCOL:
        return _SOURCE_IDS
    if protocol == DEV_COVERAGE_PROTOCOL:
        return _SOURCE_IDS | frozenset(DEV_COVERAGE_SOURCE_PINS)
    raise ValueError


def _validate_sources(payload: dict[str, Any]) -> None:
    sources = payload["sources"]
    pins = payload["source_pins"]
    expected_ids = _profile_source_ids(payload["protocol"])
    if (
        len(sources) != len(expected_ids)
        or {source["source_id"] for source in sources} != expected_ids
    ):
        raise ValueError
    if pins["docs_commit"] != DOCS_COMMIT:
        raise ValueError
    for key in (
        "package_manifest_sha256",
        "allowlist_sha256",
        "split_manifest_sha256",
        "development_exposure_sha256",
    ):
        if not _SHA.fullmatch(pins[key]):
            raise ValueError
    packaged = pins["packaged_files"]
    if len(packaged) != len(_PACKAGE_PATHS) or {pin["path"] for pin in packaged} != _PACKAGE_PATHS:
        raise ValueError
    for pin in packaged:
        if type(pin["bytes"]) is not int or pin["bytes"] < 0 or not _SHA.fullmatch(pin["sha256"]):
            raise ValueError
    chunks_by_source: dict[str, list[dict[str, Any]]] = {
        source["source_id"]: [] for source in sources
    }
    for chunk in payload["chunks"]:
        chunks_by_source[chunk["metadata"]["source_id"]].append(chunk)
    origins = []
    versions = set()
    for source in sources:
        if payload["protocol"] == DEV_COVERAGE_PROTOCOL:
            frozen = DEV_COVERAGE_SOURCE_PINS.get(source["source_id"], {})
            if any(source[key] != value for key, value in frozen.items()):
                raise ValueError
        if source["source_commit"] != pins["docs_commit"]:
            raise ValueError
        origins.append(source["origin_kind"])
        source_versions = source["applicable_versions"]
        if source["origin_kind"] == "docs_markdown":
            if source_versions or source["source_id"] != "docs:" + source["source_pointer"]:
                raise ValueError
            file = source["source_pointer"]
        elif source["origin_kind"] == "docs_generated":
            if len(source_versions) != 1:
                raise ValueError
            version = source_versions[0]
            versions.add(version)
            pointer = source["source_pointer"]
            if not pointer.startswith("python/streamlit.json/" + version + "/streamlit."):
                raise ValueError
            function = pointer.rsplit("/", 1)[1]
            if source["source_id"] != f"docstring:{version}:{function}":
                raise ValueError
            file = "python/streamlit.json"
        else:
            raise ValueError
        if (
            source["source_url"]
            != f"https://github.com/streamlit/docs/blob/{pins['docs_commit']}/{file}"
        ):
            raise ValueError
        position = 0
        text = []
        for chunk in chunks_by_source[source["source_id"]]:
            span = chunk["span"]
            if type(span["start"]) is not int or type(span["end"]) is not int:
                raise ValueError
            if span["start"] != position or span["end"] <= position:
                raise ValueError
            metadata = chunk["metadata"]
            for key in (
                "origin_kind",
                "source_commit",
                "source_url",
                "canonical_source_url",
                "source_pointer",
            ):
                if metadata[key] != source[key]:
                    raise ValueError
            if metadata["source_text_sha256"] != source["text_sha256"]:
                raise ValueError
            if metadata["chunk_text_sha256"] != chunk["text_sha256"]:
                raise ValueError
            if metadata["source_span"] != f"chars:{position}:{span['end']};unit:unicode_codepoint":
                raise ValueError
            if metadata["applicable_versions"] != canonical_json(source_versions):
                raise ValueError
            if source_versions and metadata.get("version") != source_versions[0]:
                raise ValueError
            if not source_versions and "version" in metadata:
                raise ValueError
            if chunk["chunk_id"] != _chunk_id(source, position, span["end"], chunk["text_sha256"]):
                raise ValueError
            position = span["end"]
            text.append(chunk["document"])
        if (
            position != source["characters"]
            or sha256("".join(text).encode("utf-8")) != source["text_sha256"]
        ):
            raise ValueError
    if (
        origins.count("docs_markdown") != 5
        or origins.count("docs_generated") != len(expected_ids) - 5
        or versions
        != (
            API_VERSIONS | {"1.39.0"}
            if payload["protocol"] == DEV_COVERAGE_PROTOCOL
            else API_VERSIONS
        )
    ):
        raise ValueError
    exclusions = payload["exclusions"]
    if (
        exclusions["split_status"] != "draft_not_frozen"
        or exclusions["family_review_complete"] is not False
        or exclusions["indexed_issue_count"] != 0
        or exclusions["indexed_comment_count"] != 0
        or not exclusions["reserved_issue_ids"]
    ):
        raise ValueError
    if payload["protocol"] == DEV_COVERAGE_PROTOCOL:
        reserved = exclusions["reserved_issue_ids"]
        if (
            any(type(number) is not int or number <= 0 for number in reserved)
            or len(set(reserved)) != len(reserved)
            or not DEV_COVERAGE_REQUIRED_ISSUE_IDS <= set(reserved)
        ):
            raise ValueError


def _read_json(path: Path) -> tuple[Any, bytes]:
    raw = path.read_bytes()
    return json.loads(raw), raw


def _package(seed: Path) -> tuple[dict[str, Any], dict[str, bytes], dict[str, Any]]:
    manifest, raw = _read_json(seed / "manifest.json")
    packaged: dict[str, bytes] = {}
    pins = []
    for entry in manifest["files"]:
        relative = PurePosixPath(entry["path"])
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError
        name = relative.as_posix()
        path = seed / name
        if path.resolve().is_relative_to(seed.resolve()) is False or name in packaged:
            raise ValueError
        content = path.read_bytes()
        if len(content) != entry["bytes"] or sha256(content) != entry["sha256"]:
            raise ValueError
        packaged[name] = content
        pins.append({"path": name, "bytes": len(content), "sha256": sha256(content)})
    if set(packaged) != _PACKAGE_PATHS:
        raise ValueError
    return (
        manifest,
        packaged,
        {
            "package_manifest_sha256": sha256(raw),
            "packaged_files": sorted(pins, key=lambda pin: pin["path"]),
        },
    )


def _allowlist(value: dict[str, Any]) -> None:
    _profile_source_ids(value["protocol"])
    if (
        value["docs_commit"] != DOCS_COMMIT
        or value["chunk_characters"] != CHUNK_CHARACTERS
        or value["embedding"]
        != {"kind": "lexical_hash_v1", "dimensions": EMBEDDING_DIMENSIONS, "quality_claim": False}
        or value["collection_names"] != list(COLLECTION_NAMES)
        or set(value["excluded_source_types"]) != _EXCLUDED
        or len(value["excluded_source_types"]) != len(_EXCLUDED)
    ):
        raise ValueError
    for key, expected in (
        ("markdown_source_ids", MARKDOWN_SOURCE_IDS),
        ("api_versions", API_VERSIONS),
        ("api_functions", API_FUNCTIONS),
    ):
        values = value[key]
        if len(values) != len(expected) or set(values) != expected:
            raise ValueError
    if value["protocol"] == DEV_COVERAGE_PROTOCOL:
        for key, expected in (
            ("additional_api_source_ids", DEV_COVERAGE_SOURCE_PINS.keys()),
            ("required_reserved_issue_ids", DEV_COVERAGE_REQUIRED_ISSUE_IDS),
        ):
            values = value[key]
            if len(values) != len(expected) or set(values) != expected:
                raise ValueError
    elif "additional_api_source_ids" in value or "required_reserved_issue_ids" in value:
        # An extended allowlist cannot silently become the historical profile.
        raise ValueError


def _exclusions(split: dict[str, Any], exposure: dict[str, Any]) -> dict[str, Any]:
    if split["schema_version"] != 1 or split["status"] != "draft_not_frozen":
        raise ValueError
    if exposure["independent_final_test_eligible"] is not False:
        raise ValueError
    if exposure["exclude_from_rag_corpus_with_reviewed_family"] is not True:
        raise ValueError
    numbers = set(exposure["issue_numbers"])
    reserved = set(split["exposure_reserved_issue_ids"])
    families = {number for family in split["families"] for number in family["issue_ids"]}
    if not numbers or not numbers <= reserved or not families <= reserved:
        raise ValueError
    if any(type(number) is not int or number <= 0 for number in reserved):
        raise ValueError
    return {
        "split_manifest_id": split["manifest_id"],
        "split_status": split["status"],
        "reserved_issue_ids": sorted(reserved),
        "family_review_complete": False,
        "indexed_issue_count": 0,
        "indexed_comment_count": 0,
        "policy": "documentation allowlist only; all issues, comments and outcomes excluded",
    }


def _selected(raw: bytes, wanted: set[str], *, origin: str, commit: str) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for line in raw.decode("utf-8").splitlines():
        record = json.loads(line)
        if record["source_id"] not in wanted:
            continue
        source_id = record["source_id"]
        text = record["text"]
        text_hash = sha256(text.encode("utf-8"))
        if source_id in seen or record["type"] != origin or record["docs_commit"] != commit:
            raise ValueError
        if not text.strip():
            raise ValueError
        if origin == "docs_markdown":
            pointer = record["file"]
            if source_id != "docs:" + pointer or len(text.encode("utf-8")) != record["bytes"]:
                raise ValueError
            if record["sha256"] != text_hash:
                raise ValueError
            versions = []
        else:
            pointer = "python/streamlit.json" + record["json_pointer"]
            versions = [record["version"]]
            if source_id != f"docstring:{record['version']}:{record['function']}":
                raise ValueError
            if record["json_pointer"] != f"/{record['version']}/{record['function']}":
                raise ValueError
            if record["text_sha256"] != text_hash:
                raise ValueError
        file = record["file"] if origin == "docs_markdown" else "python/streamlit.json"
        pinned_url = f"https://github.com/streamlit/docs/blob/{commit}/{file}"
        if record["pinned_source_url"] != pinned_url or not _SHA.fullmatch(text_hash):
            raise ValueError
        result.append(
            {
                "source_id": source_id,
                "origin_kind": origin,
                "source_commit": commit,
                "source_url": pinned_url,
                "canonical_source_url": record["source_url"],
                "source_pointer": pointer,
                "applicable_versions": versions,
                "text_sha256": text_hash,
                "characters": len(text),
                "text": text,
            }
        )
        seen.add(source_id)
    if seen != wanted:
        raise ValueError
    return result


def build_pilot_corpus(
    seed_root: str | Path, split_manifest: str | Path, allowlist_path: str | Path
) -> PilotCorpus:
    """Verify the seed package and ingest one explicit closed documentation profile."""
    try:
        seed = Path(seed_root)
        allowlist, allowlist_raw = _read_json(Path(allowlist_path))
        _allowlist(allowlist)
        package, files, pins = _package(seed)
        if package["docs_commit"] != allowlist["docs_commit"]:
            raise ValueError
        docs_manifest = json.loads(files["sources/docs_manifest.json"])
        if docs_manifest["commit"] != allowlist["docs_commit"]:
            raise ValueError
        split, split_raw = _read_json(Path(split_manifest))
        exposure = json.loads(files["development_exposure.json"])
        exclusions = _exclusions(split, exposure)
        if allowlist["protocol"] == DEV_COVERAGE_PROTOCOL:
            if not DEV_COVERAGE_REQUIRED_ISSUE_IDS <= set(exclusions["reserved_issue_ids"]):
                raise ValueError
        pins.update(
            {
                "allowlist_sha256": sha256(allowlist_raw),
                "split_manifest_sha256": sha256(split_raw),
                "development_exposure_sha256": sha256(files["development_exposure.json"]),
                "docs_commit": allowlist["docs_commit"],
            }
        )
        api_ids = set(_profile_source_ids(allowlist["protocol"]) - MARKDOWN_SOURCE_IDS)
        sources = _selected(
            files["sources/docs_scope_candidates.jsonl"],
            set(allowlist["markdown_source_ids"]),
            origin="docs_markdown",
            commit=allowlist["docs_commit"],
        ) + _selected(
            files["sources/docstrings_scope_candidates.jsonl"],
            api_ids,
            origin="docs_generated",
            commit=allowlist["docs_commit"],
        )
        sources.sort(key=lambda source: source["source_id"])
        chunks = []
        for source in sources:
            text = source["text"]
            version = (
                source["applicable_versions"][0] if source["applicable_versions"] else "pinned"
            )
            for start in range(0, len(text), CHUNK_CHARACTERS):
                end = min(len(text), start + CHUNK_CHARACTERS)
                document = text[start:end]
                chunk_sha = sha256(document.encode("utf-8"))
                chunk_id = _chunk_id(
                    {key: value for key, value in source.items() if key != "text"},
                    start,
                    end,
                    chunk_sha,
                )
                span = {"start": start, "end": end, "unit": "unicode_codepoint"}
                metadata = {
                    "chunk_id": chunk_id,
                    "source_id": source["source_id"],
                    "source_type": "doc",
                    "origin_kind": source["origin_kind"],
                    "source_commit": source["source_commit"],
                    "source_url": source["source_url"],
                    "canonical_source_url": source["canonical_source_url"],
                    "source_pointer": source["source_pointer"],
                    "source_span": f"chars:{start}:{end};unit:unicode_codepoint",
                    "source_text_sha256": source["text_sha256"],
                    "chunk_text_sha256": chunk_sha,
                    "applicable_versions": canonical_json(source["applicable_versions"]),
                }
                if source["applicable_versions"]:
                    metadata["version"] = version
                _validate_hit(document, metadata)
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "document": document,
                        "metadata": metadata,
                        "span": span,
                        "text_sha256": chunk_sha,
                        "embedding_sha256": embedding_sha256(lexical_embedding(document)),
                    }
                )
        payload = {
            "schema_version": 1,
            "protocol": allowlist["protocol"],
            "scope": allowlist["scope"],
            "config": {
                key: allowlist[key] for key in ("chunk_characters", "embedding", "collection_names")
            },
            "source_pins": pins,
            "exclusions": exclusions,
            "sources": [
                {key: value for key, value in source.items() if key != "text"} for source in sources
            ],
            "chunks": chunks,
        }
        encoded = canonical_json(payload)
        return PilotCorpus.from_manifest(
            {"snapshot_id": "docs-pilot-" + sha256(encoded.encode("utf-8")), "corpus": payload}
        )
    except (OSError, UnicodeError, KeyError, TypeError, ValueError):
        raise PilotCorpusRejected("PilotCorpusRejected") from None


# --- Final profile: docs + release notes + versioned API records -----------------


def _final_source_type(origin: str, pointer: str) -> str:
    if origin == "docs_markdown" and pointer.startswith(RELEASE_NOTES_PREFIX):
        return "release_note"
    return "doc"


def _final_source_set_sha256(source_ids) -> str:
    return sha256(canonical_json(sorted(source_ids)).encode("utf-8"))


def _normalized_url(value: str) -> str:
    return value.strip().rstrip("/").casefold()


def _final_allowlist(value: dict[str, Any]) -> tuple[set[str], set[str]]:
    """Return (markdown ids, api ids) after checking the closed final selection."""
    if (
        value["protocol"] != FINAL_PROTOCOL
        or value["docs_commit"] != DOCS_COMMIT
        or value["chunk_characters"] != CHUNK_CHARACTERS
        or value["embedding"]
        != {"kind": "lexical_hash_v1", "dimensions": EMBEDDING_DIMENSIONS, "quality_claim": False}
        or value["collection_names"] != list(COLLECTION_NAMES)
        or len(value["excluded_source_types"]) != len(_FINAL_EXCLUDED)
        or set(value["excluded_source_types"]) != _FINAL_EXCLUDED
        or not isinstance(value["scope"], str)
        or not value["scope"].strip()
        or not isinstance(value["selection_policy"], str)
        or not value["selection_policy"].strip()
    ):
        raise ValueError
    markdown, release, api = (
        value["markdown_source_ids"],
        value["release_note_source_ids"],
        value["api_source_ids"],
    )
    for values in (markdown, release, api):
        if not isinstance(values, list) or len(set(values)) != len(values):
            raise ValueError
    denied = set(value["denied_document_paths"])
    if not ALWAYS_DENIED_DOCUMENT_PATHS <= denied:
        raise ValueError
    for source_id in markdown:
        if not source_id.startswith("docs:content/") or source_id[5:] in denied:
            raise ValueError
    expected_release = {s for s in markdown if s[5:].startswith(RELEASE_NOTES_PREFIX)}
    if set(release) != expected_release or not release:
        raise ValueError
    for source_id in api:
        parts = source_id.split(":")
        if (
            len(parts) != 3
            or parts[0] != "docstring"
            or not _VERSION.fullmatch(parts[1])
            or not _API_FUNCTION.fullmatch(parts[2])
        ):
            raise ValueError
    every = set(markdown) | set(api)
    if (
        len(every) != FINAL_SOURCE_COUNT
        or _final_source_set_sha256(every) != FINAL_SOURCE_SET_SHA256
    ):
        raise ValueError
    return set(markdown), set(api)


def _final_exclusions(
    exclusion: dict[str, Any], exposure: dict[str, Any], denied: set[str]
) -> dict[str, Any]:
    if exclusion["schema_version"] != 1 or exclusion["exclusion_id"] != "final-index-exclusion":
        raise ValueError
    ids = exclusion["issue_ids"]
    if (
        not ids
        or any(type(number) is not int or number <= 0 for number in ids)
        or ids != sorted(set(ids))
    ):
        raise ValueError
    # Every development-exposed and historically reserved Issue stays excluded.
    if not set(exposure["issue_numbers"]) <= set(ids):
        raise ValueError
    if not DEV_COVERAGE_REQUIRED_ISSUE_IDS <= set(ids):
        raise ValueError
    documents = exclusion["direct_answer_documents"]
    if not isinstance(documents, list) or not ALWAYS_DENIED_DOCUMENT_PATHS <= set(documents):
        raise ValueError
    if not {d for d in documents if not d.startswith("http")} <= denied:
        raise ValueError
    for key in ("source_manifest", "source_manifest_id", "source_manifest_status"):
        if not isinstance(exclusion[key], str) or not exclusion[key].strip():
            raise ValueError
    if not _SHA.fullmatch(exclusion["source_manifest_sha256"]):
        raise ValueError
    return {
        "policy": (
            "docs, release notes and versioned API records only; every listed Issue, "
            "its comments and outcomes, and direct-answer documents excluded"
        ),
        "split_manifest_id": exclusion["source_manifest_id"],
        "split_status": exclusion["source_manifest_status"],
        "split_manifest_sha256": exclusion["source_manifest_sha256"],
        "reserved_issue_ids": list(ids),
        "direct_answer_documents": list(documents),
        "indexed_issue_count": 0,
        "indexed_comment_count": 0,
    }


def _validate_final_sources(payload: dict[str, Any]) -> None:
    sources = payload["sources"]
    pins = payload["source_pins"]
    exclusions = payload["exclusions"]
    ids = [source["source_id"] for source in sources]
    if (
        len(set(ids)) != len(ids)
        or len(ids) != FINAL_SOURCE_COUNT
        or _final_source_set_sha256(ids) != FINAL_SOURCE_SET_SHA256
        or ids != sorted(ids)
    ):
        raise ValueError
    if pins["docs_commit"] != DOCS_COMMIT:
        raise ValueError
    for key in (
        "package_manifest_sha256",
        "allowlist_sha256",
        "exclusion_manifest_sha256",
        "split_manifest_sha256",
        "development_exposure_sha256",
    ):
        if not _SHA.fullmatch(pins[key]):
            raise ValueError
    packaged = pins["packaged_files"]
    if len(packaged) != len(_PACKAGE_PATHS) or {pin["path"] for pin in packaged} != _PACKAGE_PATHS:
        raise ValueError
    for pin in packaged:
        if type(pin["bytes"]) is not int or pin["bytes"] < 0 or not _SHA.fullmatch(pin["sha256"]):
            raise ValueError
    denied = {
        _normalized_url(document) if document.startswith("http") else document
        for document in exclusions["direct_answer_documents"]
    }
    if not ALWAYS_DENIED_DOCUMENT_PATHS <= denied:
        raise ValueError
    if (
        exclusions["indexed_issue_count"] != 0
        or exclusions["indexed_comment_count"] != 0
        or exclusions["split_manifest_sha256"] != pins["split_manifest_sha256"]
        or not DEV_COVERAGE_REQUIRED_ISSUE_IDS <= set(exclusions["reserved_issue_ids"])
    ):
        raise ValueError
    chunks_by_source: dict[str, list[dict[str, Any]]] = {source_id: [] for source_id in ids}
    for chunk in payload["chunks"]:
        chunks_by_source[chunk["metadata"]["source_id"]].append(chunk)
    for source in sources:
        if source["source_commit"] != pins["docs_commit"]:
            raise ValueError
        pointer = source["source_pointer"]
        versions = source["applicable_versions"]
        if source["origin_kind"] == "docs_markdown":
            if versions or source["source_id"] != "docs:" + pointer:
                raise ValueError
            if pointer in denied or _normalized_url(source["canonical_source_url"]) in denied:
                raise ValueError
            file = pointer
        elif source["origin_kind"] == "docs_generated":
            if len(versions) != 1:
                raise ValueError
            version = versions[0]
            prefix = "python/streamlit.json/" + version + "/"
            function = pointer.removeprefix(prefix)
            if (
                not pointer.startswith(prefix)
                or not _API_FUNCTION.fullmatch(function)
                or source["source_id"] != f"docstring:{version}:{function}"
            ):
                raise ValueError
            file = "python/streamlit.json"
        else:
            raise ValueError
        if source["source_type"] != _final_source_type(source["origin_kind"], pointer):
            raise ValueError
        if (
            source["source_url"]
            != f"https://github.com/streamlit/docs/blob/{pins['docs_commit']}/{file}"
        ):
            raise ValueError
        position = 0
        text = []
        for chunk in chunks_by_source[source["source_id"]]:
            span = chunk["span"]
            if type(span["start"]) is not int or type(span["end"]) is not int:
                raise ValueError
            if span["start"] != position or span["end"] <= position:
                raise ValueError
            metadata = chunk["metadata"]
            for key in (
                "source_type",
                "origin_kind",
                "source_commit",
                "source_url",
                "canonical_source_url",
                "source_pointer",
            ):
                if metadata[key] != source[key]:
                    raise ValueError
            if metadata["source_text_sha256"] != source["text_sha256"]:
                raise ValueError
            if metadata["chunk_text_sha256"] != chunk["text_sha256"]:
                raise ValueError
            if metadata["source_span"] != f"chars:{position}:{span['end']};unit:unicode_codepoint":
                raise ValueError
            if metadata["applicable_versions"] != canonical_json(versions):
                raise ValueError
            if versions and metadata.get("version") != versions[0]:
                raise ValueError
            if not versions and "version" in metadata:
                raise ValueError
            identity = {key: value for key, value in source.items() if key != "source_type"}
            if chunk["chunk_id"] != _chunk_id(
                identity, position, span["end"], chunk["text_sha256"]
            ):
                raise ValueError
            position = span["end"]
            text.append(chunk["document"])
        if (
            position != source["characters"]
            or sha256("".join(text).encode("utf-8")) != source["text_sha256"]
        ):
            raise ValueError


def build_final_corpus(
    seed_root: str | Path, allowlist_path: str | Path, exclusion_path: str | Path
) -> PilotCorpus:
    """Build the closed final profile; historical profiles keep their own builder."""
    try:
        seed = Path(seed_root)
        allowlist, allowlist_raw = _read_json(Path(allowlist_path))
        markdown_ids, api_ids = _final_allowlist(allowlist)
        package, files, pins = _package(seed)
        if package["docs_commit"] != allowlist["docs_commit"]:
            raise ValueError
        docs_manifest = json.loads(files["sources/docs_manifest.json"])
        if docs_manifest["commit"] != allowlist["docs_commit"]:
            raise ValueError
        exclusion, exclusion_raw = _read_json(Path(exclusion_path))
        exposure = json.loads(files["development_exposure.json"])
        if exposure["exclude_from_rag_corpus_with_reviewed_family"] is not True:
            raise ValueError
        exclusions = _final_exclusions(exclusion, exposure, set(allowlist["denied_document_paths"]))
        pins.update(
            {
                "allowlist_sha256": sha256(allowlist_raw),
                "exclusion_manifest_sha256": sha256(exclusion_raw),
                "split_manifest_sha256": exclusion["source_manifest_sha256"],
                "development_exposure_sha256": sha256(files["development_exposure.json"]),
                "docs_commit": allowlist["docs_commit"],
            }
        )
        sources = _selected(
            files["sources/docs_scope_candidates.jsonl"],
            markdown_ids,
            origin="docs_markdown",
            commit=allowlist["docs_commit"],
        ) + _selected_api(
            files["sources/docstrings_scope_candidates.jsonl"],
            api_ids,
            commit=allowlist["docs_commit"],
        )
        sources.sort(key=lambda source: source["source_id"])
        chunks = []
        for source in sources:
            identity = {key: value for key, value in source.items() if key != "text"}
            source_type = _final_source_type(source["origin_kind"], source["source_pointer"])
            text = source["text"]
            for start in range(0, len(text), CHUNK_CHARACTERS):
                end = min(len(text), start + CHUNK_CHARACTERS)
                document = text[start:end]
                chunk_sha = sha256(document.encode("utf-8"))
                chunk_id = _chunk_id(identity, start, end, chunk_sha)
                metadata = {
                    "chunk_id": chunk_id,
                    "source_id": source["source_id"],
                    "source_type": source_type,
                    "origin_kind": source["origin_kind"],
                    "source_commit": source["source_commit"],
                    "source_url": source["source_url"],
                    "canonical_source_url": source["canonical_source_url"],
                    "source_pointer": source["source_pointer"],
                    "source_span": f"chars:{start}:{end};unit:unicode_codepoint",
                    "source_text_sha256": source["text_sha256"],
                    "chunk_text_sha256": chunk_sha,
                    "applicable_versions": canonical_json(source["applicable_versions"]),
                }
                if source["applicable_versions"]:
                    metadata["version"] = source["applicable_versions"][0]
                _validate_hit(document, metadata)
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "document": document,
                        "metadata": metadata,
                        "span": {"start": start, "end": end, "unit": "unicode_codepoint"},
                        "text_sha256": chunk_sha,
                        "embedding_sha256": embedding_sha256(lexical_embedding(document)),
                    }
                )
        payload = {
            "schema_version": 1,
            "protocol": FINAL_PROTOCOL,
            "scope": allowlist["scope"],
            "config": {
                key: allowlist[key] for key in ("chunk_characters", "embedding", "collection_names")
            },
            "source_pins": pins,
            "exclusions": exclusions,
            "sources": [
                {
                    **{key: value for key, value in source.items() if key != "text"},
                    "source_type": _final_source_type(
                        source["origin_kind"], source["source_pointer"]
                    ),
                }
                for source in sources
            ],
            "chunks": chunks,
        }
        encoded = canonical_json(payload)
        return PilotCorpus.from_manifest(
            {"snapshot_id": "docs-pilot-" + sha256(encoded.encode("utf-8")), "corpus": payload}
        )
    except (OSError, UnicodeError, KeyError, TypeError, ValueError):
        raise PilotCorpusRejected("PilotCorpusRejected") from None


def _selected_api(raw: bytes, wanted: set[str], *, commit: str) -> list[dict[str, Any]]:
    """Like `_selected` for API records, also accepting non-`streamlit.` names."""
    result = []
    seen = set()
    for line in raw.decode("utf-8").splitlines():
        record = json.loads(line)
        source_id = record["source_id"]
        if source_id not in wanted:
            continue
        text = record["text"]
        text_hash = sha256(text.encode("utf-8"))
        version, function = record["version"], record["function"]
        if (
            source_id in seen
            or record["type"] != "docs_generated"
            or record["docs_commit"] != commit
            or not text.strip()
            or source_id != f"docstring:{version}:{function}"
            or record["json_pointer"] != f"/{version}/{function}"
            or record["text_sha256"] != text_hash
        ):
            raise ValueError
        pinned_url = f"https://github.com/streamlit/docs/blob/{commit}/python/streamlit.json"
        if record["pinned_source_url"] != pinned_url:
            raise ValueError
        result.append(
            {
                "source_id": source_id,
                "origin_kind": "docs_generated",
                "source_commit": commit,
                "source_url": pinned_url,
                "canonical_source_url": record["source_url"],
                "source_pointer": "python/streamlit.json" + record["json_pointer"],
                "applicable_versions": [version],
                "text_sha256": text_hash,
                "characters": len(text),
                "text": text,
            }
        )
        seen.add(source_id)
    if seen != wanted:
        raise ValueError
    return result
