from __future__ import annotations

from pathlib import Path

import pytest


def _make_repl():
    # Ensure we can import from src/ without installing the package.
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "src"))

    from repl.python_tool_repl import build_python_repl_tool
    from simplest_tool_logging import ToolUsageTracker

    tracker = ToolUsageTracker(debug=False)
    tool = build_python_repl_tool(tracker=tracker, sub_tools=[], track_sub_tools=False)
    assert hasattr(tool, "func")
    return tool.func


def test_allowed_import_statement_works():
    repl = _make_repl()
    out = repl(
        """
import re
print(re.__name__)
""".strip()
    )
    assert out.strip() == "re"


def test_allowed_from_import_works():
    repl = _make_repl()
    out = repl(
        """
from collections import Counter
print(Counter([1, 1, 2]) == Counter({1: 2, 2: 1}))
""".strip()
    )
    assert out.strip() == "True"


@pytest.mark.parametrize(
    "code",
    [
        "import os",
        "from os import path",
        "import os.path",
        "__import__('os')",
        "__import__('os.path', fromlist=('path',))",
    ],
)
def test_disallowed_imports_are_blocked_and_return_traceback(code: str):
    repl = _make_repl()
    out = repl(code)
    # Tool output should contain the traceback and the ImportError message
    assert "Traceback (most recent call last):" in out
    assert "ImportError" in out
    assert "not allowed" in out


def test_eval_syntaxerror_falls_back_to_exec_and_imports_work():
    repl = _make_repl()
    # This is a statement, so eval() path raises SyntaxError and we fall back to exec().
    out = repl(
        """
from collections import Counter
print(Counter([1,2,2]))
""".strip()
    )
    # Output format from Counter is stable enough for a basic assertion.
    assert "Counter" in out
