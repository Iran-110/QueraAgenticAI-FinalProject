"""Conservative, source-bound API parameter units for an offline experiment.

This recognizes one deliberately narrow docstring format. It never executes a
signature, edits source text, chooses a user answer, or establishes semantic
support. Preamble/global sections remain in the complete source and explicit
context spans; a parameter unit need not contain every relevant qualification.
"""

import ast
import hashlib
import re
from dataclasses import dataclass

_API_SIGNATURE = re.compile(
    r"(?P<api>(?:[A-Za-z_][A-Za-z_0-9]*\.)+[A-Za-z_][A-Za-z_0-9]*)(?P<args>\(.*\))"
)
_HEADER = re.compile(r"(?P<name>[A-Za-z_][A-Za-z_0-9]*):[ \t]+(?P<type>\S.*)")
_INDENTED_HEADER = re.compile(r"[ \t]+[A-Za-z_][A-Za-z_0-9]*:")
_TOP_SECTION = re.compile(
    r"(?P<name>Returns|Yields|Raises|Examples|Notes|Warnings|See Also|References):(?:[ \t].*)?"
)
_FENCE = re.compile(r" {0,3}(?P<marker>`{3,}|~{3,})(?P<info>[^\r\n]*)")
_FIRST_TERMINAL = frozenset({"Returns", "Yields", "Raises"})
_UNAVAILABLE = "ParameterFocusUnavailable"
_MAX_SOURCE_CHARS = 20_000
_MAX_SIGNATURE_CHARS = 4_096
_MAX_PARAMETERS = 64


@dataclass(frozen=True, slots=True)
class ParameterUnit:
    """Exact half-open Unicode offsets, not an independently supported claim."""

    name: str
    start: int
    end: int
    semantic_support: None = None
    human_review_required: bool = True


@dataclass(frozen=True, slots=True)
class ParameterRecord:
    """Complete immutable source plus separately inspectable context and units."""

    source_text: str
    source_sha256: str
    api_name: str
    signature: str
    parameters: tuple[ParameterUnit, ...]
    prefix_span: tuple[int, int]
    suffix_span: tuple[int, int]
    semantic_support: None = None
    human_review_required: bool = True


def _unavailable():
    raise ValueError(_UNAVAILABLE) from None


def _literal_default(node):
    """Recognize data/sentinel spelling without evaluating any Python object."""
    if isinstance(node, ast.Constant):
        return type(node.value) in {str, int, float, bool, type(None)}
    if isinstance(node, ast.Name):
        return bool(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", node.id))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
        return isinstance(node.operand, ast.Constant) and type(node.operand.value) in {int, float}
    if isinstance(node, ast.Tuple | ast.List):
        return all(_literal_default(value) for value in node.elts)
    return False


def _signature_parameters(signature):
    match = _API_SIGNATURE.fullmatch(signature)
    if match is None or len(signature) > _MAX_SIGNATURE_CHARS:
        _unavailable()
    try:
        # Parsing an isolated def supplies Python's delimiter/string grammar.
        # No compile/eval/exec/import or default/name resolution is performed.
        parsed = ast.parse("def _parameter_focus" + match["args"] + ":\n    pass\n")
    except (SyntaxError, ValueError, TypeError, RecursionError):
        _unavailable()
    if len(parsed.body) != 1 or not isinstance(parsed.body[0], ast.FunctionDef):
        _unavailable()
    function = parsed.body[0]
    if function.decorator_list or function.returns or function.type_params:
        _unavailable()
    arguments = function.args
    named = [*arguments.posonlyargs, *arguments.args]
    if arguments.vararg is not None:
        named.append(arguments.vararg)
    named.extend(arguments.kwonlyargs)
    if arguments.kwarg is not None:
        named.append(arguments.kwarg)
    names = tuple(argument.arg for argument in named)
    if (
        not names
        or len(names) > _MAX_PARAMETERS
        or len(set(names)) != len(names)
        or any(argument.annotation is not None for argument in named)
        or any(not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name) for name in names)
        or any(
            not _literal_default(default)
            for default in [
                *arguments.defaults,
                *(value for value in arguments.kw_defaults if value is not None),
            ]
        )
    ):
        _unavailable()
    return match["api"], names


def _line_structure(lines):
    """Keep fenced examples literal; never interpret their fake peer headers."""
    outside, delimiters = [], set()
    active = None
    for index, raw in enumerate(lines):
        line = raw.removesuffix("\n").removesuffix("\r")
        fence = _FENCE.fullmatch(line)
        if active is not None:
            outside.append(False)
            if (
                fence
                and fence["marker"][0] == active[0]
                and len(fence["marker"]) >= len(active)
                and not fence["info"].strip()
            ):
                delimiters.add(index)
                active = None
        elif fence:
            outside.append(False)
            delimiters.add(index)
            active = fence["marker"]
        else:
            outside.append(True)
    if active is not None:
        _unavailable()
    return tuple(outside), frozenset(delimiters)


def parse_parameter_record(text: str) -> ParameterRecord:
    """Return complete parameter definitions in the reviewed plain API grammar.

    Required shape: one single-line dotted API signature, exactly one literal
    ``Parameters:`` section, all signature parameters documented once/in order,
    then a Returns/Yields/Raises section with body. Ambiguous/unsupported input
    rejects with a constant error; there is no substring or paragraph fallback.
    Existing full sources, renderer contracts and model decisions are untouched.
    """
    if (
        type(text) is not str
        or not text
        or len(text) > _MAX_SOURCE_CHARS
        or any(ord(char) < 32 and char not in "\n\r\t" for char in text)
        or any(char in text for char in "\x7f\x85\u2028\u2029")
        or "\r" in text.replace("\r\n", "")
    ):
        _unavailable()
    try:
        source_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    except UnicodeError:
        _unavailable()
    lines = text.splitlines(keepends=True)
    signature = lines[0].removesuffix("\n").removesuffix("\r")
    api_name, names = _signature_parameters(signature)
    outside, delimiters = _line_structure(lines)
    plain = [line.removesuffix("\n").removesuffix("\r") for line in lines]
    markers = [i for i, line in enumerate(plain) if outside[i] and line == "Parameters:"]
    if len(markers) != 1 or markers[0] < 2:
        _unavailable()
    marker = markers[0]
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    headers, terminal = [], None
    for index in range(marker + 1, len(lines)):
        if not outside[index]:
            continue
        line = plain[index]
        if top := _TOP_SECTION.fullmatch(line):
            if top["name"] not in _FIRST_TERMINAL:
                _unavailable()
            terminal = index
            break
        if line.startswith((" ", "\t")) and _INDENTED_HEADER.match(line):
            _unavailable()
        if header := _HEADER.fullmatch(line):
            if header["name"] not in names or plain[index - 1].strip():
                _unavailable()
            headers.append((header["name"], index))
        elif re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*:\s*", line):
            # An empty type or unexpected section cannot silently end a unit.
            _unavailable()
    if terminal is None or tuple(name for name, _index in headers) != names:
        _unavailable()
    if any(plain[index].strip() for index in range(marker + 1, headers[0][1])):
        _unavailable()
    ends = [*(index for _name, index in headers[1:]), terminal]
    for (_name, start), end in zip(headers, ends, strict=True):
        if not any(
            plain[index].strip() and index not in delimiters for index in range(start + 1, end)
        ):
            _unavailable()
    terminal_end = next(
        (
            index
            for index in range(terminal + 1, len(lines))
            if outside[index] and _TOP_SECTION.fullmatch(plain[index])
        ),
        len(lines),
    )
    if not any(
        plain[index].strip() and index not in delimiters
        for index in range(terminal + 1, terminal_end)
    ):
        _unavailable()
    units = tuple(
        ParameterUnit(name=name, start=offsets[start], end=offsets[end])
        for (name, start), end in zip(headers, ends, strict=True)
    )
    return ParameterRecord(
        source_text=text,
        source_sha256=source_sha256,
        api_name=api_name,
        signature=signature,
        parameters=units,
        prefix_span=(0, units[0].start),
        suffix_span=(offsets[terminal], len(text)),
    )
