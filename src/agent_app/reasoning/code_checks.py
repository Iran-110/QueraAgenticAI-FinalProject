"""Bounded syntax checks for explicitly labeled Python fences in proposed drafts.

This does not execute snippets or verify callback arity, types, API usage, or
source faithfulness. Unlabeled, inline, quoted, and other-language code is outside
coverage. Fences use backticks or tildes with up to three opening-indent spaces.
Each labeled block is parsed as a complete module; partial fragments can fail.
"""

import ast
import re
from dataclasses import dataclass, field

from agent_app.contracts import AnalysisResult

_MAX_BLOCK_BYTES = 8192
_MAX_BLOCKS = 8
_MAX_TOTAL_BYTES = 65536
_PYTHON_LABELS = {"python", "py", "python3"}
_FENCE = re.compile(r"^(?P<indent> {0,3})(?P<marker>`{3,}|~{3,})(?P<info>[^\r\n]*)$")


@dataclass
class _OpenFence:
    marker: str
    indent: int
    python: bool
    lines: list[str] = field(default_factory=list)
    byte_count: int = 0

    def closes(self, match: re.Match[str] | None) -> bool:
        return bool(
            match
            and match["marker"][0] == self.marker[0]
            and len(match["marker"]) >= len(self.marker)
            and not match["info"].strip(" \t")
        )

    def unindent(self, line: str) -> str:
        # Markdown removes up to the opening fence's indentation, not arbitrary
        # Python indentation inside the snippet.
        for _ in range(self.indent):
            if not line.startswith(" "):
                break
            line = line[1:]
        return line


def has_invalid_python_code(analysis: AnalysisResult) -> bool:
    """Fail closed on invalid/unfinished labeled snippets or bounded-parser failures.

    Input is a validated AnalysisResult. Only a static boolean leaves this check;
    source text and exception messages are never returned or logged.
    """
    block_count = 0
    total_bytes = 0
    for draft in (analysis.user_draft, analysis.maintainer_summary):
        if not isinstance(draft, str):
            return True
        opened = None
        # Python does not treat every Unicode splitlines() separator as a newline.
        # Preserve those characters so ast.parse can reject invalid source.
        for line in draft.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            match = _FENCE.fullmatch(line)
            if opened is None:
                if match is None or (match["marker"][0] == "`" and "`" in match["info"]):
                    continue
                info = match["info"].strip().split(maxsplit=1)
                python = bool(info and info[0].casefold() in _PYTHON_LABELS)
                opened = _OpenFence(match["marker"], len(match["indent"]), python)
                if python:
                    block_count += 1
                    if block_count > _MAX_BLOCKS:
                        return True
                continue
            if opened.closes(match):
                if opened.python:
                    try:
                        ast.parse("\n".join(opened.lines) + "\n", mode="exec")
                    except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError):
                        return True
                opened = None
                continue
            if opened.python:
                source_line = opened.unindent(line)
                try:
                    line_bytes = len((source_line + "\n").encode("utf-8"))
                except UnicodeError:
                    return True
                opened.byte_count += line_bytes
                total_bytes += line_bytes
                if opened.byte_count > _MAX_BLOCK_BYTES or total_bytes > _MAX_TOTAL_BYTES:
                    return True
                opened.lines.append(source_line)
        if opened is not None and opened.python:
            return True
    return False
