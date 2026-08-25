# Future Features — Ideas

Not committed, not scoped, no code yet. Captured so they don't get lost.

## More variation per script

### 1. Skippable lines
**Idea:** Let `produce-script` mark certain body sentences as optional (e.g. `[SKIP]` prefix
or a similar inline marker) — detail or color that strengthens the video but isn't load-bearing
for the spine. `produce-video` could then render a second, shorter cut per hook by dropping the
marked lines, without a second trip through script writing.
**Why:** More output variants (short cut vs. full cut) from one script-writing pass, instead of
one variant per hook only.
**Open questions:**
- `/prepare-video` reads `script.md` as the transcript ground truth — a skippable line means the
  actual take may or may not contain it, so the ground-truth check needs to accept either version
  rather than flagging a real gap as an error.
- Does the linter's word cap apply to the skip-included or skip-excluded count, or both?

### 2. Raise the word-count ceiling
**Idea:** Increase the per-series target length enough that a script can carry skippable lines
(#1) without the full version blowing the cap — i.e. the cap is sized for "everything included,"
and dropping skip-marked lines is what gets a leaner cut, not a rewrite.
**Why:** Makes #1 workable without loosening the linter's quality bar for scripts that don't use
skippable lines at all.
**Open questions:** Per-series or global increase; how much headroom skippable lines actually need
in practice before this is worth doing.

### 3. Branching endings (tree structure)
**Idea:** One script, one shared setup/body, multiple alternate `**CONCLUSION**` / `**CTA**`
branches — same idea as the existing multi-hook shortlist (Stage 1 of `produce-script`), but
applied to the *end* of the video instead of the start. Each branch would render as its own video:
shared hook+body, different landing.
**Why:** Tests different payoffs/CTAs against the same setup, the mirror of what multi-hook
testing already does at the front.
**Open questions:**
- Needs its own approval step (like Stage 2's hook approval) so branches don't multiply
  unreviewed.
- Interacts with CTA/resource selection (Stage 3.6) — does each branch get its own CTA, or do all
  branches share one?
- `produce-video` currently renders one video per hook; this would need it to also fan out per
  ending, i.e. hooks × endings combinations, which changes the output-per-slug count materially.

## On-screen overlays

### 4. Circular countdown ring
**Idea:** A small circular progress-ring overlay (thin outline) that starts as a full circle and
depletes over the course of the video, reaching empty at the end.
**Why:** Visible countdown as a retention cue — signals there's a defined end and something to
stick around for.
**Open questions:**
- Track the whole video or just the hook window — hooks vary in length per variant, so the ring's
  pace would need to be computed per rendered video, not fixed.
- Screen position that doesn't collide with captions or other overlays (screenshots, figures).

### 5. "Press here for 2x speed" tap zone
**Idea:** A small graphic on the right side of the frame styled like a tappable "2x speed"
control.
**Why:** Mimics a real player affordance for curiosity/engagement.
**Open questions:**
- The output is a static rendered MP4 — this can only ever be a decorative graphic, not a
  functioning control, since there's nothing on the platform side to wire it to. Worth deciding
  up front whether a non-functional button reads as a harmless novelty or as misleading a viewer
  who actually taps it expecting playback to change.
- Screen position and timing (always on vs. appears partway through).
