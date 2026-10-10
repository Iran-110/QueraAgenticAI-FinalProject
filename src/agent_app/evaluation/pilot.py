"""P1 entry point kept for the recorded command; the general runner does the work.

``python -m agent_app.evaluation.pilot FIXTURE`` equals an offline
``agent_app.evaluation.runner`` run. The historical P1 receipt
(``receipts/pilot-12782-v1.json``) used the earlier single-case format.
"""

from agent_app.evaluation.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
