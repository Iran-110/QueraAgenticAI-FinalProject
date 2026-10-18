"""Offline signature-declared defaults; never patch an indexed or historical source.

Caller provenance declarations are content-bound, not authenticated here. Complete
raw JSON and legacy text remain available; no code/source snippet is executed.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields, is_dataclass
from html.parser import HTMLParser

from experiments.core_parameter_focus_v1.parameters import parse_parameter_record
from experiments.core_parameter_review_v1.integrity import _signature_defaults

_ERROR = "RawDefaultNormalizationUnavailable"
_SHA = re.compile(r"[0-9a-f]{64}")
_FUNCTION = re.compile(r"streamlit\.[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*")


def _reject():
    raise ValueError(_ERROR) from None


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json(value, depth=0):
    if depth > 32:
        _reject()
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            _reject()
        for child in value.values():
            _json(child, depth + 1)
    elif type(value) is list:
        for child in value:
            _json(child, depth + 1)
    elif type(value) not in {str, bool, int, float, type(None)}:
        _reject()
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def canonical_entry_sha256(raw_entry):
    """Hash a lossless JSON-data entry; physical file hash is a separate input."""
    try:
        return _sha(_json(raw_entry))
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        _reject()


class _HTMLText(HTMLParser):
    """Exact text extraction policy of the archived preparation script."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "pre", "li", "br", "blockquote", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"p", "pre", "li", "blockquote", "tr"}:
            self.parts.append("\n")

    @classmethod
    def extract(cls, value):
        if value is not None and type(value) is not str:
            _reject()
        parser = cls()
        parser.feed(value or "")
        return re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()


def reconstruct_legacy_text(raw_entry):
    """Faithful legacy projection, including its old ambiguous default fields."""
    try:
        if type(raw_entry) is not dict or type(raw_entry.get("signature")) is not str:
            _reject()
        parts = [
            raw_entry["signature"],
            _HTMLText.extract(raw_entry.get("description")),
            "Parameters:",
        ]
        for arg in raw_entry.get("args", []):
            parts.append(
                f"{arg.get('name')}: {arg.get('type_name')}; default={arg.get('default')}\n"
                + _HTMLText.extract(arg.get("description"))
            )
        for ret in raw_entry.get("returns", []):
            parts.append(
                f"Returns: {ret.get('type_name', ret.get('name', ''))}\n"
                + _HTMLText.extract(ret.get("description"))
            )
        parts.extend(["Examples:", _HTMLText.extract(raw_entry.get("example"))])
        return "\n\n".join(parts)
    except (ValueError, TypeError, AttributeError, UnicodeError, RecursionError):
        _reject()


@dataclass(frozen=True, slots=True)
class DefaultObservation:
    name: str
    signature_state: str
    signature_token: str | None
    signature_span: tuple[int, int] | None
    raw_default_state: str
    raw_default_json: str | None
    action: str
    old_span: tuple[int, int]
    old_text: str
    replacement: str


@dataclass(frozen=True, slots=True)
class RawDefaultNormalization:
    schema_id: str
    version: str
    function: str
    expected_version: str
    expected_function: str
    docs_commit: str
    raw_file_sha256: str
    raw_entry_sha256: str
    json_pointer: str
    canonical_raw_entry: str
    original_text: str
    original_text_sha256: str
    derived_text: str
    derived_text_sha256: str
    observations: tuple[DefaultObservation, ...]
    derived_identity: str
    context_sha256: str
    basis: str = "source_documentation_signature"
    raw_membership_authenticated: bool = False
    derived_text_is_complete_raw_documentation: bool = False
    actual_runtime_defaults_verified: bool = False
    runtime_adoption: bool = False
    semantic_support: None = None
    human_review_required: bool = True
    proposal_or_action_authorized: bool = False


def normalize_raw_defaults(
    raw_entry,
    legacy_text,
    *,
    version,
    function,
    expected_version,
    expected_function,
    docs_commit,
    raw_file_sha256,
    expected_entry_sha256,
):
    """Create a fresh offline derivation, preserving every non-header byte.

    Only signature literal tokens replace metadata defaults. Required/variadic
    parameters lose the misleading default field; unresolved names stay flagged.
    This does not establish membership in a caller-declared raw file or version.
    """
    try:
        if (
            type(version) is not str
            or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version)
            or type(function) is not str
            or not _FUNCTION.fullmatch(function)
            or type(expected_version) is not str
            or version != expected_version
            or type(expected_function) is not str
            or function != expected_function
            or type(docs_commit) is not str
            or not re.fullmatch(r"[0-9a-f]{40}", docs_commit)
            or type(raw_file_sha256) is not str
            or not _SHA.fullmatch(raw_file_sha256)
            or type(expected_entry_sha256) is not str
            or not _SHA.fullmatch(expected_entry_sha256)
            or type(legacy_text) is not str
            or len(legacy_text) > 20_000
            or "\r" in legacy_text.replace("\r\n", "")
            or type(raw_entry) is not dict
        ):
            _reject()
        raw_json = _json(raw_entry)
        if len(raw_json) > 1_000_000 or _sha(raw_json) != expected_entry_sha256:
            _reject()
        if legacy_text.replace("\r\n", "\n") != reconstruct_legacy_text(raw_entry).replace(
            "\r\n", "\n"
        ):
            _reject()
        record = parse_parameter_record(legacy_text)
        if record.api_name not in {function, "st." + function.removeprefix("streamlit.")}:
            _reject()
        args = raw_entry.get("args")
        if (
            type(args) is not list
            or any(type(arg) is not dict for arg in args)
            or [arg.get("name") for arg in args] != [unit.name for unit in record.parameters]
            or raw_entry.get("name") != function.rsplit(".", 1)[1]
        ):
            _reject()
        defaults, observations = _signature_defaults(record), []
        for arg, unit in zip(args, record.parameters, strict=True):
            header = legacy_text[unit.start : unit.end].splitlines()[0]
            if header.count("; default=") != 1:
                _reject()
            marker = header.index("; default=")
            state, span, token, _literal = defaults[unit.name]
            if state in {"required", "variadic_without_default"}:
                start, replacement, action = unit.start + marker, "", "remove_spurious_default"
            else:
                start = unit.start + marker + len("; default=")
                replacement = token if state == "literal" else header[marker + len("; default=") :]
                action = "signature_literal" if state == "literal" else "preserve_unresolved"
            end = unit.start + len(header)
            raw_state = (
                "missing"
                if "default" not in arg
                else "null_ambiguous"
                if arg["default"] is None
                else "supplied"
            )
            observations.append(
                DefaultObservation(
                    unit.name,
                    state,
                    token,
                    span,
                    raw_state,
                    _json(arg["default"]) if "default" in arg else None,
                    action,
                    (start, end),
                    legacy_text[start:end],
                    replacement,
                )
            )
        derived = legacy_text
        for item in reversed(observations):
            derived = derived[: item.old_span[0]] + item.replacement + derived[item.old_span[1] :]
        parse_parameter_record(derived)
        context = {
            "schema_id": "raw-default-normalization-v1",
            "version": version,
            "function": function,
            "expected_version": expected_version,
            "expected_function": expected_function,
            "docs_commit": docs_commit,
            "raw_file_sha256": raw_file_sha256,
            "raw_entry_sha256": expected_entry_sha256,
            "json_pointer": f"/{version}/{function}",
            "canonical_raw_entry": raw_json,
            "original_text": legacy_text,
            "original_text_sha256": _sha(legacy_text),
            "derived_text": derived,
            "derived_text_sha256": _sha(derived),
            "observations": tuple(observations),
            "derived_identity": "api-signature-defaults-v1:"
            + _sha(
                _json(
                    {
                        "schema_id": "raw-default-normalization-v1",
                        "version": version,
                        "function": function,
                        "docs_commit": docs_commit,
                        "raw_file_sha256": raw_file_sha256,
                        "raw_entry_sha256": expected_entry_sha256,
                        "original_text_sha256": _sha(legacy_text),
                        "derived_text_sha256": _sha(derived),
                    }
                )
            ),
        }
        digest = _sha(
            json.dumps(
                {**context, "observations": [asdict(item) for item in observations]},
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        )
        return RawDefaultNormalization(**context, context_sha256=digest)
    except (
        ValueError,
        TypeError,
        AttributeError,
        KeyError,
        UnicodeError,
        RecursionError,
        OverflowError,
    ):
        _reject()


def _typed_equal(left, right):
    if type(left) is not type(right):
        return False
    if is_dataclass(left):
        return all(
            _typed_equal(getattr(left, f.name), getattr(right, f.name)) for f in fields(left)
        )
    if type(left) is tuple:
        return len(left) == len(right) and all(
            _typed_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def validate_raw_default_normalization(report):
    """Recompute every bound field; a reconstructed dataclass is not authority."""
    try:
        if type(report) is not RawDefaultNormalization:
            _reject()
        rebuilt = normalize_raw_defaults(
            json.loads(report.canonical_raw_entry),
            report.original_text,
            version=report.version,
            function=report.function,
            expected_version=report.expected_version,
            expected_function=report.expected_function,
            docs_commit=report.docs_commit,
            raw_file_sha256=report.raw_file_sha256,
            expected_entry_sha256=report.raw_entry_sha256,
        )
        if not _typed_equal(report, rebuilt):
            _reject()
        return rebuilt
    except (ValueError, TypeError, AttributeError, UnicodeError, RecursionError):
        _reject()
