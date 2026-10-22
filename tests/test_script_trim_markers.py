"""A [cut-N] marker has to stay on its own sentence through the reflow, and the linter has
to enforce the limit on how much of the body can be cut."""
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent / ".claude/skills/scripts/scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reflow_keeps_a_marker_on_its_own_sentence():
    out = _load("format_script").format_script(
        "**SCRIPT**\nThe point lands. [cut-1] A side detail. The next point.\n**CONCLUSION**\n")
    assert out.splitlines()[1:4] == ["The point lands.", "[cut-1] A side detail.", "The next point."]


def test_marking_over_a_quarter_of_the_body_blocks():
    lint = _load("lint_script").lint
    body = ["**VIDEO TYPE**", "misc", "**HOOK**", "Hook.", "**SCRIPT**",
            "One two three four five six seven eight.",
            "[cut-1] One two three four five six seven eight.",
            "**CONCLUSION**", "One two three four five six seven eight.", "**REFERENCES:**"]
    errors, _ = lint(body)
    assert [code for _, code, _ in errors] == ["trim-share"]
