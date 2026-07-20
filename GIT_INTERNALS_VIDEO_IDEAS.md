# Git Internals — Two-Video Plan (Merge vs. Rebase)

Both videos go deep on the same underlying machinery (the object graph, SHA
hashing), which is what makes them feel similar. The fix isn't a different
topic — it's making each video own exactly one new mechanical idea and
refusing to re-teach the other's.

## Differentiation

| | Video 1 — Merge | Video 2 — Rebase |
|---|---|---|
| **Owns** | Content-addressable storage: how a SHA is computed from content, and how a three-way merge auto-resolves per file | History chaining: how a commit's SHA bakes in its parent's SHA, so rewriting history cascades new hashes down the branch |
| **The one "aha"** | "Git doesn't store diffs — it stores whole snapshots, named by the hash of their content." | "A commit's identity *is* its whole history behind it. Change one commit, and every commit after it gets a new identity — even if the code is byte-for-byte the same." |
| **Reuses from the other video** | Nothing — this is the primer | One line only: "remember, a SHA is a hash of content" — don't re-derive it |
| **Carries through one concrete example** | One file, two branches, a line changed on each side → walk `merge-base`, per-file diff, conflict markers | Same two branches → walk the replay: old parent → new parent → new SHA, then the reflog as the safety net |

Because video 2 explicitly builds on video 1's vocabulary instead of
repeating it, watching them back to back should feel like part 1/part 2, not
two versions of the same script.

---

## Video 1 — "What actually happens when you merge two branches"

**Core thread:** git is a content-addressable filesystem first, a version
control tool second. A blob is hashed from raw file content, a tree is
hashed from a sorted list of (name, mode, hash) entries, a commit is hashed
from a tree + parent(s) + metadata. A merge is git finding the nearest
common ancestor (`merge-base`) by walking parent pointers, then diffing each
side's tree against that ancestor **per file** — if only one side touched a
file, that file's blob is taken wholesale (no line-diffing at all); only
files touched on *both* sides get a real three-way line diff, and only
overlapping hunks become conflicts.

**Good "not obvious" beats to hit:**
- Most files in a merge are never actually diffed — they're just picked by whichever side changed them.
- A fast-forward "merge" does zero diffing — it's just moving a pointer.
- Conflict markers (`<<<<<<<` / `=======` / `>>>>>>>`) are literal text git inserts at the hunk boundary, not some special file state.

**Sources:**
- [Pro Git — Git Internals: Git Objects](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects) — official, free. SHA-1 hashing of blob/tree/commit, exact object format.
- [Pro Git — Plumbing and Porcelain](https://git-scm.com/book/en/v2/Git-Internals-Plumbing-and-Porcelain) — the low-level commands (`git hash-object`, `git cat-file`) if you want to show it live.
- [git-scm.com/docs/merge-strategies](https://git-scm.com/docs/merge-strategies) — official docs on the `ort` strategy (default since Git 2.33) and three-way merge behavior.
- [git-scm.com/docs/git-merge](https://git-scm.com/docs/git-merge) — merge-base, fast-forward vs. true merge.
- [Julia Evans — "Inside .git"](https://jvns.ca/blog/2024/01/26/inside-git/) — walks the actual object files on disk, very concrete, good for a screen-recorded demo.
- [James Coglan — "The Myers diff algorithm," part 1](https://blog.jcoglan.com/2017/02/12/the-myers-diff-algorithm-part-1/) (3-part series) — only if you want the actual line-matching algorithm git uses, not just "it diffs."

---

## Video 2 — "What actually happens when you rebase"

**Core thread:** rebase doesn't move commits, it copies them. For each
commit on your branch, git computes the patch relative to its *old* parent,
then re-applies that patch on top of the new base — producing a brand-new
commit object with a new parent pointer. Since a commit's SHA is a hash that
includes its parent's SHA, that one new parent cascades a new SHA through
every commit after it, even though the file content is identical. This is
also exactly why rebasing a pushed/shared branch breaks collaborators: their
ref still points at the old SHA chain, which now shares no history with
yours. The old commits aren't gone — they sit unreferenced until garbage
collected, which is what the reflog is actually pointing at.

**Good "not obvious" beats to hit:**
- Same diff, different hash — rebase doesn't preserve commit identity, only content.
- "Interactive rebase" and "merge conflict during rebase" are the same replay mechanism, just paused mid-patch.
- Reflog isn't magic undo — it's just git not having garbage-collected the orphaned commits yet (~90 days default).

**Sources:**
- [Pro Git — Rebasing](https://git-scm.com/book/en/v2/Git-Branching-Rebasing) — official walkthrough of the replay mechanism, step by step.
- [git-scm.com/docs/git-rebase](https://git-scm.com/docs/git-rebase) — official docs, explicit that rebase creates new commits with new SHAs.
- [Julia Evans — "git branches: intuition & reality"](https://jvns.ca/blog/2023/11/23/branches-intuition-reality/) — explains commits as copied/replayed, a clean mental model to script from.
- [Julia Evans — "git rebase: what can go wrong?"](https://jvns.ca/blog/2023/11/06/rebasing-what-can-go-wrong-/) — real failure modes, useful if you want a concrete incident as the hook instead of a pure explainer.
- [Pro Git — Git Internals: Maintenance and Data Recovery](https://git-scm.com/book/en/v2/Git-Internals-Maintenance-and-Data-Recovery) — reflog as the actual safety net, not a marketing point.

---

## Keeping it "super deep" in a short runtime

- **Carry one concrete example through the whole video** — don't explain the general case, narrate one specific object graph (two branches, one file, a couple commits) start to finish. Depth comes from precision on one example, not from covering more ground.
- **Name real internals** (SHA-1, blob/tree/commit, `merge-base`, reflog) so it reads as genuinely deep — but only define a term if it's load-bearing for that video's one "aha." Anything not needed for the payoff gets cut, even if it's true and interesting.
- **Show the actual objects if screen-recording** — `git cat-file -p <sha>`, `git log --graph --oneline`, or even just `ls .git/objects` makes the claim verifiable on screen instead of a whiteboard assertion.
- **Video 2 should spend zero time re-explaining what a SHA is** — one clause ("remember, a commit's hash is just a hash of its content...") and straight into "...and its parent." That's the entire budget for recap.
