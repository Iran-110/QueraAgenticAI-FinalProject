"""GET-only presentation preflight, separate from any model/funding operation.

Run from the project root. No dotenv/token is read, no POST is sent, and no
scope is created, closed or refilled. Software and artifact observations never
become a model-quality score. Report bodies and exception details are omitted.
"""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from agent_app.llm.budget import BudgetLedger
from agent_app.presentation_runtime import read_protocol
from agent_app.ui_client import BackendClient

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = (
    "judges-presentation-fa-v2.pdf",
    "judges-presentation-fa-v2.html",
    "judges-presentation-fa-v2-content.json",
)


_INDEX_CHILD = r"""
import json, os, sys
from pathlib import Path
blocked = []
network_attempts = 0
def audit(event, args):
    global network_attempts
    if event in ('open', 'sqlite3.connect'):
        value = args[0]
        if isinstance(value, (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(value))
            parts = path.parts
            if (path.name in {'.env', 'reviewer-token.txt', 'budget.sqlite3',
                             'test-card-review-v1.json', 'native-test-gold-review-v1.json',
                             'native-test-exposure-decision-v1.json', 'exposure-frozen-v1.json',
                             'native-registration-test-v1.json'}
                or path.name.startswith('evidence-test')
                or ('split-e1-v1' in parts and 'test' in parts)):
                blocked.append('ProtectedInputRejected')
                raise PermissionError('ProtectedInputRejected')
    elif event == 'socket.connect':
        network_attempts += 1
        blocked.append('NetworkRejected')
        raise PermissionError('NetworkRejected')
sys.addaudithook(audit)
verified = False
client = None
close_available = False
try:
    from agent_app.evaluation.live import _verified_index
    client = _verified_index(sys.argv[1], sys.argv[2], sys.argv[3])
    client.verify()
    verified = True
except Exception:
    pass
finally:
    if client is not None:
        close = getattr(client, 'close', None)
        close_available = callable(close)
        if close_available:
            try:
                close()
            except Exception:
                verified = False
print(json.dumps({'schema_version':1,'verified':verified,'blocked':blocked,
                  'network_connect_attempts':network_attempts,
                  'client_close_available':close_available,
                  'cleanup':'verifier_process_exit',
                  'audit_scope':'child Python audit events; native calls not attested'}))
"""


def _verify_physical_index(path, snapshot_id, manifest_sha256):
    """Verify in a neutral child: Chroma Settings must not discover repository .env.

    The child receives public index arguments only. Its own audit denies private
    inputs and Python socket connections. The parent's audit cannot attest child
    I/O; this returned observation deliberately states that narrower boundary.
    """
    environment = {
        name: os.environ[name]
        for name in (
            "HOME",
            "USER",
            "LOGNAME",
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "TZ",
            "SYSTEMROOT",
            "WINDIR",
        )
        if name in os.environ
    }
    environment.update(
        PATH=os.defpath,
        PYTHONPATH=str(ROOT / "src"),
        PYTHONUTF8="1",
        PYTHONDONTWRITEBYTECODE="1",
        ANONYMIZED_TELEMETRY="False",
    )
    try:
        with tempfile.TemporaryDirectory(prefix="presentation-index-check-") as working:
            completed = subprocess.run(
                [sys.executable, "-c", _INDEX_CHILD, str(path), snapshot_id, manifest_sha256],
                cwd=working,
                env=environment,
                capture_output=True,
                text=True,
                timeout=40,
                check=False,
            )
        # Native/import diagnostics are never copied into the public report.
        observation = json.loads(completed.stdout.strip().splitlines()[-1])
        if (
            completed.returncode != 0
            or type(observation) is not dict
            or type(observation.get("schema_version")) is not int
            or observation["schema_version"] != 1
            or observation.get("verified") is not True
            or observation.get("blocked") != []
            or type(observation.get("network_connect_attempts")) is not int
            or observation["network_connect_attempts"] != 0
            or type(observation.get("client_close_available")) is not bool
            or observation.get("cleanup") != "verifier_process_exit"
            or observation.get("audit_scope")
            != "child Python audit events; native calls not attested"
        ):
            raise ValueError
        return observation
    except Exception:
        raise ValueError("PhysicalIndexUnverified") from None


class VisibleCopy(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ignored = 0
        self.text = []
        self.slides = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"style", "script"}:
            self.ignored += 1
        if tag == "section" and "slide" in dict(attrs).get("class", "").split():
            self.slides += 1

    def handle_endtag(self, tag):
        if tag in {"style", "script"}:
            self.ignored = max(0, self.ignored - 1)

    def handle_data(self, value):
        if not self.ignored:
            self.text.append(value)


def _read(path, maximum=4_000_000):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("PublicArtifactRejected")
    resolved = path.resolve()
    if resolved.is_relative_to(ROOT / "data") or resolved.name == ".env":
        raise ValueError("PublicArtifactRejected")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > maximum:
        raise ValueError("PublicArtifactRejected")
    return path.read_bytes()


def artifact_checks(directory, qa_path):
    """Bind exact deliverable bytes to visual QA; this is not automatic visual QA."""
    result = {"verified": False, "visual_review_replaced": False}
    try:
        directory = Path(directory)
        if directory.is_symlink() or Path(qa_path).name != "judges-v2-qa.json":
            raise ValueError
        qa = json.loads(_read(qa_path))
        if (
            not isinstance(qa, dict)
            or not isinstance(qa.get("manual_visual_review"), dict)
            or not isinstance(qa.get("output_sha256"), dict)
        ):
            raise ValueError
        if (
            type(qa.get("schema_version")) is not int
            or qa["schema_version"] != 1
            or qa.get("parent_content_review_accepted") is not True
            or qa.get("layout_overflow_pages") != []
            or qa.get("manual_visual_review", {}).get(
                "all13_actual_pdf_pages_poppler_rendered_and_inspected"
            )
            is not True
        ):
            raise ValueError
        raw = {name: _read(directory / name) for name in ARTIFACTS}
        hashes = {name: hashlib.sha256(value).hexdigest() for name, value in raw.items()}
        if any(qa["output_sha256"].get(name) != digest for name, digest in hashes.items()):
            raise ValueError
        if not raw[ARTIFACTS[0]].startswith(b"%PDF-"):
            raise ValueError
        copy = VisibleCopy()
        copy.feed(raw[ARTIFACTS[1]].decode("utf-8"))
        slides = json.loads(raw[ARTIFACTS[2]])
        fields = {"title", "body", "eyebrow", "foot", "cls"}
        if (
            copy.slides != 13
            or type(qa["pdf_pages"]) is not int
            or qa["pdf_pages"] != 13
            or not isinstance(slides, list)
            or len(slides) != 13
            or any(
                not isinstance(slide, dict)
                or slide.keys() != fields
                or any(type(value) is not str for value in slide.values())
                or not slide["title"].strip()
                for slide in slides
            )
        ):
            raise ValueError
        text = " ".join(copy.text)
        # Deliberately narrow editorial controls. A manual audience/content
        # review is still necessary; these are not a semantics classifier.
        patterns = (
            r"\b(?:A[123]|B[12]|C[12])\b",
            r"سؤال(?:‌|\s)*های احتمالی",
            r"پرسش(?:‌|\s)*های احتمالی",
            r"start-live-demo",
            r"reviewer-token",
            r"127\.0\.0\.1",
            r"متن (?:آماده|آزمایش|تست) را (?:وارد|کپی)",
        )
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            raise ValueError
        result.update(verified=True, pages=13, sha256=hashes)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        result["error_code"] = "PresentationArtifactsUnverified"
    return result


def loopback_url(value):
    """No redirects, external destinations, credentials or implicit proxy use."""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.port is None
    ):
        raise ValueError("LoopbackBaseUrlRequired")
    return value.rstrip("/")


def session_checks(
    protocol_path,
    *,
    api_url,
    ui_url,
    viewer_url=None,
    watch_path=None,
    watch_sha256=None,
    transport=None,
):
    """Read current capacity, not just 14 minus the number of paid requests.

    Unused second attempts of already committed turns are not new message slots.
    A fully used 3/2/2-case pool is exhausted even when the financial scope has
    unused request identities and money remaining.
    """
    result = {"ready": False, "provider_probe": "not_performed", "request_method": "GET"}
    try:
        api_url, ui_url = loopback_url(api_url), loopback_url(ui_url)
        viewer_url = loopback_url(viewer_url) if viewer_url else None
        protocol, digest, slots = read_protocol(protocol_path)
        result["source_verification"] = "funded_21_file_subset"
        if watch_path is not None or watch_sha256 is not None:
            from agent_app.presentation_release import validate_watch

            validate_watch(protocol_path, watch_path, expected_sha256=watch_sha256)
            result["source_verification"] = "funded_subset_and_additive_release_inventory"
        # A valid protocol only declares index pins. Verify the actual stored
        # records/manifest too: GET health and case endpoints never retrieve and
        # can stay healthy after this separate storage disappears or changes.
        index = protocol["index"]
        index_observation = _verify_physical_index(
            index["path"], index["snapshot_id"], index["index_manifest_sha256"]
        )
        result["index_verification"] = "verified_physical_manifest_snapshot_and_records"
        result["index_probe"] = index_observation
        ledger = BudgetLedger(protocol["ledger_path"])
        status = ledger.quarantine_scope_status(protocol["scope_id"])
        snapshot = ledger.snapshot()
        result.update(
            scope_active=status.active,
            consumed_requests=status.consumed_requests,
            maximum_requests=status.max_requests,
            remaining_usd=str(status.remaining_usd),
            global_halt=snapshot.halted,
            c5_reconciled=False,
            provider_key_read=False,
        )
        if (
            not status.active
            or status.protocol_sha256 != digest
            or status.max_requests != len(slots)
            or status.remaining_usd < min(slot.amount_usd for slot in slots)
            or not snapshot.halted
        ):
            raise ValueError
        with httpx.Client(
            timeout=5, follow_redirects=False, trust_env=False, transport=transport
        ) as http:
            client = BackendClient(_AtBase(http, api_url))
            capabilities = client.discover_capabilities()
            if (
                not capabilities.durable_reviews
                or not capabilities.message_auth
                or capabilities.reasoning_label != "metis_grounded_live"
                or capabilities.retrieval_label != "local_chroma_hash"
            ):
                raise ValueError
            # No credential is supplied. BackendClient validates the complete
            # displayed case/handoff and refuses a cross-case response.
            remaining_turns, per_case = 0, []
            for case in protocol["cases"]:
                view = client.get_case(case["case_id"])
                revision = view["case_revision"]
                allowed = case["revisions"]
                if type(revision) is not int or revision not in [0, *allowed]:
                    raise ValueError
                # A reset/missing tracker must not look like a fresh funded
                # case when the ledger already records a later model attempt.
                for slot in slots:
                    if slot.case_id == case["case_id"]:
                        recorded = ledger.get(slot.request_id)
                        if recorded is not None and recorded.case_revision > revision:
                            result["error_code"] = "PresentationTrackerBehindLedger"
                            return result
                remaining = sum(value > revision for value in allowed)
                remaining_turns += remaining
                per_case.append({"revision": revision, "remaining_turns": remaining})
            result.update(remaining_message_turns=remaining_turns, case_capacity=per_case)
            if remaining_turns == 0:
                result["error_code"] = "PresentationTurnPoolExhausted"
                return result
            for base in (ui_url, viewer_url):
                if base is not None:
                    response = http.get(base + "/_stcore/health")
                    if response.status_code != 200 or response.content.strip() != b"ok":
                        raise ValueError
            result["ready"] = True
    except Exception:
        # Raw validation/provider/http bodies and arbitrary exception strings
        # have no place in a screen-shared health report.
        result["error_code"] = "PresentationSessionUnverified"
    return result


class _AtBase:
    def __init__(self, http, base):
        self.http, self.base = http, base

    def request(self, method, url, **kwargs):
        if method != "GET" or kwargs.get("headers") or kwargs.get("json"):
            raise ValueError("ReadOnlyPreflight")
        return self.http.request(method, self.base + url, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--qa", required=True, type=Path)
    parser.add_argument("--api", default="http://127.0.0.1:8001")
    parser.add_argument("--ui", default="http://127.0.0.1:8502")
    parser.add_argument("--viewer")
    parser.add_argument("--watch", type=Path)
    parser.add_argument("--watch-sha256")
    args = parser.parse_args()
    artifacts = artifact_checks(args.artifacts, args.qa)
    session = session_checks(
        args.protocol,
        api_url=args.api,
        ui_url=args.ui,
        viewer_url=args.viewer,
        watch_path=args.watch,
        watch_sha256=args.watch_sha256,
    )
    report = {
        "schema_version": 1,
        "operator_ready": artifacts["verified"] and session["ready"],
        "artifacts": artifacts,
        "session": session,
        "model_quality": "partial, requires separate source/human review",
        "heldout_evaluation": "not performed by this healthcheck",
        "financial_authorization": False,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["operator_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
