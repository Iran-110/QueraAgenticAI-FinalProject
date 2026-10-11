"""Durable, local-only tracker for the Streamlit support pilot.

All authoritative case mutations, event receipts, proposal handoffs, reviews and
local comment actions share one SQLite database. Every mutation uses an IMMEDIATE
transaction; the model and source documents never authorize tools.

This module deliberately does not replace the offline HTTP adapter automatically.
The API/UI owners must connect their ingress and authenticated reviewer boundary.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import ValidationError

from agent_app.contracts import (
    AnalysisResult,
    ApprovedReplyQuestion,
    CaseState,
    ProposalHandoff,
    UserTurn,
)
from agent_app.orchestration.handoff import (
    HandoffRejected,
    edit_handoff,
    ensure_handoff_current,
    validate_handoff,
)
from agent_app.orchestration.intake import IntakeRejected, prepare_approved_version_reply
from agent_app.orchestration.turns import UserTurnRejected, propose_user_turn


class TrackerRejected(ValueError):
    """Stable, non-sensitive error code for an operational rejection."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _model_json(value: Any) -> str:
    return _json(value.model_dump(mode="json"))


class SQLiteCaseTracker:
    """SQLite implementation of T1–T3 with explicit reviewer credentials.

    ``reviewer_tokens`` must be supplied by trusted application configuration,
    not user/model content. Empty configuration fails closed for review actions.
    Only local comments are written; no GitHub or real-user writes are performed.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        reviewer_tokens: Mapping[str, str] | None = None,
    ) -> None:
        self.path = Path(path)
        if str(self.path) == ":memory:":
            raise TrackerRejected("PersistentPathRequired")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._reviewer_hashes = {
            name: hashlib.sha256(token.encode("utf-8")).digest()
            for name, token in (reviewer_tokens or {}).items()
            if name and token
        }
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    awaiting_reply_json TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    case_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    PRIMARY KEY (case_id, event_id)
                );
                CREATE TABLE IF NOT EXISTS proposals (
                    case_id TEXT NOT NULL,
                    proposal_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    handoff_json TEXT NOT NULL,
                    lifecycle TEXT NOT NULL,
                    parent_proposal_id TEXT,
                    PRIMARY KEY (case_id, proposal_id)
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    case_id TEXT NOT NULL,
                    review_id TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    PRIMARY KEY (case_id, review_id)
                );
                CREATE TABLE IF NOT EXISTS local_comments (
                    case_id TEXT NOT NULL,
                    proposal_id TEXT NOT NULL,
                    action_id TEXT NOT NULL UNIQUE,
                    reviewer_id TEXT NOT NULL,
                    body TEXT NOT NULL,
                    PRIMARY KEY (case_id, proposal_id)
                );
                CREATE TABLE IF NOT EXISTS conversation (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    reference_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    body TEXT NOT NULL,
                    UNIQUE (case_id, actor, reference_id)
                );
                CREATE TABLE IF NOT EXISTS audit (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.path), isolation_level=None, timeout=10)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 10000")
            yield connection
        finally:
            # Closing an uncommitted SQLite transaction rolls it back on errors.
            connection.close()

    @staticmethod
    def _begin(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")

    @staticmethod
    def _audit(connection: sqlite3.Connection, case_id: str, event: str, data: Any) -> None:
        # No credentials or arbitrary raw source/user content in the audit table.
        connection.execute(
            "INSERT INTO audit(case_id,event_type,details_json) VALUES(?,?,?)",
            (case_id, event, _json(data)),
        )

    @staticmethod
    def _load(connection: sqlite3.Connection, case_id: str) -> tuple[CaseState, str, str | None]:
        record = connection.execute(
            "SELECT state_json,status,awaiting_reply_json FROM cases WHERE case_id=?",
            (case_id,),
        ).fetchone()
        if record is None:
            return CaseState(case_id=case_id), "new", None
        return (
            CaseState.model_validate_json(record["state_json"]),
            record["status"],
            record["awaiting_reply_json"],
        )

    @staticmethod
    def _save(
        connection: sqlite3.Connection,
        state: CaseState,
        status: str,
        awaiting_reply_json: str | None,
    ) -> None:
        connection.execute(
            """INSERT INTO cases(case_id,state_json,status,awaiting_reply_json)
            VALUES(?,?,?,?) ON CONFLICT(case_id) DO UPDATE SET
            state_json=excluded.state_json, status=excluded.status,
            awaiting_reply_json=excluded.awaiting_reply_json""",
            (state.case_id, _model_json(state), status, awaiting_reply_json),
        )

    def read_case(self, case_id: str) -> dict[str, Any]:
        # Read must not create a case. Input validation also protects read paths.
        CaseState(case_id=case_id)
        with self._connect() as connection:
            # Keep state, proposal, reply and conversation on one read snapshot.
            # Without BEGIN, concurrent commits can mix different revisions
            # across these SELECTs even though every writer is transactional.
            connection.execute("BEGIN")
            state, status, reply = self._load(connection, case_id)
            pending = None
            if state.pending_proposal_id:
                row = connection.execute(
                    "SELECT handoff_json FROM proposals WHERE case_id=? AND proposal_id=?",
                    (case_id, state.pending_proposal_id),
                ).fetchone()
                if row is None:
                    raise TrackerRejected("PendingProposalMissing")
                pending = json.loads(row["handoff_json"])
            history = [
                {
                    "actor": row["actor"],
                    "reference_id": row["reference_id"],
                    "revision": row["revision"],
                    "text": row["body"],
                }
                for row in connection.execute(
                    "SELECT actor,reference_id,revision,body FROM conversation "
                    "WHERE case_id=? ORDER BY sequence",
                    (case_id,),
                )
            ]
            result = {
                "state": state.model_dump(mode="json"),
                "history": history,
                "status": status,
                "pending_handoff": pending,
                "awaiting_reply": json.loads(reply) if reply else None,
            }
            connection.commit()
            return result

    def apply_turn(
        self,
        turn: UserTurn,
        *,
        reply_to_proposal_id: str | None = None,
        event_context: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Deduplicate ORIGINAL event before checking revision or preparing a reply.

        The original payload and reply binding are hashed. Preparation can change
        the turn, but must never change the caller-supplied event identity.
        """
        turn = UserTurn.model_validate(turn.model_dump(mode="json"))
        event_context = dict(event_context or {})
        if not all(type(key) is str and type(value) is str for key, value in event_context.items()):
            raise TrackerRejected("InvalidEventContext")
        identity = _hash(
            {
                "turn": turn.model_dump(mode="json"),
                "reply_to_proposal_id": reply_to_proposal_id,
                "context": event_context,
            }
        )
        with self._connect() as db:
            self._begin(db)
            previous = db.execute(
                "SELECT payload_sha256,receipt_json FROM events WHERE case_id=? AND event_id=?",
                (turn.case_id, turn.turn_id),
            ).fetchone()
            if previous is not None:
                if not secrets.compare_digest(previous["payload_sha256"], identity):
                    raise TrackerRejected("EventConflict")
                receipt = json.loads(previous["receipt_json"])
                db.commit()
                return {**receipt, "replayed": True}

            state, _status, reply_data = self._load(db, turn.case_id)
            if turn.expected_revision != state.case_revision:
                raise TrackerRejected("StaleRevision")
            prepared = turn
            preparation = (
                "structured" if turn.reported_facts or turn.checks_performed else "unstructured"
            )
            if reply_to_proposal_id is not None:
                if reply_data is None or any(
                    (
                        turn.reported_facts,
                        turn.checks_performed,
                        turn.unknowns,
                        turn.context_changed,
                    )
                ):
                    raise TrackerRejected("PendingReplyMissing")
                try:
                    prepared = prepare_approved_version_reply(
                        state,
                        turn,
                        reply=ApprovedReplyQuestion.model_validate_json(reply_data),
                        proposal_id=reply_to_proposal_id,
                    )
                except IntakeRejected as error:
                    raise TrackerRejected(error.code) from None
                preparation = "canonical_version_reply"
            try:
                transition = propose_user_turn(state, prepared)
            except UserTurnRejected as error:
                raise TrackerRejected(error.code) from None

            if state.pending_proposal_id is not None:
                db.execute(
                    """UPDATE proposals SET lifecycle='stale'
                    WHERE case_id=? AND proposal_id=? AND lifecycle='pending'""",
                    (turn.case_id, state.pending_proposal_id),
                )
            candidate = transition.candidate
            receipt = {
                "case_id": turn.case_id,
                "turn_id": turn.turn_id,
                "ingress_hash": identity,
                "prepared_hash": transition.event_hash,
                "committed_revision": candidate.case_revision,
                "changed_fact_names": list(transition.changed_fact_names),
                "context_changed": transition.context_changed,
                "invalidated_checks": list(transition.invalidated_checks),
                "preparation": preparation,
                "replayed": False,
            }
            self._save(db, candidate, "open", None)
            db.execute(
                "INSERT INTO conversation(case_id,actor,reference_id,revision,body) "
                "VALUES(?, 'user', ?, ?, ?)",
                (turn.case_id, turn.turn_id, candidate.case_revision, turn.message),
            )
            db.execute(
                "INSERT INTO events(case_id,event_id,payload_sha256,receipt_json) VALUES(?,?,?,?)",
                (turn.case_id, turn.turn_id, identity, _json(receipt)),
            )
            self._audit(
                db,
                turn.case_id,
                "turn_committed",
                {"turn_id": turn.turn_id, "revision": candidate.case_revision},
            )
            db.commit()
            return receipt

    def stage_proposal(self, handoff: ProposalHandoff) -> dict[str, Any]:
        try:
            handoff = validate_handoff(handoff)
        except HandoffRejected as error:
            raise TrackerRejected(error.code) from None
        with self._connect() as db:
            self._begin(db)
            state, _status, reply = self._load(db, handoff.case.case_id)
            if state.case_revision != handoff.case.case_revision:
                raise TrackerRejected("StaleRevision")
            if state.pending_proposal_id is not None:
                raise TrackerRejected("PendingProposalMismatch")
            if state != handoff.case:
                raise TrackerRejected("CaseContentMismatch")
            if db.execute(
                "SELECT 1 FROM proposals WHERE case_id=? AND proposal_id=?",
                (state.case_id, handoff.proposal_id),
            ).fetchone():
                raise TrackerRejected("ProposalConflict")
            db.execute(
                """INSERT INTO proposals(case_id,proposal_id,revision,handoff_json,lifecycle)
                VALUES(?,?,?,?, 'pending')""",
                (state.case_id, handoff.proposal_id, state.case_revision, _model_json(handoff)),
            )
            self._save(
                db,
                state.model_copy(update={"pending_proposal_id": handoff.proposal_id}),
                "awaiting_review",
                reply,
            )
            self._audit(
                db,
                state.case_id,
                "proposal_staged",
                {"proposal_id": handoff.proposal_id, "revision": state.case_revision},
            )
            db.commit()
            return {
                "case_id": state.case_id,
                "proposal_id": handoff.proposal_id,
                "revision": state.case_revision,
            }

    def _require_reviewer(self, reviewer_id: str, reviewer_token: str) -> None:
        # Do not log tokens or hash the ID into a substitute for authentication.
        expected = self._reviewer_hashes.get(reviewer_id)
        if (
            expected is None
            or not isinstance(reviewer_token, str)
            or not secrets.compare_digest(
                expected, hashlib.sha256(reviewer_token.encode("utf-8")).digest()
            )
        ):
            raise TrackerRejected("ReviewerUnauthorized")

    @staticmethod
    def _record_local_comment(
        db: sqlite3.Connection, *, case_id: str, proposal_id: str, reviewer_id: str, body: str
    ) -> str:
        """Local ticket-tool side effect in the SAME transaction; override to inject failures."""
        action_id = _hash({"case_id": case_id, "proposal_id": proposal_id, "kind": "comment"})
        db.execute(
            "INSERT INTO local_comments(case_id,proposal_id,action_id,reviewer_id,body) "
            "VALUES(?,?,?,?,?)",
            (case_id, proposal_id, action_id, reviewer_id, body),
        )
        return action_id

    def review(
        self,
        case_id: str,
        *,
        review_id: str,
        proposal_id: str,
        expected_revision: int,
        expected_handoff_sha256: str,
        decision: Literal["approve", "reject", "edit"],
        reviewer_id: str,
        reviewer_token: str,
        edited_draft: str | None = None,
    ) -> dict[str, Any]:
        """Authenticate, CAS/check exact handoff, then atomically commit local effects.

        Replays of the same review ID with equal payload return the original
        receipt, including after restart. A reused ID with different content
        cannot approve another proposal. Editing always needs new approval.
        """
        self._require_reviewer(reviewer_id, reviewer_token)
        if decision not in ("approve", "reject", "edit"):
            raise TrackerRejected("DecisionInvalid")
        if type(review_id) is not str or not review_id or len(review_id) > 200:
            raise TrackerRejected("ReviewIdInvalid")
        if type(expected_revision) is not int or expected_revision < 0:
            raise TrackerRejected("StaleRevision")
        if (
            type(expected_handoff_sha256) is not str
            or len(expected_handoff_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in expected_handoff_sha256)
        ):
            raise TrackerRejected("HandoffDigestMismatch")
        if edited_draft is not None and (
            type(edited_draft) is not str or len(edited_draft) > 20_000
        ):
            raise TrackerRejected("EditedProposalInvalid")
        if decision == "edit" and not (edited_draft or "").strip():
            raise TrackerRejected("EditedProposalInvalid")
        if decision != "edit" and edited_draft is not None:
            raise TrackerRejected("DecisionInvalid")
        request_hash = _hash(
            {
                "case_id": case_id,
                "review_id": review_id,
                "proposal_id": proposal_id,
                "expected_revision": expected_revision,
                "expected_handoff_sha256": expected_handoff_sha256,
                "decision": decision,
                "reviewer_id": reviewer_id,
                "edited_draft": edited_draft,
            }
        )
        with self._connect() as db:
            self._begin(db)
            previous = db.execute(
                "SELECT request_sha256,receipt_json FROM reviews WHERE case_id=? AND review_id=?",
                (case_id, review_id),
            ).fetchone()
            if previous is not None:
                if not secrets.compare_digest(previous["request_sha256"], request_hash):
                    raise TrackerRejected("ReviewConflict")
                receipt = json.loads(previous["receipt_json"])
                db.commit()
                return {**receipt, "replayed": True}
            state, _status, _reply = self._load(db, case_id)
            if state.case_revision != expected_revision:
                raise TrackerRejected("StaleRevision")
            if state.pending_proposal_id != proposal_id:
                raise TrackerRejected("PendingProposalMismatch")
            row = db.execute(
                """SELECT handoff_json,lifecycle,revision FROM proposals
                WHERE case_id=? AND proposal_id=?""",
                (case_id, proposal_id),
            ).fetchone()
            if row is None or row["lifecycle"] != "pending" or row["revision"] != expected_revision:
                raise TrackerRejected("PendingProposalMismatch")
            try:
                handoff = ProposalHandoff.model_validate_json(row["handoff_json"])
                ensure_handoff_current(handoff, state, proposal_id)
            except (HandoffRejected, ValidationError) as error:
                raise TrackerRejected(getattr(error, "code", "PendingProposalMismatch")) from None

            if not secrets.compare_digest(handoff.handoff_sha256, expected_handoff_sha256):
                raise TrackerRejected("HandoffDigestMismatch")

            next_pending: str | None = None
            action_id: str | None = None
            reply_json = None
            status = "open"
            if decision == "approve":
                # The action is inside the transaction: no partial accept on tool failure.
                action_id = self._record_local_comment(
                    db,
                    case_id=case_id,
                    proposal_id=proposal_id,
                    reviewer_id=reviewer_id,
                    body=handoff.analysis.user_draft,
                )
                db.execute(
                    "INSERT INTO conversation(case_id,actor,reference_id,revision,body) "
                    "VALUES(?, 'assistant', ?, ?, ?)",
                    (case_id, proposal_id, expected_revision, handoff.analysis.user_draft),
                )
                status = {
                    "ask": "awaiting_user",
                    "answer": "answer_sent",
                    "escalate": "escalated",
                }[handoff.analysis.decision]
                if handoff.analysis.decision == "ask":
                    reply_json = _model_json(
                        ApprovedReplyQuestion(
                            case_id=case_id,
                            case_revision=expected_revision,
                            proposal_id=proposal_id,
                            question=handoff.analysis,
                        )
                    )
                db.execute(
                    "UPDATE proposals SET lifecycle='approved' WHERE case_id=? AND proposal_id=?",
                    (case_id, proposal_id),
                )
            elif decision == "reject":
                db.execute(
                    "UPDATE proposals SET lifecycle='rejected' WHERE case_id=? AND proposal_id=?",
                    (case_id, proposal_id),
                )
            else:
                try:
                    draft = (edited_draft or "").strip()
                    original = handoff.analysis
                    edited = AnalysisResult.model_validate(
                        {
                            **original.model_dump(mode="json"),
                            "user_draft": draft,
                            "next_question": draft if original.decision == "ask" else None,
                        }
                    )
                    replacement = edit_handoff(handoff, str(uuid4()), edited)
                except (ValidationError, HandoffRejected):
                    raise TrackerRejected("EditedProposalInvalid") from None
                next_pending = replacement.proposal_id
                db.execute(
                    "UPDATE proposals SET lifecycle='edited' WHERE case_id=? AND proposal_id=?",
                    (case_id, proposal_id),
                )
                db.execute(
                    """INSERT INTO proposals
                    (case_id,proposal_id,revision,handoff_json,lifecycle,parent_proposal_id)
                    VALUES(?,?,?,?, 'pending', ?)""",
                    (
                        case_id,
                        next_pending,
                        expected_revision,
                        _model_json(replacement),
                        proposal_id,
                    ),
                )
                status = "awaiting_review"

            self._save(
                db,
                state.model_copy(update={"pending_proposal_id": next_pending}),
                status,
                reply_json,
            )
            receipt = {
                "case_id": case_id,
                "review_id": review_id,
                "proposal_id": proposal_id,
                "revision": expected_revision,
                "reviewer_id": reviewer_id,
                "decision": decision,
                "status": status,
                "action_id": action_id,
                "new_proposal_id": next_pending,
                "replayed": False,
            }
            db.execute(
                "INSERT INTO reviews(case_id,review_id,request_sha256,receipt_json) VALUES(?,?,?,?)",
                (case_id, review_id, request_hash, _json(receipt)),
            )
            self._audit(
                db,
                case_id,
                "review_committed",
                {
                    "review_id": review_id,
                    "proposal_id": proposal_id,
                    "decision": decision,
                    "action_id": action_id,
                    "revision": expected_revision,
                },
            )
            db.commit()
            return receipt

    def comments(self, case_id: str) -> list[dict[str, Any]]:
        CaseState(case_id=case_id)
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """SELECT proposal_id,action_id,reviewer_id,body
                    FROM local_comments WHERE case_id=? ORDER BY rowid""",
                    (case_id,),
                )
            ]

    def audit_trace(self, case_id: str) -> list[dict[str, Any]]:
        CaseState(case_id=case_id)
        with self._connect() as connection:
            return [
                {
                    "sequence": row["sequence"],
                    "event": row["event_type"],
                    "details": json.loads(row["details_json"]),
                }
                for row in connection.execute(
                    "SELECT sequence,event_type,details_json FROM audit WHERE case_id=? ORDER BY sequence",
                    (case_id,),
                )
            ]

    def reset_all(self, *, confirmation: str) -> None:
        """Development-only destructive reset; never implicit on constructor/restart."""
        if confirmation != "RESET LOCAL TRACKER":
            raise TrackerRejected("ResetConfirmationRequired")
        with self._connect() as db:
            self._begin(db)
            for table in (
                "audit",
                "conversation",
                "local_comments",
                "reviews",
                "proposals",
                "events",
                "cases",
            ):
                db.execute(f"DELETE FROM {table}")
            db.commit()
