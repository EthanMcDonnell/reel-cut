# Instagram De-duplication + Per-Hook Captions — Plan / Handoff

**Status:** planning only, nothing built yet. Written 2026-07-04.

**Goal:** we render three videos per topic (`render-hooks` → `<slug>-hook1/2/3.mp4`) that share
an identical body and differ only in the ~3s hook. Concern: Instagram's algorithm clusters them
as near-duplicates and throttles reach. User wants (a) per-video cute captions and (b) any
legitimate way to reduce clustering.

---

## How the pipeline produces the 3 videos (context)

- `/produce-video` (`.claude/commands/produce-video.md`) → fills `images.json` + `headings.json`
  (one hook card per hook), then runs `reelcut render-hooks`.
- `render-hooks` (`reelcut/cli.py:161`) renders one mp4 per hook: `hook_i + shared body`, other
  hooks cut out. Outputs `output/<slug>-hook{i}.mp4`.
- **All three share:** identical body footage, identical voiceover audio, identical music
  (`chill-draw-interest`, the only track in `assets/audio/`), identical burned-in captions,
  identical title card (same title/subtitle stamped on every hook card).
- Audio track selection: `audio.json` per slug → `_resolve_audio_tracks` (`cli.py:842`). Config
  `audio.tracks.<name>.source_start` already supported (`config.yaml:97`).
- Visual transform point: `_final_encode` in `reelcut/renderer.py` (has a `scale` filter ~line 269).

---

## Research findings (the important part — read before building anything)

Meta's duplicate detection is **purpose-built to defeat cosmetic render tricks.** Do not build
visual-transform / metadata / speed differentiation expecting it to move the originality score.

- **SSCD** (Self-Supervised Copy Detection — the model IG runs) is explicitly trained to see
  through **horizontal flips, large crops, color/tone shifts, watermark insertion, background
  substitution, and re-encodes.** Clusters anything above **0.75 cosine similarity.** An
  85%-identical body stays well above that. → zoom/crop/eq per hook = wasted effort.
- **Audio fingerprinting** catches modified audio "even if creators alter the pitch, speed, or
  tempo," ~97% accuracy. Our **voiceover is byte-identical across all three** — a strong audio
  match that no music trick removes. Micro-speed/atempo is dead.
- **Metadata is not used** for duplicate detection (SSCD is content-based).
- IG assigns an **Originality Score** per Reel and compares against your **own previous uploads**;
  content sharing **70%+ visual OR audio** with a prior post is deprioritized.
- **First ~6s scanned hardest** — distinct hooks are the on-strategy move (we already do this).
- IG is **specifically cracking down on same-footage "trial reel" hook variants in 2025–26.**
- Creator-reported reality: "same footage + new audio + new captions → still flagged as
  near-duplicate, reach drops fast."

Sources: [SSCD repo](https://github.com/facebookresearch/sscd-copy-detection) ·
[edpizzi copy-detection](https://edpizzi.com/research/copy-detection/) ·
[foximusic audio](https://www.foximusic.com/blog/instagram-reels-music-copyright-legal-guide/) ·
[audiodrome](https://audiodrome.net/for-creators/instagram-music-copyright/) ·
[avramify duplicate penalty](https://www.avramify.com/blogs/news/instagrams-new-penalty-for-duplicate-reels) ·
[engagedm trial-reel crackdown](https://engagedm.co.uk/2025/09/30/trial-reels-rules/) ·
[flowshorts algorithm](https://flowshorts.app/blog/instagram-reels-algorithm)

**Verdict:** there is no render hack that reliably de-clusters three videos sharing an identical
body + identical voiceover. The durable lever is **posting strategy**, not rendering.

---

## User decisions (locked)

1. **One audio track only** for now → whole-track music-swap lever is OFF the table.
2. Open to visual / "backend" differentiation, but wanted research first (see verdict above).
3. **Filename = caption.** User wants the mp4 filename to literally be the caption text
   (readable in Telegram; user believes IG may read it too — see caveat below).
4. **Same account** for all three (so IG compares them against each other).
5. Hooks already differ per video.

---

## The plan

### ✅ Build: per-hook caption generator + filename = caption
- New `/produce-video` step: generate **one caption per hook**, each derived from *that hook's*
  angle so the three genuinely differ.
- **Style:** all-lowercase, cute, **≥1 emoji near the end** (💣 billion-laughs energy). Reuse the
  `hooks` / `.claude/voice/voice-profile.md` tone.
- **Filename:** rename each output to the caption text. Deliver the caption in three places:
  the filename, a sidecar (`output/<slug>-hookN.caption.txt`), **and** the Telegram message body
  (so user can copy-paste into IG's real caption field).
- **Caveat to remember:** IG does **not** read the upload filename as the caption or any ranking
  signal — the caption field is separate and pasted manually. Filename=caption is a *convenience*
  (human handle + Telegram label), not an algo lever. User was told this and still wants it.
- **Implementation gotchas:**
  - Emoji + spaces in filenames break Step 7's `for f in output/<slug>-hook*.mp4` glob. Need to
    iterate the actual rendered files (or keep a run manifest mapping slug→caption→file) instead
    of a glob on the new names.
  - Tailscale link (`https://host/reels/<name>`) needs **URL-encoding** for spaces/emoji.
  - Decide separator policy (keep spaces? APFS handles emoji fine, but URLs get ugly).

### ⚠️ Recommend (no code): posting strategy is the actual dedup answer
- Post the three via **IG Trial Reels** (built for testing variants against non-followers), or
  **space them out days apart.** Back-to-back same-account posting is what gets throttled.

### ❌ Do NOT build
- Zoom / crop / eq / horizontal-flip / metadata / speed differentiation. SSCD + audio
  fingerprinting are built to defeat exactly these on an 85%-shared body. Wasted effort.
- Whole-track music swap (only one track available anyway).

### 🔵 Only if spacing + trial-reels prove insufficient (expensive, deferred)
- Meaningfully different **body** per variant (different overlay/B-roll coverage across the whole
  runtime, or a re-edit). This is the only thing that truly de-clusters — but it costs the
  efficiency the 3-from-1 pipeline exists to provide.

---

## Next session: where to start
1. Confirm filename/caption delivery shape (filename + sidecar + Telegram — see gotchas above).
2. Implement the caption-generation step in `.claude/commands/produce-video.md` (prompt + style
   rules) and the rename/sidecar/URL-encode wiring in `render-hooks` (`cli.py:161`) + Step 7 of
   the command doc.
3. Leave posting strategy as a note to the user (Trial Reels / spacing).
