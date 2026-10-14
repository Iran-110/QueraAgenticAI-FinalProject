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
                if metadata["source_type"] != "doc" or metadata["chunk_id"] != chunk["chunk_id"]:
                    raise ValueError
                if chunk["span"]["end"] - chunk["span"]["start"] != len(document):
                    raise ValueError
                if chunk["span"]["unit"] != "unicode_codepoint":
                    raise ValueError
                _validate_hit(document, metadata)
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
