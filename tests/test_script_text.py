"""Tests for reelcut.script_text.extract_spoken_text."""
from reelcut.script_text import extract_spoken_text


def test_extracts_hooks_and_body_drops_markers_and_references():
    md = (
        "**HOOK**\n"
        "What is the Billion Laughs attack and why was it so dangerous?\n"
        "A 2002 attack was still hiding inside LangChain in 2024.\n"
        "**SCRIPT**\n"
        "You define a word once, so &lol; means the word lol.\n"
        "**CONCLUSION**\n"
        "The fix is almost boring.\n"
        "**REFERENCES:**\n"
        "https://example.com/page\n"
    )
    out = extract_spoken_text(md)
    # Spoken lines are kept, joined into one line.
    assert "Billion Laughs attack" in out
    assert "means the word lol" in out
    assert "The fix is almost boring." in out
    # Structural markers and the references section are gone.
    assert "**" not in out
    assert "HOOK" not in out and "SCRIPT" not in out and "CONCLUSION" not in out
    assert "example.com" not in out and "REFERENCES" not in out
    assert "\n" not in out


def test_strips_numbered_hook_labels_keeps_text():
    md = (
        "**HOOK**\n"
        "HOOK 1: First framing of the idea.\n"
        "HOOK 2: Second framing of the idea.\n"
        "**SCRIPT**\n"
        "Body sentence.\n"
    )
    out = extract_spoken_text(md)
    assert out == "First framing of the idea. Second framing of the idea. Body sentence."


def test_skips_yaml_frontmatter():
    md = (
        "---\n"
        "title: Something\n"
        "status: done\n"
        "---\n"
        "**SCRIPT**\n"
        "Only this is spoken.\n"
    )
    out = extract_spoken_text(md)
    assert out == "Only this is spoken."


def test_everything_after_references_is_dropped():
    md = (
        "**SCRIPT**\n"
        "Spoken body.\n"
        "**REFERENCES:**\n"
        "link\n"
        "**RESOURCES**\n"
        "Comment a keyword and I will send the guide.\n"
    )
    out = extract_spoken_text(md)
    assert out == "Spoken body."
