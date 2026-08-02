# Video Idea — SSCD, and why "just resize it 2%" doesn't beat Instagram

**One video.** Series fit: `interesting-tech` (name an unknown artifact, withhold the how) or
`tbbt` ("So [Company] literally…"). Debunk format, backed by Meta's *own* published research —
this is not opinion, there's a paper and a repo.

**Why this one is good:** every reel-growth account repeats the same folklore — "resize your
video by 1–3%", "mirror it", "crop the edges", "re-encode it" and Instagram won't know it's a
repost. Meta published the exact model class trained to see through all of those. The video
is: here's the advice everyone gives you, here's the AI that was literally built to defeat it.
It's a satisfying reversal and it's true.

---

## Hook options

Lead candidate (Hidden Knowledge — names the exact myth, then reverses it):
- **"Everyone tells you to resize your reel a couple percent to beat Instagram but Meta published the exact AI trained to see through it."**

Alternates:
- **"What is SSCD and why does it make 'just resize your video' completely useless?"** *(What-is — SSCD is unknown, so the name itself withholds)*
- **"So Instagram runs an AI that was trained on purpose to see through every trick people use to reupload a video."** *(tbbt "So [Company] literally")*
- **"Everyone reposts videos by cropping and mirroring them but there's a Meta model that treats that as the same video anyway."**

Weakest-but-punchy: **"You can't resize your way past Instagram and Meta published the proof."**

---

## The angle it has to deliver

The whole video hinges on one reveal: **the tricks aren't just weak, they're the literal training
data.** SSCD (and its video-copy-detection siblings) are trained *by* generating crops, flips,
color shifts, re-encodes, overlaid text/emoji, and blur of an image, then teaching the model that
all of those are the *same* content. So the exact edits people sell as "evasion" are the
augmentations the model was hardened against. That's the punchline: you're not fooling it, you're
feeding it a case it was optimized to get right.

Beats to hit in ~60s:
1. The folklore (resize 2%, mirror, crop, re-encode → "new" video).
2. What copy detection actually does: turn each frame into a **descriptor / embedding**, then
   measure distance. Copies land close together regardless of pixels.
3. The twist: the model is trained with **exactly those edits as augmentations**, so invariance to
   them is the point, not a weakness.
4. So-what: two clips can look "different" byte-for-byte and still be one item to the system.
   (Optional CTA / soft tie to your own niche: this is why reposting the same body with a new
   intro doesn't reset the counter.)

---

## The real technical substance (for the script)

- **SSCD** = *A Self-Supervised Descriptor for Image Copy Detection*, Meta AI (FAIR), CVPR 2022.
  It maps an image to a vector; a copy of that image maps to a nearby vector. Detection = nearest-
  neighbour distance under a threshold, not pixel comparison.
- **How it's trained:** self-supervised contrastive learning (SimCLR-style) with an entropy
  regularization term, using aggressive augmentation — crops, rotations, horizontal flips, color
  jitter, blur, JPEG re-compression, and overlays of text/emoji/other images. Built for the 2021
  **Image Similarity Challenge (ISC)**, where the whole task was "find the original despite these
  manipulations."
- **Video:** SSCD is image-level (applied frame-wise). Meta also ran the 2022 **Video Similarity
  Challenge (VSC)** and published video-copy-detection models for exactly this — same idea across
  frames plus temporal alignment.
- **The point for the myth:** resize / crop / flip / re-encode are *inside the augmentation set*.
  Invariance to them is a trained objective. That's why "change it 2%" does nothing to the
  descriptor distance.

---

## Keep honest (don't let the script overclaim)

- Meta has **not** publicly confirmed the exact production model behind Instagram's Reels
  deduplication. SSCD/VSC are the *published, verifiable* demonstration of the capability — say
  "this is the class of model Meta builds and open-sourced for exactly this problem," not "this
  specific model runs on your uploads." The debunk stands either way: the capability is public and
  the tricks are the training data.
- Copy-detection (is this the same content?) and reach-throttling (does the algorithm suppress it?)
  are related but not identical. The honest claim is "these edits don't make it a different video,"
  not "these edits are why your reach dropped." Don't promise a growth outcome.
- Don't turn it into a how-to-evade video. The frame is "here's why the popular advice is
  physically defeated," which is more interesting and doesn't age into bad advice.

---

## Sources

- [SSCD repo](https://github.com/facebookresearch/sscd-copy-detection) (Meta / FAIR, open source)
- Paper: *A Self-Supervised Descriptor for Image Copy Detection*, Pizzi et al., CVPR 2022
  ([arXiv:2202.10261](https://arxiv.org/abs/2202.10261))
- [2021 Image Similarity Challenge (ISC)](https://ai.meta.com/blog/the-image-similarity-challenge-and-data-set-for-detecting-image-manipulation/)
  — the manipulation set SSCD was built to beat
- 2022 Video Similarity Challenge (VSC) — the video-copy-detection counterpart
- Prior in-repo research: `INSTAGRAM_DEDUP_PLAN.md` (SSCD > 0.75 clustering, audio fingerprinting)
  and `INSTAGRAM_DEDUP_EVASION_PLAN.md` (technique-by-technique scoring)

---

*Run through `/produce-script` with `interesting-tech` (or `tbbt`) so it inherits the right voice,
length, and CTA. Verify the SSCD/ISC/VSC facts at produce time before scripting.*
