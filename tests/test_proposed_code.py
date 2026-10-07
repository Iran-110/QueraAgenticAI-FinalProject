"""Nonexecuting Python syntax checks with explicit coverage and resource bounds."""

import sys

import pytest

from agent_app.contracts import AnalysisResult
from agent_app.reasoning import code_checks
from agent_app.reasoning.code_checks import has_invalid_python_code


def analysis(user_draft="A pending reply.", maintainer_summary="A pending summary."):
    return AnalysisResult(
        decision="answer",
        user_draft=user_draft,
        maintainer_summary=maintainer_summary,
        rationale="Synthetic code validation test only.",
    )


def fenced(source, language="python", marker="```"):
    return f"{marker}{language}\n{source}\n{marker}"


def test_extra_callback_closing_parenthesis_is_rejected():
    source = 'def callback():\n    pass\nst.button("Run", on_click=callback))'

    assert has_invalid_python_code(analysis(fenced(source))) is True


@pytest.mark.parametrize("language", ["python", "py", "python3", "PYTHON", "python title=example"])
def test_valid_callback_syntax_is_accepted_for_known_python_labels(language):
    source = (
        "def callback(step):\n"
        "    st.session_state.counter += step\n"
        'st.button("Run", on_click=callback, args=(1,))'
    )

    assert has_invalid_python_code(analysis(fenced(source, language))) is False


def test_valid_syntax_does_not_claim_correct_callback_arity_or_streamlit_api_usage():
    source = 'def callback(required_argument):\n    pass\nst.button("Run", on_click=callback)'

    assert has_invalid_python_code(analysis(fenced(source))) is False


@pytest.mark.parametrize("draft_name", ["user_draft", "maintainer_summary"])
def test_both_final_drafts_are_checked(draft_name):
    reply = analysis(**{draft_name: fenced("value = )")})

    assert has_invalid_python_code(reply) is True


@pytest.mark.parametrize("language", ["", "text", "pseudocode", "javascript", "pythonish"])
def test_unlabeled_and_other_language_fences_are_outside_python_coverage(language):
    assert has_invalid_python_code(analysis(fenced("this is not Python )", language))) is False


def test_inline_code_and_prose_are_not_parsed_as_python():
    reply = analysis("Proposed inline snippet `st.button())` and plain text with ) punctuation.")

    assert has_invalid_python_code(reply) is False


def test_python_label_inside_an_unknown_outer_fence_is_not_reinterpreted():
    outer = "````text\n```python\nnot valid Python )\n```\n````"

    assert has_invalid_python_code(analysis(outer)) is False


@pytest.mark.parametrize(
    "draft",
    [
        "```python\nvalue = 1",
        "````python\nvalue = 1\n```",
        "```python\nvalue = 1\n~~~",
    ],
)
def test_missing_or_mismatched_closing_python_fence_is_rejected(draft):
    assert has_invalid_python_code(analysis(draft)) is True


def test_crlf_and_opening_fence_indent_preserve_python_function_indentation():
    draft = "Example\r\n  ```python\r\n  def callback():\r\n      return 1\r\n  callback()\r\n  ```"

    assert has_invalid_python_code(analysis(draft)) is False


def test_tilde_fences_and_longer_closing_markers_are_supported():
    draft = "~~~py\nvalue = 1\n~~~~~"

    assert has_invalid_python_code(analysis(draft)) is False


def test_unicode_identifiers_and_strings_are_valid_without_executing_them():
    assert has_invalid_python_code(analysis(fenced('نام = "سلام"'))) is False


@pytest.mark.parametrize("source", ["value = 1\u2028other = 2", "value = '\0'"])
def test_invalid_unicode_or_null_source_fails_closed_without_diagnostics(source, capsys):
    assert has_invalid_python_code(analysis(fenced(source))) is True
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_unpaired_surrogate_in_a_bypassed_model_fails_closed(capsys):
    # Normal boundary validation already rejects this Unicode value.
    bypass = analysis().model_copy(update={"user_draft": fenced("value = '\ud800'")})

    assert has_invalid_python_code(bypass) is True
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("failure", [RecursionError, MemoryError, ValueError])
def test_parser_resource_failures_return_only_a_boolean(monkeypatch, failure, capsys):
    def fail_parse(*_args, **_kwargs):
        raise failure("PRIVATE_SNIPPET_OR_EXCEPTION_MARKER")

    monkeypatch.setattr(code_checks.ast, "parse", fail_parse)

    assert has_invalid_python_code(analysis(fenced("value = 1"))) is True
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_real_deep_parser_input_fails_closed():
    deeply_nested = "value = " + "(" * 1_000 + "1" + ")" * 1_000

    assert has_invalid_python_code(analysis(fenced(deeply_nested))) is True


def test_oversized_single_block_is_rejected_before_ast_parsing(monkeypatch):
    def forbid_parse(*_args, **_kwargs):
        pytest.fail("An oversized block must not reach the parser")

    monkeypatch.setattr(code_checks.ast, "parse", forbid_parse)

    assert has_invalid_python_code(analysis(fenced("#" + "x" * 8_192))) is True


def test_utf8_bytes_rather_than_characters_bound_a_python_block(monkeypatch):
    def forbid_parse(*_args, **_kwargs):
        pytest.fail("UTF-8 bytes must be checked before parsing")

    monkeypatch.setattr(code_checks.ast, "parse", forbid_parse)

    assert has_invalid_python_code(analysis(fenced("#" + "😀" * 2_048))) is True


def test_eight_blocks_are_permitted_but_nine_across_both_drafts_are_rejected():
    block = fenced("value = 1")
    eight = analysis("\n".join([block] * 4), "\n".join([block] * 4))
    nine = analysis("\n".join([block] * 4), "\n".join([block] * 5))

    assert has_invalid_python_code(eight) is False
    assert has_invalid_python_code(nine) is True


def test_byte_limit_boundary_is_accepted_and_one_extra_byte_is_rejected():
    exact = "#" + "x" * 8_190  # Source plus the normalized newline is 8,192 bytes.

    assert has_invalid_python_code(analysis(fenced(exact))) is False
    assert has_invalid_python_code(analysis(fenced(exact + "x"))) is True


def test_eight_utf8_blocks_at_the_combined_byte_limit_can_span_both_drafts():
    source = "#" + "😀" * 2_047 + "xx"  # Exactly 8,192 UTF-8 bytes including newline.
    four_blocks = "\n".join([fenced(source)] * 4)

    assert has_invalid_python_code(analysis(four_blocks, four_blocks)) is False


def test_parsing_imports_and_function_calls_never_executes_them(tmp_path):
    marker_path = tmp_path / "must-not-exist.txt"
    source = (
        "import module_that_must_never_be_imported_by_the_guard\n"
        "from pathlib import Path\n"
        f"Path({str(marker_path)!r}).write_text('executed')\n"
        "def callback():\n"
        "    raise RuntimeError('must not execute')\n"
        "callback()"
    )

    assert has_invalid_python_code(analysis(fenced(source))) is False
    assert not marker_path.exists()
    assert "module_that_must_never_be_imported_by_the_guard" not in sys.modules


@pytest.mark.parametrize(
    "source",
    [
        "return 1",
        "break",
        "continue",
        "await helper()",
        "def callback(value, value):\n    pass",
        "def callback(value, **value):\n    pass",
        "def callback():\n    nonlocal missing",
    ],
)
def test_parseable_but_uncompilable_complete_modules_are_rejected(source, capsys):
    assert has_invalid_python_code(analysis(fenced(source))) is True
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize(
    "source",
    [
        "def callback():\n    return 1",
        "for value in range(2):\n    break",
        "async def callback():\n    await helper()",
        "def callback(value, /, **kwargs):\n    return kwargs",
    ],
)
def test_valid_scoped_counterparts_survive_static_compilation(source):
    assert has_invalid_python_code(analysis(fenced(source))) is False


@pytest.mark.parametrize(
    "failure", [SyntaxError, TypeError, ValueError, RecursionError, MemoryError]
)
def test_compiler_failures_export_no_source_or_exception_text(monkeypatch, failure, capsys):
    def fail_compile(*_args, **_kwargs):
        raise failure("PRIVATE_COMPILER_EXCEPTION_MARKER")

    monkeypatch.setattr(code_checks, "compile", fail_compile, raising=False)
    assert has_invalid_python_code(analysis(fenced("value = 1"))) is True
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_source_bearing_parser_and_compiler_warnings_are_suppressed(capsys):
    assert has_invalid_python_code(analysis(fenced("PRIVATE_MARKER is 123456"))) is False
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
