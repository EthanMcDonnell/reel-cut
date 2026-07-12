#!/usr/bin/env python3
"""Deterministic QC linter for ReelCut scripts.

Catches mechanical defects that self-review keeps shipping (em dashes, banned
throat-clearing openers, missing apostrophes, format and blank-line violations)
so they never reach a saved script. Mechanical rules are checked mechanically;
subjective judgement stays with the stop-slop review.

Usage:
    .venv/bin/python .claude/skills/scripts/scripts/lint_script.py <script.md>
    cat script.md | .venv/bin/python .claude/skills/scripts/scripts/lint_script.py -

Exit 0 = no blocking errors (warnings are advisory). Exit 1 = blocking error(s).
"""
import argparse
import re
import sys

REQUIRED_HEADERS = ["**HOOK**", "**SCRIPT**", "**CONCLUSION**", "**REFERENCES:**"]
# Optional headers, allowed but not required. **CTA**, when present, holds the
# spoken comment-bait line and sits between CONCLUSION and REFERENCES.
OPTIONAL_HEADERS = ["**CTA**"]
ALL_HEADERS = REQUIRED_HEADERS + OPTIONAL_HEADERS
# Sections whose content is excluded from the body word-count cap: every hook
# variant (split into separate videos) and the appended CTA tag.
NON_BODY_SECTIONS = {"**HOOK**", "**CTA**"}

# Throat-clearing openers (banned). Deliberately narrow so it never catches the
# skill-endorsed open-loop phrase "But here's the part nobody talks about".
THROAT_CLEARING = [
    "here's the thing", "here's the problem", "here's what", "here's why",
    "here's how", "here's this", "here's that", "here's the interesting",
    "heres the thing", "heres the problem", "heres what", "heres why",
    "heres how", "heres this", "heres that", "heres the interesting",
]

META_BANNED = [
    "let that sink in", "plot twist", "let me walk you through",
    "here's what i mean", "heres what i mean",
]

# Unambiguous missing-apostrophe contractions. Every entry is a non-word in
# English, so flagging it as an error never collides with valid prose
# (its, wont, cant, lets, im, hes, shes are deliberately excluded).
APOSTROPHE = [
    "dont", "doesnt", "didnt", "isnt", "wasnt", "arent", "werent", "havent",
    "hasnt", "hadnt", "wouldnt", "couldnt", "shouldnt", "mustnt", "theyre",
    "youre", "weve", "youve", "theyve", "ive", "heres", "thats", "whats",
    "wheres", "theres", "whos", "youll", "theyll", "youd", "theyd",
]

# Softer banned phrases — surfaced, but not blocking.
WARN_PHRASES = [
    "it turns out", "the truth is", "the reality is", "make no mistake",
    "let me be clear", "the lesson here", "the lesson is", "the takeaway",
    "deep dive", "game changer", "game-changer", "circle back",
    "at the end of the day", "needless to say",
]


def lint(lines):
    errors, warns = [], []
    stripped = [l.strip() for l in lines]
    joined = "\n".join(lines)

    # Required headers: present, and on their own clean line.
    for h in REQUIRED_HEADERS:
        if h in stripped:
            continue
        if h in joined:
            ln = next((i + 1 for i, l in enumerate(lines) if h in l), 0)
            errors.append((ln, "header-corrupt", f"`{h}` is not on its own line (stray characters around it?)"))
        else:
            errors.append((0, "header-missing", f"required header `{h}` not found"))

    in_refs = False
    for i, line in enumerate(lines, 1):
        s = line.strip()
        low = line.lower()

        if s == "":
            errors.append((i, "blank-line", "empty line (saved scripts must have no blank lines)"))
            continue
        if s == "**REFERENCES:**":
            in_refs = True
            continue
        if in_refs:
            continue  # reference URLs: skip prose checks

        if "—" in line:
            errors.append((i, "em-dash", "em dash — use a comma or period"))
        if " – " in line:
            errors.append((i, "en-dash", "spaced en dash used as punctuation; use a comma or period"))
        if "--" in line:
            warns.append((i, "double-hyphen", "`--` reads as an em dash; use a comma or period"))

        for p in THROAT_CLEARING:
            if p in low:
                errors.append((i, "throat-clearing", f'banned opener "{p}"'))
        for p in META_BANNED:
            if p in low:
                errors.append((i, "meta", f'banned phrase "{p}"'))
        if re.search(r"\betc\b", low):
            errors.append((i, "etc", '"etc" leftover; write the full thought or cut it'))
        for w in APOSTROPHE:
            if re.search(rf"\b{w}\b", low):
                errors.append((i, "apostrophe", f'"{w}" is missing an apostrophe'))

        for p in WARN_PHRASES:
            if p in low:
                warns.append((i, "weak-phrase", f'weak/banned phrase "{p}"'))
        if re.match(r"\s*(so|look)[ ,]", low):
            opener = "So" if low.lstrip().startswith("so") else "Look"
            warns.append((i, "opener", f'line opens with "{opener}"; start with the content'))

    # Optional **CTA**, if present, must sit between CONCLUSION and REFERENCES.
    if "**CTA**" in stripped:
        pos = {h: stripped.index(h) for h in ("**CONCLUSION**", "**CTA**", "**REFERENCES:**") if h in stripped}
        cta = pos["**CTA**"]
        if "**CONCLUSION**" in pos and cta < pos["**CONCLUSION**"]:
            errors.append((cta + 1, "cta-order", "**CTA** must come after **CONCLUSION**"))
        if "**REFERENCES:**" in pos and cta > pos["**REFERENCES:**"]:
            errors.append((cta + 1, "cta-order", "**CTA** must come before **REFERENCES:**"))

    # Body word count for the cap. The HOOK block holds every hook variant
    # (recorded once, then split into separate videos) and the CTA is an appended
    # tag, so both are excluded from the cap — only SCRIPT + CONCLUSION, the
    # shared body, counts. Also excludes headers and reference URLs.
    words, n_hooks = 0, 0
    section, in_refs = None, False
    for s in stripped:
        if s == "**REFERENCES:**":
            in_refs = True
            continue
        if in_refs:
            continue
        if s in ALL_HEADERS:
            section = s
            continue
        if not s:
            continue
        if section in NON_BODY_SECTIONS:
            if section == "**HOOK**":
                n_hooks += 1
            continue
        words += len(s.split())
    if words > 230:
        note = f"body only, {n_hooks} hooks excluded" if n_hooks else "body only"
        warns.append((0, "word-count", f"{words} words of content ({note}; hard cap 230)"))

    return errors, warns


def main():
    ap = argparse.ArgumentParser(description="Deterministic QC linter for ReelCut scripts.")
    ap.add_argument("path", help="path to the script .md file, or - for stdin")
    args = ap.parse_args()

    try:
        content = sys.stdin.read() if args.path == "-" else open(args.path, encoding="utf-8").read()
    except FileNotFoundError:
        print(f"lint_script: file not found: {args.path}", file=sys.stderr)
        sys.exit(2)

    lines = content.split("\n")
    if lines and lines[-1] == "":  # drop the trailing empty from a final newline
        lines = lines[:-1]

    errors, warns = lint(lines)

    def show(items):
        for ln, code, msg in sorted(items):
            loc = f"L{ln}" if ln else "  —"
            print(f"  {loc:>5}  [{code}] {msg}")

    if errors:
        print(f"✗ {len(errors)} blocking error(s):")
        show(errors)
    if warns:
        print(f"⚠ {len(warns)} warning(s):")
        show(warns)
    if not errors and not warns:
        print("✓ clean — no issues")
    elif not errors:
        print("✓ no blocking errors (warnings above are advisory)")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
