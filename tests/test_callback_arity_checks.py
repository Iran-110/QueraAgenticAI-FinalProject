"""Source-scoped static binding checks; no proposed snippet is executed."""

from pathlib import Path

import pytest

from agent_app.contracts import AnalysisResult, CaseState, EvidenceBundle
from agent_app.reasoning import proposal_checks
from agent_app.reasoning.code_checks import has_invalid_python_code
from agent_app.reasoning.probes import load_suite
from agent_app.reasoning.proposal_checks import callback_code_issues

SUITE = load_suite(Path(__file__).parents[1] / "experiments/decision_quality/cases-guards-v4.json")
PROBE = next(probe for probe in SUITE.cases if probe.id == "synthetic-own-widget-pass-key-control")
EVIDENCE = PROBE.bundles[0]


def proposal(source, *, field="user_draft", language="python"):
    fields = {"user_draft": "Pending review.", "maintainer_summary": "Pending summary."}
    fields[field] = f"```{language}\n{source}\n```"
    return AnalysisResult(decision="answer", rationale="Offline binding fixture.", **fields)


def source(parameters="value", arguments="", *, body="pass", widget="selectbox"):
    callback_parameter = "on_click" if widget == "form_submit_button" else "on_change"
    widget_args = '"Send"' if widget == "form_submit_button" else '"Choice", [1, 2]'
    suffix = f", {arguments}" if arguments else ""
    return (
        "import streamlit as st\n"
        f"def callback({parameters}):\n    {body}\n"
        f"st.{widget}({widget_args}, {callback_parameter}=callback{suffix})"
    )


def codes(code, *, evidence=EVIDENCE, state=PROBE.case_state, field="user_draft"):
    return tuple(
        issue.code for issue in callback_code_issues(proposal(code, field=field), state, evidence)
    )


@pytest.mark.parametrize(
    "parameters, arguments",
    [
        ("value", ""),
        ("value", "args=None, kwargs=None"),
        ("value", "args=(), kwargs={}"),
        ("value", "args=[]"),
        ("value", "args=(1, 2)"),
        ("first, second", "args=(1,)"),
        ("first, second=2", ""),
        ("*, value", ""),
        ("*, value", "args=(1,)"),
        ("value", 'args=(1,), kwargs={"value": 2}'),
        ("value", 'kwargs={"unexpected": 2}'),
        ("value, /", 'kwargs={"value": 2}'),
        ("value, /", 'args=(1,), kwargs={"value": 2}'),
        ("value, /, **rest", 'kwargs={"value": 2}'),
        ("value, *rest", ""),
        ("value=1, /", 'kwargs={"value": 2}'),
        ("value, *rest, flag=True, **extra", 'args=(1,), kwargs={"value": 2}'),
    ],
)
def test_proven_callback_parameter_binding_mismatch(parameters, arguments):
    assert codes(source(parameters, arguments)) == ("callback_arity_mismatch",)


@pytest.mark.parametrize(
    "parameters, arguments",
    [
        ("", ""),
        ("value", "args=(1,)"),
        ("value", "args=[1]"),
        ("value", 'kwargs={"value": 1}'),
        ("value", 'kwargs={"value": 1, "value": 2}'),
        ("value=1", ""),
        ("first, second=2", "args=(1,)"),
        ("*, value", 'kwargs={"value": 1}'),
        ("*, value=None", ""),
        ("value, /", "args=(1,)"),
        ("value, /, **rest", 'args=(1,), kwargs={"value": 2}'),
        ("value=1, /, **rest", 'kwargs={"value": 2}'),
        ("*rest", "args=(1, 2, 3)"),
        ("value, *rest", "args=(1, 2, 3)"),
        ("**rest", 'kwargs={"value": 1}'),
        ("value, *rest, flag, **extra", 'args=(1, 2), kwargs={"flag": 3, "extra": 4}'),
    ],
)
def test_python_defaults_variadics_and_keyword_binding_are_preserved(parameters, arguments):
    assert codes(source(parameters, arguments)) == ()


@pytest.mark.parametrize("field", ["user_draft", "maintainer_summary"])
def test_finding_covers_either_draft_and_default_syntax_check_stays_separate(field):
    assert codes(source(), field=field) == ("callback_arity_mismatch",)
    assert has_invalid_python_code(proposal(source(), field=field)) is False


def test_zero_argument_rewrite_and_intentional_old_snapshot_are_valid():
    rewritten = source("", body='st.session_state["saved"] = st.session_state["choice"]')
    snapshot = source("old_value", 'args=(st.session_state["choice"],)')
    assert codes(rewritten) == codes(snapshot) == ()


def test_form_submit_callback_uses_its_own_pinned_documentation():
    probe = next(
        probe for probe in SUITE.cases if probe.id == "synthetic-form-submit-exact-parameter"
    )
    assert codes(source(widget="form_submit_button"), evidence=probe.bundles[0]) == (
        "callback_arity_mismatch",
    )
    assert (
        codes(source("value", "args=(1,)", widget="form_submit_button"), evidence=probe.bundles[0])
        == ()
    )


def test_signature_alone_never_establishes_how_the_widget_invokes_a_callback():
    hits = tuple(hit for hit in EVIDENCE.hits if "signature" in hit.chunk_id)
    assert (
        codes(source(), evidence=EvidenceBundle(snapshot_id=EVIDENCE.snapshot_id, hits=hits)) == ()
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"source_type": "issue"},
        {"source_commit": "0" * 40},
        {"source_span": None},
        {"source_span": "JSON pointer /1.63.0/streamlit.selectbox; callback args"},
        {"source_url": "https://example.org/python/streamlit.json"},
        {"source_id": "docstring:1.64.0:streamlit.button"},
        {"applicable_versions": ()},
        {"applicable_versions": ("1.63.0",)},
        {"excerpt": "An optional list or tuple of args to pass to the callback."},
        {"excerpt": "args: list or tuple; default=None\nSome arguments."},
    ],
)
def test_callback_argument_documentation_requires_matching_pinned_metadata(updates):
    hits = tuple(
        hit.model_copy(update=updates) if hit.chunk_id == "selectbox-164-callback-v4" else hit
        for hit in EVIDENCE.hits
    )
    assert (
        codes(source(), evidence=EvidenceBundle(snapshot_id=EVIDENCE.snapshot_id, hits=hits)) == ()
    )


def test_signature_must_also_come_from_the_reviewed_commit():
    hits = tuple(
        hit.model_copy(
            update={
                "source_commit": "0" * 40,
                "source_url": "https://github.com/streamlit/docs/blob/"
                + "0" * 40
                + "/python/streamlit.json",
            }
        )
        if "signature" in hit.chunk_id
        else hit
        for hit in EVIDENCE.hits
    )
    assert (
        codes(source(), evidence=EvidenceBundle(snapshot_id=EVIDENCE.snapshot_id, hits=hits)) == ()
    )


@pytest.mark.parametrize(
    "state", [CaseState(case_id="unknown"), PROBE.case_state.model_copy(update={"facts": ()})]
)
def test_unknown_user_version_cannot_enable_arity_check(state):
    assert codes(source(), state=state) == ()


@pytest.mark.parametrize(
    "transform",
    [
        lambda code: code.replace("on_change=callback", "on_change=cb").replace(
            "st.selectbox", "cb = callback\nst.selectbox"
        ),
        lambda code: code + "\ncallback = replacement",
        lambda code: code + "\ndef callback(value=1):\n    pass",
        lambda code: code + "\ndef other():\n    callback = replacement",
        lambda code: code + "\ndef other(callback):\n    pass",
        lambda code: code + "\ndef other():\n    global callback",
        lambda code: code + "\ncallback.__defaults__ = (1,)",
        lambda code: code + '\ncallback.__kwdefaults__.update({"value": 1})',
        lambda code: code + "\ncallback.__code__ = replacement.__code__",
        lambda code: code + '\nsetattr(callback, "__defaults__", (1,))',
        lambda code: code.replace("def callback", "@decorate\ndef callback"),
        lambda code: code.replace("def callback", "async def callback"),
        lambda code: code.replace("def callback(value)", "def callback(value, value)"),
        lambda code: code.replace("def callback(value)", "def callback(value, *value)"),
        lambda code: code.replace("st.selectbox", "if enabled:\n    st.selectbox"),
        lambda code: code.replace("st.selectbox", "def register():\n    st.selectbox"),
        lambda code: code.replace("st.selectbox", "with container:\n    st.selectbox"),
        lambda code: code.replace("def callback", "if enabled:\n    def callback").replace(
            "\n    pass", "\n        pass"
        ),
        lambda code: code + "\nimport opaque_package",
        lambda code: code + "\nopaque_helper()",
        lambda code: code.replace("def callback", "opaque_helper()\ndef callback"),
        lambda code: code.replace(
            "def callback", "def other(value=opaque_helper()):\n    pass\ndef callback"
        ),
        lambda code: code.replace(
            "def callback", "def other(value: opaque_helper()):\n    pass\ndef callback"
        ),
        lambda code: code.replace('"Choice"', "opaque_label()"),
        lambda code: code.replace('"Choice"', "label_property.value"),
        lambda code: code.replace('"Choice"', 'custom["label"]'),
        lambda code: code.replace('"Choice"', "(callback := replacement)"),
        lambda code: code.replace("st.selectbox", "target.registration = st.selectbox"),
        lambda code: code.replace("st.selectbox", 'target["registration"] = st.selectbox'),
        lambda code: code.replace(
            "st.selectbox", "registration: annotation_factory() = st.selectbox"
        ),
        lambda code: code.replace("on_change=callback", "on_change=object.callback"),
        lambda code: code.replace("on_change=callback", "on_change=lambda: callback(1)"),
        lambda code: code.replace("as st", "as ui"),
        lambda code: code + "\nst = custom_streamlit",
    ],
)
def test_dynamic_bindings_context_and_evaluation_effects_cause_abstention(transform):
    assert codes(transform(source())) == ()


@pytest.mark.parametrize(
    "arguments",
    [
        "args=external_args",
        "kwargs=external_kwargs",
        "args=(*external_args,)",
        'kwargs={**external_kwargs, "value": 1}',
        "kwargs={key_name: 1}",
        "args=(opaque_value(),)",
        "args=(lambda value=opaque_value(): value,)",
        "args=[value for value in values]",
        "args=(value for value in values)",
        "**external_widget_keywords",
        "on_change=callback",
    ],
)
def test_opaque_argument_containers_and_duplicate_widget_parameters_are_not_counted(arguments):
    assert codes(source("first, second", arguments)) == ()


def test_registration_must_follow_handler_definition_and_module_import():
    original = source()
    lines = original.splitlines()
    late_definition = "\n".join((lines[0], lines[-1], *lines[1:-1]))
    late_import = "\n".join((*lines[1:], lines[0]))
    assert codes(late_definition) == codes(late_import) == ()


def test_different_fences_are_not_combined_into_a_complete_binding():
    result = proposal("import streamlit as st\ndef callback(value):\n    pass")
    result = result.model_copy(
        update={
            "maintainer_summary": '```python\nst.selectbox("Choice", [1, 2], on_change=callback)\n```'
        }
    )
    assert callback_code_issues(result, PROBE.case_state, EVIDENCE) == ()


@pytest.mark.parametrize("language", ["", "text", "javascript"])
def test_only_complete_labeled_python_fences_qualify(language):
    assert (
        callback_code_issues(proposal(source(), language=language), PROBE.case_state, EVIDENCE)
        == ()
    )


def test_plain_name_assignment_registration_can_qualify():
    assert codes(source().replace("st.selectbox", "selected = st.selectbox")) == (
        "callback_arity_mismatch",
    )


@pytest.mark.parametrize("alias", ["ui", "streamlit"])
def test_unshadowed_explicit_module_aliases_can_qualify(alias):
    code = source().replace("as st", f"as {alias}").replace("st.selectbox", f"{alias}.selectbox")
    assert codes(code) == ("callback_arity_mismatch",)


def test_unaliased_module_import_can_qualify():
    code = (
        source()
        .replace("import streamlit as st", "import streamlit")
        .replace("st.selectbox", "streamlit.selectbox")
    )
    assert codes(code) == ("callback_arity_mismatch",)


def test_resource_limits_cause_no_semantic_finding(monkeypatch):
    monkeypatch.setattr(proposal_checks, "_MAX_AST_NODES", 1)
    assert codes(source()) == ()


def test_no_snippet_execution_or_raw_diagnostics(tmp_path, capsys):
    marker = tmp_path / "must-not-be-created.txt"
    code = source(body=f"open({str(marker)!r}, 'w').write('executed')")
    issues = callback_code_issues(proposal(code), PROBE.case_state, EVIDENCE)
    assert [issue.code for issue in issues] == ["callback_arity_mismatch"]
    assert all(issue.field is None for issue in issues)
    assert "callback" not in "".join(issue.model_dump_json() for issue in issues).replace(
        "callback_arity_mismatch", ""
    )
    assert str(marker) not in "".join(issue.model_dump_json() for issue in issues)
    assert not marker.exists()
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
