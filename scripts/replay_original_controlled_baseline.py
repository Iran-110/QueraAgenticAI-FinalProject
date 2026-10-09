"""Replay V8 on the original registered Git code, without changing the checkout.

Only trusted repository Python is imported; evidence/proposal snippets are data.
No gateway, environment file, model request, or tracker store is used.
"""

import argparse
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from agent_app.reasoning.controlled_experiments import load_controlled_pack

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "dad3202db11cff8331718c6a5d58df834c49c79c"
CHILD = """
import sys, json, importlib.machinery
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[2]) / 'src'))
sys.meta_path.insert(0, importlib.machinery.PathFinder)
import agent_app
from agent_app.contracts import CaseState, EvidenceBundle
from agent_app.orchestration import SupportEngine
from agent_app.testing.fakes import FakeRetriever, FakeReasoner
assert Path(agent_app.__file__).resolve().is_relative_to(Path(sys.argv[2]).resolve())
suite = json.loads(Path(sys.argv[1]).read_text()); rows = []
for case in suite['cases']:
    for replay in case['authored_replays']:
        reasoner = FakeReasoner(replay['sequence'])
        engine = SupportEngine(
            FakeRetriever([EvidenceBundle.model_validate(b) for b in case['bundles']]),
            reasoner, snapshot_id=suite['snapshot_id'])
        result = engine.run(CaseState.model_validate(case['case_state']),
                            case['user_message'], run_id='baseline:' + replay['id'])
        observed = {'status': result.status,
                    'final_decision': result.analysis.decision if result.analysis else None,
                    'error_code': result.error_code,
                    'model_attempts': result.model_attempts,
                    'retrieval_rounds': result.retrieval_rounds}
        assert observed == replay['expected_by_scope']['all']
        rows.append({'case_id': case['id'], 'replay_id': replay['id'],
                     'control': replay['control'], 'observed': observed,
                     'reasoner_chunk_ids': [[h.chunk_id for h in inp[2].hits]
                                            for inp in reasoner.inputs]})
print(json.dumps(rows))
"""


def replay_original_baseline() -> dict:
    pack = load_controlled_pack()
    with tempfile.TemporaryDirectory(prefix="core-original-baseline-") as target:
        archived = subprocess.run(
            ["git", "archive", BASELINE, "src/agent_app"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        with tarfile.open(fileobj=io.BytesIO(archived)) as archive:
            archive.extractall(target, filter="data")
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                CHILD,
                str(ROOT / "experiments/decision_quality/cases-controlled-v8.json"),
                target,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if result.returncode:
            # Do not export child traceback/input-bearing validation details.
            raise ValueError("Original baseline replay failed.")
        rows = json.loads(result.stdout)
    return {
        "mode": "offline_authored_replay_on_original_git_code",
        "baseline_git_commit": BASELINE,
        "registration_git_commit": "8814fbb",
        "suite_sha256": pack.protocol["suite_sha256"],
        "real_api_calls": 0,
        "paid_cost_usd": "0",
        "original_default_scope": "all",
        "observations": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = replay_original_baseline()
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as destination:
            destination.write(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
