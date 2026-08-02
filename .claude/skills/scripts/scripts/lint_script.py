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

# Category tags and hype that belong nowhere in a resource label.
RESOURCE_BANNED_LABELS = [
    "lead magnet", "go deeper", "go-deeper", "hands-on", "hands on", "the real source",
    "steal this", "steal-this", "build-it", "adjacent tool", "canonical",
    "deep dive", "deep-dive", "the exact", "the actual", "definitive",
    "ultimate", "everything you need",
]

# CTA openers that sell instead of tell. The line has to sound like the creator
# mentioning the resource, not an ad asking what the viewer wants.
CTA_BANNED_OPENERS = [
    "want ", "wanna ", "want to ", "do you want", "if you want",
    "ever wondered", "curious ", "need ",
]

# Softer banned phrases — surfaced, but not blocking.
WARN_PHRASES = [
    "it turns out", "the truth is", "the reality is", "make no mistake",
    "let me be clear", "the lesson here", "the lesson is", "the takeaway",
    "deep dive", "game changer", "game-changer", "circle back",
    "at the end of the day", "needless to say",
]

# Percentages, multiples, and fractions — each is a comparison, so each needs
# the other side of it stated nearby.
RELATIVE_STAT = re.compile(
    r"\d+(?:\.\d+)?\s?(?:%|percent)"
    r"|\b\d+(?:\.\d+)?\s?x\b"
    r"|\b(?:\d+|two|three|four|five|six|seven|eight|nine|ten)\s+times\s+"
    r"(?:\w+er|faster|slower|smaller|bigger|larger|cheaper|more|less)"
    r"|\bfactor of\s+(?:\d+|two|three|four|five|six|seven|eight|nine|ten)\b"
    # "in half" only in its outcome sense; bare double/triple describe scaling
    # relationships ("double the input, quadruple the work"), which are self-contained.
    r"|\b(?:cut|drop(?:ped)?|shrank|shrunk|fell)\s+(?:\w+\s+){0,3}in half\b"
    r"|\bhalved\b",
    re.I,
)

# Phrasing that establishes what the stat is measured against.
BASELINE_MARKER = re.compile(
    r"\bcompared to\b|\bcompared with\b|\bversus\b|\bvs\.?\b"
    r"|\bbefore\b|\bpreviously\b|\bused to\b|\bhad been\b|\bwas\b|\bwere\b"
    r"|\bdown from\b|\bup from\b|\bfrom \d|\binstead of\b|\bthan\b"
    r"|\bold\b|\bformerly\b|\bonce\b",
    re.I,
)


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

    # Viewer resources block: short list, short labels. Labels are names, not
    # pitches, so a long one is always a run-on justification or a category tag.
    if "**VIEWER RESOURCES:**" in stripped:
        start = stripped.index("**VIEWER RESOURCES:**")
        urls, in_ref_links = 0, False
        for i, s in enumerate(stripped[start + 1:], start + 2):
            if s.startswith("http"):
                if not in_ref_links:  # source article links are uncapped
                    urls += 1
                continue
            label = s.rstrip(":")
            low_label = label.lower()
            if "reference article" in low_label:  # the source article label, fixed
                in_ref_links = True
                continue
            if "—" in label:
                errors.append((i, "resource-label", "em dash in resource label; use a comma or cut it"))
            for tag in RESOURCE_BANNED_LABELS:
                if tag in low_label:
                    errors.append((i, "resource-label", f'label says "{tag}"; name the resource instead'))
            if len(label.split()) > 6:
                errors.append((i, "resource-label", f"label is {len(label.split())} words; 6 or fewer, no explanation"))
        if urls > 2:
            errors.append((start + 1, "resource-count", f"{urls} resource links; 2 maximum, not counting the source article(s)"))

    # Optional **CTA**, if present, must sit between CONCLUSION and REFERENCES.
    if "**CTA**" in stripped:
        pos = {h: stripped.index(h) for h in ("**CONCLUSION**", "**CTA**", "**REFERENCES:**") if h in stripped}
        cta = pos["**CTA**"]
        if "**CONCLUSION**" in pos and cta < pos["**CONCLUSION**"]:
            errors.append((cta + 1, "cta-order", "**CTA** must come after **CONCLUSION**"))
        if "**REFERENCES:**" in pos and cta > pos["**REFERENCES:**"]:
            errors.append((cta + 1, "cta-order", "**CTA** must come before **REFERENCES:**"))
        # The CTA states the resource as a fact, then asks for the comment. A
        # question about what the viewer wants reads as an ad on the last line.
        for i in range(cta + 1, len(stripped)):
            if stripped[i] in ALL_HEADERS:
                break
            first = stripped[i].lower().lstrip("\"'")
            for opener in CTA_BANNED_OPENERS:
                if first.startswith(opener):
                    errors.append((i + 1, "cta-opener", f'CTA opens with "{opener}"; state the resource as a fact, then ask for the comment'))

    # Body word count for the cap. The HOOK block holds every hook variant
    # (recorded once, then split into separate videos) and the CTA is an appended
    # tag, so both are excluded from the cap — only SCRIPT + CONCLUSION, the
    # shared body, counts. Also excludes headers and reference URLs.
    words, n_hooks = 0, 0
    body = []
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
        body.append(s)
    if words > 190:
        note = f"body only, {n_hooks} hooks excluded" if n_hooks else "body only"
        warns.append((0, "word-count", f"{words} words of content ({note}; hard cap 190)"))

    # Per-sentence length. A spoken sentence past ~25 words has chained one
    # clause too many, burying the reveal under its own qualifiers. Across the
    # existing script library only the weakest script trips this, so the
    # threshold flags real run-ons rather than ordinary long sentences.
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(body))
    for sentence in sentences:
        n = len(sentence.split())
        if n > 25:
            warns.append((0, "sentence-length", f"{n}-word sentence; split it: \"{sentence}\""))

    # Relative stats without a baseline. "cut memory by 87.5%" is unusable to a
    # viewer who was never told what the old number was, and the baseline is
    # nearly always sitting right there in the source.
    for i, sentence in enumerate(sentences):
        if not RELATIVE_STAT.search(sentence):
            continue
        window = " ".join(sentences[max(0, i - 1):i + 2])
        if not BASELINE_MARKER.search(window):
            warns.append((0, "stat-baseline",
                          f'relative stat with no stated baseline — compared to what? "{sentence}"'))

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
