"""Opt-in, nonexecuting checks for a few source-grounded callback contradictions.

These are not general Python, Streamlit, runtime or source-faithfulness checks.
Only complete labeled Python fences with an explicit unshadowed module import
are covered. Uncertain imports, signatures, versions and expressions are skipped.
Fresh-value capture additionally requires caller-owned intent; a previous-value
snapshot is legitimate when that intent is absent.
"""

import ast
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from agent_app.contracts import AnalysisResult, CaseState, EvidenceBundle, EvidenceHit, OutputIssue
from agent_app.reasoning.code_checks import _python_modules

_MAX_AST_NODES = 8192
_MAX_ALIASES = 8
_MAX_SIGNATURE_BYTES = 4096
_SIGNATURE = re.compile(r"st\.(?P<name>[A-Za-z_]\w*)\((?P<parameters>.*)\)")
_VERSION = re.compile(r"\d+\.\d+\.\d+")
_COMMIT = re.compile(r"[a-f0-9]{40}")
# This particular unversioned timing source was reviewed alongside the current
# 1.64.0 API record. Its commit date does not establish historical applicability.
_REVIEWED_TIMING_COMMIT = "695e6ce2fb1b23afc6df66b40420ab0013ad72fd"
_REVIEWED_TIMING_VERSION = "1.64.0"
_TIMING_PATH = "content/develop/concepts/architecture/widget-behavior.md"
_TIMING_PHRASES = (
    "arguments will be established when the widget command is called",
    "not later when the user interacts with the widget",
    "you can't pass that value to the callback function via the `args` parameter",
    "look up its value using `st.session_state` _within the callback function_",
)


@dataclass(frozen=True)
class _Signature:
    keyword_names: frozenset[str]
    accepts_arbitrary_keywords: bool
    shape: str


def _nodes(module: ast.AST) -> tuple[ast.AST, ...] | None:
    nodes = []
    for node in ast.walk(module):
        nodes.append(node)
        if len(nodes) > _MAX_AST_NODES:
            return None
    return tuple(nodes)


def _official_path(hit: EvidenceHit) -> str | None:
    if (
        hit.source_type != "doc"
        or not hit.source_commit
        or not _COMMIT.fullmatch(hit.source_commit)
        or not hit.source_span
    ):
        return None
    url = urlsplit(hit.source_url)
    prefix = f"/streamlit/docs/blob/{hit.source_commit}/"
    if url.scheme != "https" or url.hostname != "github.com" or not url.path.startswith(prefix):
        return None
    return url.path[len(prefix) :]


def _user_version(case: CaseState) -> str | None:
    versions = {
        fact.value
        for fact in case.facts
        if fact.name.casefold() == "streamlit_version"
        and fact.provenance_kind == "user"
        and fact.status == "active"
    }
    if len(versions) != 1:
        return None
    version = versions.pop()
    return version if _VERSION.fullmatch(version) else None


def _signatures(evidence: EvidenceBundle, version: str) -> dict[str, _Signature]:
    candidates: dict[str, set[_Signature]] = {}
    for hit in evidence.hits:
        if version not in hit.applicable_versions or _official_path(hit) != "python/streamlit.json":
            continue
        lines = hit.excerpt.strip().splitlines()
        if not lines:
            continue
        line = lines[0].strip()
        if len(line.encode("utf-8")) > _MAX_SIGNATURE_BYTES:
            continue
        match = _SIGNATURE.fullmatch(line)
        if not match:
            continue
        name = match["name"]
        if (
            hit.source_id != f"docstring:{version}:streamlit.{name}"
            or not hit.source_span.startswith(f"JSON pointer /{version}/streamlit.{name};")
        ):
            continue
        try:
            tree = ast.parse(f"def _signature({match['parameters']}):\n    pass\n")
        except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError):
            continue
        if (
            not isinstance(tree, ast.Module)
            or len(tree.body) != 1
            or not isinstance(tree.body[0], ast.FunctionDef)
            or _nodes(tree) is None
        ):
            continue
        signature_args = tree.body[0].args
        signature = _Signature(
            frozenset(arg.arg for arg in (*signature_args.args, *signature_args.kwonlyargs)),
            signature_args.kwarg is not None,
            ast.dump(signature_args, include_attributes=False),
        )
        candidates.setdefault(name, set()).add(signature)
    # Disagreement means unknown applicability; do not select the stricter source.
    return {name: next(iter(values)) for name, values in candidates.items() if len(values) == 1}


def _has_timing(evidence: EvidenceBundle, version: str) -> bool:
    if version != _REVIEWED_TIMING_VERSION:
        return False
    for hit in evidence.hits:
        if (
            hit.source_commit != _REVIEWED_TIMING_COMMIT
            or _official_path(hit) != _TIMING_PATH
            or (hit.applicable_versions and version not in hit.applicable_versions)
        ):
            continue
        excerpt = " ".join(hit.excerpt.split())
        if all(phrase in excerpt for phrase in _TIMING_PHRASES):
            return True
    return False


def _import_bindings(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.asname or alias.name.split(".")[0] for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        return tuple(alias.asname or alias.name for alias in node.names)
    return ()


def _attribute_root(node: ast.AST) -> tuple[str | None, str | None]:
    attributes = []
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        if isinstance(node, ast.Attribute):
            attributes.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return node.id, attributes[-1] if attributes else None
    return None, None


def _aliases(module: ast.Module, nodes: tuple[ast.AST, ...]) -> frozenset[str]:
    aliases = {
        alias.asname or alias.name
        for node in module.body
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "streamlit"
    }
    if len(aliases) > _MAX_ALIASES:
        return frozenset()
    for alias in tuple(aliases):
        imports = sum(alias in _import_bindings(node) for node in nodes)
        uncertain = imports != 1
        for node in nodes:
            if isinstance(node, ast.ImportFrom) and any(item.name == "*" for item in node.names):
                uncertain = True
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                uncertain |= node.id == alias
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                uncertain |= node.name == alias
            if isinstance(node, ast.arg):
                uncertain |= node.arg == alias
            if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
                uncertain |= node.name == alias
            if isinstance(node, ast.MatchMapping):
                uncertain |= node.rest == alias
            if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(
                node.ctx, (ast.Store, ast.Del)
            ):
                root, first_attribute = _attribute_root(node)
                # Ordinary Session State value writes do not replace the module.
                value_write = first_attribute == "session_state" and not (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.attr == "session_state"
                )
                uncertain |= root == alias and not value_write
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in {
                    "exec",
                    "eval",
                    "globals",
                    "locals",
                    "vars",
                }:
                    uncertain = True
                function_name = (
                    node.func.id
                    if isinstance(node.func, ast.Name)
                    else node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else None
                )
                if function_name in {"setattr", "delattr"} and node.args:
                    uncertain |= isinstance(node.args[0], ast.Name) and node.args[0].id == alias
        if uncertain:
            aliases.remove(alias)
    return frozenset(aliases)


def _key(node: ast.AST, *, depth: int = 0) -> tuple | None:
    if depth > 16:
        return None
    if isinstance(node, ast.Constant) and type(node.value) in {str, int}:
        return ("constant", type(node.value).__name__, node.value)
    if isinstance(node, ast.Name):
        return ("name", node.id)
    if isinstance(node, ast.JoinedStr):
        values = tuple(_key(value, depth=depth + 1) for value in node.values)
        return ("joined", values) if all(value is not None for value in values) else None
    if isinstance(node, ast.FormattedValue) and node.format_spec is None:
        value = _key(node.value, depth=depth + 1)
        return ("formatted", node.conversion, value) if value is not None else None
    return None


def _state_read(node: ast.AST, alias: str) -> tuple | None:
    if not (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "session_state"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == alias
    ):
        return None
    return _key(node.slice)


def _literal_values(node: ast.AST, *, kwargs: bool) -> tuple[ast.AST, ...] | None:
    if kwargs:
        if not isinstance(node, ast.Dict) or any(
            not isinstance(key, ast.Constant) or not isinstance(key.value, str) for key in node.keys
        ):
            return None
        values = tuple(node.values)
    else:
        if not isinstance(node, (ast.Tuple, ast.List)):
            return None
        values = tuple(node.elts)
    # Opaque helpers, deferred lambdas, unpacking and comprehensions stay outside
    # coverage. Only plain values and direct state subscripts are inspected.
    if any(not isinstance(value, (ast.Name, ast.Constant, ast.Subscript)) for value in values):
        return None
    return values


def _eager_computation(node: ast.AST) -> bool:
    pending = [node]
    while pending:
        current = pending.pop()
        if isinstance(current, (ast.Call, ast.NamedExpr)):
            return True
        if isinstance(current, ast.Lambda):
            # A lambda's body is deferred; its defaults are evaluated now.
            pending.extend(current.args.defaults)
            pending.extend(value for value in current.args.kw_defaults if value is not None)
        else:
            pending.extend(ast.iter_child_nodes(current))
    return False


def _captures_value(call: ast.Call, signature: _Signature, alias: str) -> bool:
    keywords = {keyword.arg: keyword.value for keyword in call.keywords}
    callback = next(
        (
            keywords[name]
            for name in ("on_change", "on_click")
            if name in keywords and name in signature.keyword_names
        ),
        None,
    )
    if (
        not {"key", "args", "kwargs"}.issubset(signature.keyword_names)
        or callback is None
        or not isinstance(callback, (ast.Name, ast.Lambda))
        or "key" not in keywords
    ):
        return False
    own_key = _key(keywords["key"])
    if own_key is None:
        return False
    # With symbolic keys, opaque computations can change a binding between the
    # keyword evaluations. Skip such calls rather than infer execution effects.
    if own_key[0] != "constant" and any(
        _eager_computation(value) for value in (*call.args, *keywords.values())
    ):
        return False
    for name in ("args", "kwargs"):
        if name not in keywords:
            continue
        values = _literal_values(keywords[name], kwargs=name == "kwargs")
        if values is not None and any(_state_read(value, alias) == own_key for value in values):
            return True
    return False


def callback_code_issues(
    analysis: AnalysisResult,
    case: CaseState,
    evidence: EvidenceBundle,
    *,
    require_fresh_widget_value: bool = False,
) -> tuple[OutputIssue, ...]:
    """Return only bounded allowlisted findings; never execute or log snippets.

    The caller must request this checker separately from default syntax checks.
    Syntax failures remain that checker's responsibility. Absence of a finding
    means either no recognized contradiction or incomplete semantic coverage.
    """
    try:
        version = _user_version(case)
        if version is None:
            return ()
        signatures = _signatures(evidence, version)
        if not signatures:
            return ()
        modules = _python_modules(analysis)
        if modules is None:
            return ()
        fresh = require_fresh_widget_value and _has_timing(evidence, version)
        codes = set()
        for module in modules:
            nodes = _nodes(module)
            if nodes is None:
                continue
            aliases = _aliases(module, nodes)
            for node in nodes:
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in aliases
                ):
                    continue
                signature = signatures.get(node.func.attr)
                if signature is None:
                    continue
                if not signature.accepts_arbitrary_keywords and any(
                    keyword.arg is not None and keyword.arg not in signature.keyword_names
                    for keyword in node.keywords
                ):
                    codes.add("invalid_api_keyword")
                if fresh and _captures_value(node, signature, node.func.value.id):
                    codes.add("callback_value_captured")
        return tuple(
            OutputIssue(code=code)
            for code in ("invalid_api_keyword", "callback_value_captured")
            if code in codes
        )
    except (ValueError, TypeError, UnicodeError, RecursionError, MemoryError):
        # Resource limits or ambiguous source input never manufacture a semantic
        # rejection. The separate syntax checker still fails closed on its input.
        return ()
