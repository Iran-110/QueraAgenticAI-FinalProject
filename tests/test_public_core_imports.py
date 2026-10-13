"""Cold installed-package imports must not rely on pytest's import ordering."""

import subprocess
import sys

import pytest


def _fresh_python(tmp_path, script):
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    "first_import",
    [
        "from agent_app.reasoning.grounding import GroundedReasoner",
        "from agent_app.orchestration.ports import GroundedPlanner",
        "from agent_app.orchestration.handoff import validate_handoff",
        "from agent_app.orchestration.service import CoreTurnService",
        "from agent_app.orchestration.engine import SupportEngine",
        "from agent_app.orchestration import CoreAdapters",
        "from agent_app.orchestration import CoreTurnOutcome",
        "from agent_app.orchestration import CoreTurnService",
        "from agent_app.orchestration import SupportEngine",
    ],
)
def test_public_core_imports_work_first_in_a_fresh_process(tmp_path, first_import):
    _fresh_python(
        tmp_path,
        first_import
        + """
from agent_app.reasoning.grounding import GroundedReasoner
from agent_app.orchestration import (
    SupportEngine, CoreAdapters, CoreTurnOutcome, CoreTurnService,
)
from agent_app.orchestration.engine import SupportEngine as Engine
from agent_app.orchestration.service import (
    CoreAdapters as Adapters, CoreTurnOutcome as Outcome, CoreTurnService as Service,
)
assert SupportEngine is Engine
assert CoreAdapters is Adapters
assert CoreTurnOutcome is Outcome
assert CoreTurnService is Service
""",
    )


def test_ports_import_does_not_initialize_high_level_services(tmp_path):
    _fresh_python(
        tmp_path,
        """
import sys
from agent_app.orchestration.ports import GroundedPlanner
assert 'agent_app.orchestration.service' not in sys.modules
assert 'agent_app.orchestration.handoff' not in sys.modules
from agent_app.reasoning.grounding import GroundedReasoner
assert 'agent_app.orchestration.service' not in sys.modules
assert 'agent_app.orchestration.handoff' not in sys.modules
""",
    )


def test_package_exports_remain_discoverable_and_support_star_import(tmp_path):
    _fresh_python(
        tmp_path,
        """
import agent_app.orchestration as public
expected = ['SupportEngine', 'CoreAdapters', 'CoreTurnOutcome', 'CoreTurnService']
assert public.__all__ == expected
assert set(expected) <= set(dir(public))
assert not hasattr(public, 'UnknownCoreExport')
namespace = {}
exec('from agent_app.orchestration import *', namespace)
for name in expected:
    assert namespace[name] is getattr(public, name)
    assert getattr(public, name) is getattr(public, name)
assert not hasattr(public, 'UnknownCoreExport')
""",
    )


def test_grounding_first_can_execute_an_offline_core_turn(tmp_path):
    _fresh_python(
        tmp_path,
        """
from agent_app.reasoning.grounding import GroundedReasoner, make_grounded_request
from agent_app.contracts import CaseState, EvidenceBundle, GroundedPlan
from agent_app.orchestration import SupportEngine
from agent_app.orchestration.handoff import ReasoningCapture, build_handoff, validate_handoff
from agent_app.testing.fakes import FakeRetriever

requests = []
def request_factory(case, message, evidence):
    request = make_grounded_request(case, message, evidence)
    requests.append(request)
    return request

class Planner:
    def plan(self, request, *, context):
        return GroundedPlan(context_sha256=request.context_sha256, decision='escalate')

capture = ReasoningCapture(GroundedReasoner(Planner(), request_factory=request_factory))
engine = SupportEngine(
    FakeRetriever([EvidenceBundle(snapshot_id='cold-import-fixture')]),
    capture,
    snapshot_id='cold-import-fixture',
)
result = engine.run(CaseState(case_id='cold-import-case'), 'The widget resets.')
assert result.status == 'awaiting_approval'
handoff = build_handoff(result, capture.last, grounded_request=requests[-1])
assert validate_handoff(handoff).analysis.decision == 'escalate'
""",
    )
