"""Reviewed offline binding of the existing SQLite tracker to the real HTTP routes.

The fixed credential is synthetic test configuration, never a production secret.
It stays inside the trusted binding and is excluded from receipts and worker JSON.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from agent_app import api
from agent_app.testing.http_pilot_runtime import HTTPRuntime
from agent_app.tracker.sqlite_tracker import SQLiteCaseTracker

_TEST_TOKEN = "offline-http-pilot-synthetic-reviewer-token"


@contextmanager
def sqlite_factory(state_dir: Path) -> Iterator[HTTPRuntime]:
    from agent_app.persistent_api import create_app

    state_dir.mkdir(parents=True, exist_ok=True)
    tokens = {"fixture-maintainer": _TEST_TOKEN}
    tracker = SQLiteCaseTracker(state_dir / "http-pilot.sqlite", reviewer_tokens=tokens)
    application = create_app(
        tracker=tracker, reviewer_tokens=tokens, adapters=lambda scenario: api._adapters(scenario)
    )
    with patch.object(api, "app", application):
        yield HTTPRuntime(
            application,
            "sqlite_case_tracker",
            durable_review=True,
            review_headers={"Authorization": f"Bearer {_TEST_TOKEN}"},
            local_actions_supplier=tracker.comments,
        )
