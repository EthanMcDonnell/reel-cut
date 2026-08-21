# ReelCut — PENDING TODO

**Status:** Gap 1 **FIXED** 2026-08-03. Gap 4 **FIXED** 2026-08-15. Gap 5 **FIXED** 2026-08-16.
Gap 2 **ADDRESSED** 2026-08-22 (see below). Gap 3 still proposed, not started. Gap 4 opened and closed 2026-08-15 off
`ht-ghd-better-gitcli`; Gap 5 opened and closed 2026-08-16 off `vlc-defender-plugin-cache`.
Opened 2026-08-02 off the `canva-session-revocations-s3` prepare run; Gap 3 added 2026-08-03 off
`figma-pgkeeper-connection-pooler`. Every gap here was found the same way — by comparing the cut
transcript against the source script, which until 2026-08-22 lived outside the repo and the
pipeline never read. Scripts now live at `assets/<slug>/script.md`.

---

## Settled: the last take IS always the right take

Confirmed by the person doing the recording. When a take is re-recorded, the later one is the one
wanted — every time. **Do not build anything that prefers an earlier take, ranks takes by
completeness, or asks which take to keep.** That is not the bug, and "fixing" it would break the
one rule the detector currently gets right.

The bug is that a retake cut can reach *backwards past its own take* and swallow a neighbouring
sentence that was never retaken at all.

---

## Gap 1 — backward snap absorbs un-retaken content ✅ FIXED 2026-08-03

### What happened

Script (`assets/canva-session-revocations-s3/script.md`):

> They moved the list into S3, chopped into timestamped chunks. **A booting gateway grabs only the
> last 12 hours.** Older ones don't matter, since every cookie refreshes by then…

Three takes of the "older ones don't matter" beat were recorded:

| take | span | words |
|---|---|---|
| A | 73.261 → 78.140 | "A booting gateway grabs only the last 12 hours, older ones don't matter." |
| B | 82.786 → 86.660 | "Older ones don't matter. Since every cookie refreshes by then." |
| C | 90.971 → 98.180 | "Older ones don't matter, since every cookie usually refreshes by then, and refreshes get checked against the database." |

C was kept — correct. But the cut reached back to **73.261**, taking the whole of A including
"A booting gateway grabs only the last 12 hours", a scripted sentence that appears in **no other
take**. Rendered result:

> "…chopped into timestamp chunks. ⟨cut⟩ Older ones don't matter…"

"Older ones" now has no referent. The 12-hour window is the entire point of the chunking.

### Mechanism

`reelcut/retake_detector.py` → `_snap_to_take_boundaries()`, START branch (~L340-360).

The matcher anchored the cut at "older" (76.895). `boundary[ci]` was False — the preceding word
is `'hours,'`, and:

- `_is_sentence_end('hours,')` → False (comma; the test at L396 only accepts `.` `?` `!`)
- gap `76.895 - 76.313 = 0.582s` < `take_boundary_s = 2.0`

so the snap walked backwards to the previous real boundary, which was `'chunks.'` — crossing the
entire "A booting gateway…" clause. The one guard that could have stopped it:

```python
preamble_words = ci - k        # L355
keeper_words   = ke - cj
if (boundary[k] and t_start - words[k].start <= max_reach_s
        and preamble_words <= keeper_words):     # L358
    t_start = words[k].start
```

preamble = 9 words, keeper = ~19 words → `9 <= 19` passes → snap fires.

That guard is aimed at mid-sentence restarts, where the preamble is the *sentence's unique body*
and is **longer** than the keeper. Here the preamble was unique content that happened to be
**shorter** than the keeper, so length told us nothing. This is not a threshold that wants
tuning — length is the wrong signal.

### Rejected approach — content overlap (do not retry)

The first proposal was to bail when the preamble's content words are absent from the keeper.
**It does not work**, and the reason is worth keeping: it breaks the billion-laughs case that the
snap exists for. There, take A's head "with no particular" must be absorbed, but its content words
`{particular}` intersect the keeper `{virus, stolen, password, instead, lines, completely, valid,
xml}` at **∅** — identical to the canva signature. Content overlap cannot tell a divergent
restatement from unique content, because a divergent restatement is *by definition* worded
differently.

### Actual fix (`reelcut/retake_detector.py`, START branch of `_snap_to_take_boundaries`)

The discriminator is **structural, not lexical**: does the keeper have a head of its own for the
preamble to be a divergent restatement OF?

- billion-laughs — keeper take C opens `"see there was no …"` *before* the shared core `"virus"`.
  It has a head. Take A's `"with no particular"` is that head's counterpart → absorb it.
- canva — keeper take C opens exactly on the matched core, `"Older ones don't matter"`. It has
  **no** head. So `"A booting gateway grabs only the last 12 hours,"` corresponds to nothing in the
  keeper — it was never re-said → leave it kept.

Implemented by walking back from the keeper's first word to its own take boundary and requiring
that distance to be non-zero:

```python
kb = min(cj, n - 1)
while kb > 0 and not boundary[kb]:
    kb -= 1
keeper_head = cj - kb if cj < n else 0   # keeper's own unmatched head
if (boundary[k] and t_start - words[k].start <= max_reach_s
        and preamble_words <= keeper_words and keeper_head > 0):
    t_start = words[k].start
```

The existing length guard is kept — the two catch different shapes.

**Known trade-off:** when the keeper opens on the core, a genuinely disfluent head ("um so
basically…") now survives the snap instead of being absorbed. That is deliberate: leaving filler is
cosmetic and the gap detector cleans most of it anyway, whereas deleting scripted content is a
content bug. Do not "improve" this by re-adding a length or content threshold — see above.

### Verified

1. `tests/test_retake_detector.py::test_real_clip_snap_does_not_absorb_preamble_keeper_never_re_said`
   — real words/timings from the clip; asserts the cut opens at 76.895 not 73.261. Fails on the
   pre-fix detector (obtained 73.261), passes after.
2. Full suite: **205 passed, 3 xfailed**. The two cases the snap was built for still pass —
   `test_three_takes_leading_divergence_snaps_to_take_boundaries` (billion-laughs) and
   `test_mid_sentence_restart_keeps_unique_lead_in`.
3. Swept all 15 clips under `assets/` + `assets/archive/`, diffing retake cuts before vs after.
   **13 byte-identical.** Two moved:
   - `canva-session-revocations-s3` — the intended fix (35.501s → 31.867s cut).
   - `claude-1m-context-window-trap` — **the same bug, second instance** (38.756s → 35.129s). The
     cut opened at 29.520 and ate `"So the work explodes as the text grows"`, confirmed scripted in
     that slug's script. That video is **already published** with
     the line missing.

### Follow-up

`canva-session-revocations-s3`'s `captions.json` was produced by the pre-fix detector, so its `edl`
still carries the bad cut. Re-running `transcribe` regenerates it correctly but wipes the `it.` fix
and the fixlog (per the `/prepare-video` reset rule), so it needs a re-run plus re-applying that one
edit — or a hand-patch of the single span. Not done yet.

---

## Gap 2 — nothing checks the transcript against the script ✅ ADDRESSED 2026-08-22

Two errors in this clip were invisible to the confidence-based digest because Whisper was
**confident and wrong**:

| time | transcribed | script |
|---|---|---|
| 0:24.204 | `unsee` (conf 0.91) | **un-issue** |
| 0:53.924 | `well.` (conf 0.79) | *(nothing — "…from MySQL, stampeding…")* |

"so nothing can **unsee** it" ships as an on-screen caption. `debug.0.review.txt` ranks by
confidence, so it will never surface either one. The exact source text existed, but it was sitting
in an Obsidian vault outside the repo that no command read.

### What shipped

`/produce-script` Stage 3.5 now saves the script to **`assets/<slug>/script.md`** instead of the
vault, and `/prepare-video` Step 3 reads it as ground truth for wording before assessing. The
Obsidian vault is gone from the project — its 115-note idea backlog was exported to
`VIDEO_IDEAS_BACKLOG.md` at the root.

The check is **agent-run, not a script**: Step 3 aligns the surviving transcript against
`script.md` and reports the three buckets below; Step 4's fix table gained a row making a
script-contradicted `words[i].word` a CERTAIN-FIX, casing included — the auto-fix policy amendment
this gap called for. Dropped sentences and inserted tokens stay report-only, because fixing either
means moving a boundary or adding/removing a `words` entry, which Step 4 never does.
`_clean_transcription_artifacts` already ignores `script.md`, so it survives a re-transcribe like
`manifest.json` — no code change was needed.

**Still open:** this only helps slugs produced *after* 2026-08-22. Existing slugs were not
backfilled (deliberate — the shipped ones gain nothing), so the verification below has no
`script.md` to run against and was never executed.

### Original proposal — a deterministic pass (not built)

If the agent-run check proves too loose, the fallback is a reconciliation pass over the script,
modelled on the existing
`scrape/reconcile_manifest.py` (same report-buckets shape, same `--slug` interface):

- Align the surviving transcript against the script body, hook lines, conclusion and CTA.
- Report **wrong words** — aligned position, transcript token differs from script token
  (`unsee`/`un-issue`). Candidate for auto-fix in `words[]`, since the script is ground truth.
- Report **dropped sentences** — a script sentence with no surviving transcript span. Would have
  caught Gap 1 independently, from the other direction.
- Report **inserted tokens** — transcript words with no script counterpart (`well.`, and the
  stray `it.` already hand-fixed this run).

Ad-libs are normal and must not spam the report ("See," added, "Before"→"Previously", "usually"
added were all fine this run) — so it needs a similarity floor, not exact matching.

### Verify

Run against `canva-session-revocations-s3` and require exactly these three hits: `unsee`,
`well.`, and the dropped "A booting gateway grabs only the last 12 hours." — with the known
ad-libs above **not** reported.

---

## Gap 3 — the Whisper prompt is built from the slug, so proper nouns come back wrong

### What happened

`figma-pgkeeper-connection-pooler`, 2026-08-03. `reelcut/cli.py:439` builds `initial_prompt` by
title-casing the **slug** and appending it to the config base. The whole prompt for that run was:

> `'Hello. Software engineering. AI for 12 months, Figma Pgkeeper Connection Pooler'`

Whisper was therefore never told any of the script's actual proper nouns, and returned:

| time | transcribed | script |
|---|---|---|
| 0:51 | `Chachabit` (conf 0.56) | **ChatGPT** |
| 0:59 | `single` + `-threaded,` (two tokens) | single-threaded |
| 0:58, 1:06 | `pgBouncer`, `pgKeeper` | **PgBouncer**, **PGKeeper** |

All hand-fixed in `words[]` this run. The slug also actively *taught* the wrong casing —
`Pgkeeper` is neither `PGKeeper` nor `pgkeeper`.

### Proposed fix

Seed `initial_prompt` from `assets/<slug>/script.md`, which the pipeline has a deterministic path
to and still doesn't read (same root cause as Gap 2, which put the file there).

**Do not feed it the full script.** Whisper's `initial_prompt` is capped at 224 tokens — half the
448-token decoder context — and a ~200-word script overruns that. Worse, long prose priming
encourages the decoder to *continue the prompt* rather than transcribe, which is a hallucination
risk on quiet passages. So the note must be reduced, not pasted.

**⚠️ Reducing to the HOOK lines alone would not have fixed this run.** The two hooks were:

> Figma's Postgres intentionally kills your request first if you're the one who's waited longest.
> Figma stopped over 20 outages in one quarter by making their Postgres queue deliberately unfair.

Those yield `Figma` and `Postgres` — and **none** of `ChatGPT`, `PgBouncer`, `PGKeeper`, the three
terms that actually broke. The failing nouns live in the script body, because a hook is written to
be plain. Hook-only is the right *size* but the wrong *content*.

Extract a **term list from the whole note instead** — capitalised tokens, intercaps
(`PgBouncer`, `PGKeeper`, `ChatGPT`), and hyphenates (`single-threaded`), deduped, dropping
sentence-initial ordinary words. On this note that is roughly:

> `Figma, Postgres, PostgreSQL, PgBouncer, PGKeeper, ChatGPT, OpenAI, single-threaded`

~15 tokens, comfortably inside the cap, no prose to continue, and it carries the exact casing —
which is the half of the problem the slug was getting wrong regardless of length. This is also how
`initial_prompt` is meant to be used: a vocabulary hint, not a transcript.

Keep the config base prompt in front of it. Drop the slug-derived text or keep it as a fallback for
slugs with no note.

### Verify

1. Re-transcribe `figma-pgkeeper-connection-pooler` with the note-seeded prompt and require
   `ChatGPT`, `PgBouncer`, `PGKeeper` to come back correct and correctly cased, with no hand-fix.
2. Re-run every slug under `assets/` and `assets/archive/` — slugs with no `script.md` must produce
   a byte-identical transcript to today's, proving the fallback path is inert.
3. Assert the assembled prompt stays under the 224-token cap; fail loudly rather than let Whisper
   silently truncate it.

### Note

Overlaps Gap 2, which has now put `script.md` in the slug folder. Gap 3 is the remaining half:
it needs the same file parsed, but in `reelcut/cli.py` at transcribe time rather than by the agent
at review time.

---

## Gap 4 — the cut's right edge trusted an untrusted timestamp ✅ FIXED 2026-08-15

### What happened

`ht-ghd-better-gitcli`, tail of the clip. 1.78 seconds of dead air shipped:

```
1:22.370→1:22.530  WORD   'just...'  conf=1.00
1:22.530→1:24.306  NOISE  1776ms     KEEP [hard_floor (next_conf=0.33 < 0.35)]
1:24.306→1:24.409  WORD   'You'      conf=0.33
```

**The first diagnosis in this file was wrong** and is kept here because the wrong answer is
instructive. It read the defect as "an abandoned clause (`I just...`) survives both detectors" and
proposed a trailing-fragment rule in `gap_detector`. But `I just...` is only **0.32s** of speech —
it is not what makes the ending drag. The 1.78s of silence next to it is.

### Mechanism

`gap_detector._build_gaps`, the `next_conf` branch:

```python
elif next_conf < config.min_word_confidence:
    # The word we're cutting INTO is uncertain — don't cut regardless of prev side.
    should_cut = False
```

The cut's **right** edge is `nxt.start - pad`, taken straight from the word timestamp. When
alignment confidence drops, that timestamp cannot be trusted — and the only response available was
to veto the entire cut, stranding the whole gap.

**The veto's instinct was correct.** Measuring the audio shows `You` really begins at 84.256, and
there is a 150ms *untranscribed vocalisation* at 83.65–83.80 (-23.5dB, spectral flatness 0.20 —
voiced, as loud as real speech) sitting in the middle of the "silence". A naive cut to
`nxt.start - pad` was genuinely unsafe. The veto was not wrong to refuse; it was wrong to have no
option *except* refusing.

**A duration threshold does not fix this** (this was the second wrong answer — do not retry it).
The cut's right edge is `nxt.start - pad` regardless of gap length, so the clipping risk is
identical for a 100ms gap and a 1776ms one. A duration escape hatch would have fixed this clip by
coincidence, not by mechanism.

### Actual fix

The left edge of a cut was **already** measured from audio — `_find_trailing_speech_end` exists
because WhisperX truncates word *ends*. WhisperX mis-times word *starts* the same way, but the
right edge never got the mirror function. So build it:

- `gap_detector._find_speech_onset_backward()` — walks back from `word_start` through contiguous
  speech to the word's true onset, stopping at the first silence of >= 100ms.
- `Gap.speech_onset` carries it; defaults to `Gap.end`, i.e. trusting the timestamp, which is the
  behaviour everywhere alignment is confident.
- `edl.py` cuts to `gap.speech_onset - pad_s` instead of `nxt.start - pad_s`.
- The `next_conf` branch measures and cuts instead of vetoing.

**The safety property that makes this deployable without a confidence gate:** the scan is capped at
`word_start`, so `cut_end <= nxt.start - pad` always. A cut derived from it is a strict subset of
what the raw timestamp would produce — it can shrink a cut, never extend one into a word. No new
config knob; it reuses `silence_threshold_db` and `failure_tolerance_ratio` like every other scan
in the file.

### Verified

1. `tests/test_gap_retake_aware.py::test_measured_onset_pulls_the_cut_back_when_a_word_starts_before_its_timestamp`
   — synthetic scene with a word timestamped 300ms late; asserts the onset is found at 2.7s and the
   cut stops before it.
2. `test_low_conf_word_is_protected_by_a_measured_onset_not_by_a_veto` — replaces the old test that
   asserted the veto. Pins the invariant (the cut never reaches into the word), not the mechanism.
3. Swept all 21 clips, re-running `detect_gaps` against the real audio with words reconstructed
   from `.debug.4.post-vad.txt`: **12 gaps across 8 clips now cut, ~33s of dead air** (gross; a
   large part sits inside retake spans already removed downstream, so the net gain in rendered
   output is ~13s). In **6 of the 12** the measurement pulled the boundary back 10–130ms to protect
   the next word — `for` in `claude-1m-context-window-trap` would have lost 130ms of its onset.

### Review findings (post-implementation audit, same day)

Auditing the shipped fix against all 21 clips turned up three defects in it. Two were code and
are fixed; one was a documentation overclaim.

**1. `_find_speech_onset_backward` was described as finding "the word's true onset". It does not.**
It finds the last contiguous *audible* run before the word, which is the word's onset only when the
word started before its timestamp. It can equally be a breath, or untranscribed speech sitting in
the gap. Auditing every cut against the scan showed **365 cuts** whose right edge overruns it —
and **243 of those have next-word confidence >= 0.80**, where the timestamp is fine and the overrun
is untranscribed audio the pipeline cuts *on purpose*. Docstring corrected.

This also supplies the real reason the measurement is scoped to `next_conf < min_word_confidence`
rather than applied to every gap. The original justification ("blast radius") was engineering
caution. The actual reason is that applying it globally would stop the pipeline removing
untranscribed gap audio — core behaviour, not a bug. Worked example: `claude-fable-5` at 76.1s has
1.4s of continuous speech between `brought`(0.26) and `in.`(0.86) that no word covers.

**2. The new branch hard-picked `min_silence_ms`, bypassing the type-based floors below it.**
Arbitrary — a low-confidence *breath* gap got the 200ms silence floor instead of the 100ms breath
floor. 4 gaps affected. Now applies whichever floor the gap's own type would get, so measuring the
boundary does not silently change the duration rule.

**3. The branch could set `cut=True` on a gap `edl.py` then declines.** When the measured onset
leaves no room past the pad, `edl.py`'s `cut_end > cut_start + 0.010` check skips the cut while the
`Gap` still claimed `cut=True` — the same debug-report-lies-about-a-cut class noted below. 1 new
instance introduced, 3 in-branch instances total, all now reported `cut=False` with
`measured onset leaves nothing to cut`. The ~636 instances *outside* this branch are pre-existing
and deliberately untouched.

Net effect on output: unchanged — still 12 gaps across 8 clips, 33.05s gross, and
`ht-ghd-better-gitcli` 82.530s still cuts 1.54s. The refinements corrected reasoning and reporting,
not results. A fourth defect was caught in the *tests*: the first version of the
`nothing to cut` test passed vacuously (its scene never triggered the condition it asserted on).
Rewritten with the precondition asserted, and verified to fail against the pre-fix detector.

### Also removed

The retake-awareness `next_conf` bump (`_in_retake(words[i+1]) -> next_conf = 1.0`) existed solely
to unblock this veto. With the veto gone it is dead intent. Removing it is inert on rendered
output: only 6 gaps sit in the divergence window (100–200ms), and the 3 that the bump actually
applied to are inside retake spans cut wholesale downstream. The `prev_conf` half is untouched —
it guards the left edge, which is a different problem.

### Known unrelated bug found while diagnosing this

`debug_report.py:531` labels a gap `KEEP [mid_sentence_floor]` when `gap.cut` is true but
`gap.speech_end` is not found among the EDL cut boundaries. `edl.py` can move that boundary via the
`min_keep_ms` floor, so the lookup misses and a cut that **did** happen is reported as kept — e.g.
`ht-ghd-better-gitcli` at 1:24.880, reported KEEP, actually cut as EDL span 31. This misreads as a
detector bug and cost a wrong diagnosis above. Not fixed.

## Gap 5 — the closure bridge only opened *after* it had seen speech ✅ FIXED 2026-08-16

### What happened

`vlc-defender-plugin-cache`. The script says "…an index in one file called **plugins.dat**". The
render played "…one file called plugins" and jumped straight to "Recently VideoLAN…". The caption
still read `file called plugins .dat.` on screen for the whole line, because captions are drawn
from the word list and the word list was fine — only the audio was missing.

WhisperX aligned `.dat` to 44.459→44.639s. The speaker actually said "dot" (44.459–44.639) and then
"dat" (44.729–45.129) — the second syllable falls entirely *past* the aligned word end. The EDL cut
44.659→45.810 and took it.

### Mechanism

`gap_detector._find_trailing_speech_end`. It exists for exactly this: WhisperX truncates word ends,
so the cut's left edge is measured from audio, and it deliberately bridges silences up to
`max_closure_ms = 90 ms` so a stop-closure (/d/, /t/, /k/) can't strand a final syllable.

The bridge was gated on having already seen speech:

```python
else:
    if not saw_speech:
        return word_end   # silent right away — word end was accurate
```

Here the scan *opened* on the closure. On the loudnorm'd wav the first frame after 44.639 measures
0.006 above-threshold — under `failure_tolerance_ratio` 0.02 — so the function returned the raw word
end on frame 0 and never reached the "dat" 90 ms later. `edl.py`'s `min_keep_ms` floor then nudged
`cut_start` to 44.659 (the word is 180 ms < 200 ms), which is where the cut in `captions.json` came
from.

The premise "silent right away → the word end was accurate" is wrong whenever WhisperX truncates a
word **at** the closure rather than after it. That is not a rare shape — it is the same
phonetic event the bridge was written for, arriving one frame earlier.

**Not a threshold problem.** Lowering `silence_threshold_db` or `failure_tolerance_ratio` to make
that one frame register would loosen every silence decision in the file. The defect is the gate, not
the sensitivity.

### Actual fix

Delete the `saw_speech` gate. The `max_closure_ms` budget now runs from the first frame, so leading
silence is spent against the same 90 ms allowance as any other closure. Nothing else changes:

- If the gap is genuinely silent, the run passes 90 ms, the loop breaks, `last_speech_end` is still
  `word_end` — byte-identical to the old early return. Inert for well-aligned words.
- The result is still capped at `min(gap_end, word_end + 800 ms)`, so `cut_start` can never reach
  the next word's timestamp.
- `test_does_not_jump_across_silence_to_grab_later_breath` still holds: 200 ms of silence outlasts
  the budget, so a breath sitting behind a real pause stays inside the cut.

### Verified

1. `tests/test_gap_trailing_speech.py::test_bridges_a_closure_that_starts_at_the_word_end` — a
   closure opening exactly at the aligned word end with a syllable behind it. Fails pre-fix
   (obtained 0.400, the raw word end), passes after.
2. Full suite: **294 passed, 3 xfailed**.
3. Swept all 14 clips under `assets/` + `assets/archive/`, rebuilding gaps and the EDL from the real
   audio with words from `.debug.4.post-vad.txt`. **6 byte-identical, 8 changed, and every change
   shrinks a cut** — no cut is created, moved right, or extended. 1.99s retained in total across all
   14 clips. Two of those are real speech that was being clipped:
   - `vlc-defender-plugin-cache` 44.659→45.099, peak **-3.9 dB** — the "dat" above.
   - `canva-session-revocations-s3` 35.320→35.490, peak **-6.4 dB** — same bug, second instance,
     after "empty."

   The remaining six are quiet consonant decay (peak -20 to -37 dB, 40–230 ms), which is the tail
   the function was built to protect in the first place.
4. `tests/fixtures/edl/*.gaps.txt` regenerated via `regen_gaps.py` for the six slugs still in
   `assets/`; three moved, all in `speech_end` only.

### Not fixed — the caption and the audio can still disagree

Nothing checks that the audio under a surviving caption word survived with it. Here the caption read
`.dat` over audio the EDL had removed, and no report flagged it — `debug.5.timeline.txt` even labels
the gap `KEEP` (the `debug_report.py:531` mislabel noted under Gap 4). A cheap check would be: for
every kept word, assert some EDL keep-span covers `[start, speech_end]`. Related to Gap 2, which
comes at the same class of defect from the script side.

## Where this would slot in

Gaps 1 and 2 are `/prepare-video` Step 3/4 concerns. Gap 4 landed in `gap_detector`/`edl`, which
run during Step 2, so an existing slug only picks it up on a re-transcribe. Gap 3 is earlier — it changes Step 2
(transcription) itself, so it must land before a run, not after; it cannot be applied as a fix to
an existing `captions.json`. Gap 2 landed inside Step 3 rather than as a
Step 2.6 of its own, with its wrong-word hits eligible for auto-fix and its dropped-sentence hits
report-only.

Gap 2's wrong-word fix edits `words[]` text, which the auto-fix policy in
`.claude/commands/prepare-video.md` now explicitly permits.

## Evidence

Gaps 1 and 2 — `canva-session-revocations-s3`:

- `assets/canva-session-revocations-s3/856D0E66-E505-4529-9AC1-E30DCF76FFDC.debug.7.fixlog.txt`
- `assets/canva-session-revocations-s3/856D0E66-E505-4529-9AC1-E30DCF76FFDC.debug.5.timeline.txt` (L313-368)
- `assets/canva-session-revocations-s3/856D0E66-E505-4529-9AC1-E30DCF76FFDC.debug.6.summary.txt` (L80-99)

Gap 3 — `figma-pgkeeper-connection-pooler`:

- `assets/figma-pgkeeper-connection-pooler/C374FEFC-4C20-419F-9C26-07C4289112D6.debug.7.fixlog.txt`
  (CAPTION TEXT FIXES APPLIED section)
- `assets/figma-pgkeeper-connection-pooler/C374FEFC-4C20-419F-9C26-07C4289112D6.debug.6.summary.txt`
  (retranscription window at 49.580s — `Chachabit` survived a retranscribe at 0.56)
- `reelcut/cli.py:434-446` — the slug-derived prompt construction
