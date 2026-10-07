"""Streamlit support assistant package."""


def main(argv: list[str] | None = None) -> int:
    """Load the CLI only when invoked; importing contracts has no demo side effects."""
    from agent_app.cli import main as run

    return run(argv)
