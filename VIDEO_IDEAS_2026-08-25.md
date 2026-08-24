# Video Ideas — 25 August 2026

Generated from the 15 highest-engagement and highest-viewed posts, 12 most-saved posts, freshly refreshed `tbbt` and `updates` candidates, verified full-text sources, and the standing archive/idea-bank exclusion set.

## What the analytics actually say

| Signal | Post | Views | Engagement | Shares | Saves | Comments |
|---|---|---:|---:|---:|---:|---:|
| Strongest all-rounder | Claude usage limits | 122,684 | 6,525 | 1,411 | 4,464 | 3,038 |
| Biggest mechanism story | 42.zip | 101,192 | 5,039 | 408 | 643 | 36 |
| Best systems explainer | Reddit moves Kafka to Kubernetes | 84,772 | 2,352 | 379 | 836 | 219 |
| Strongest visible-breakage news | Windows update failures | 78,163 | 1,966 | 1,237 | 669 | 290 |
| Strongest price-shock share driver | Copilot cost increase | 92,153 | 1,466 | 2,462 | 221 | 71 |

- **The channel has one massive practical-AI outlier.** The Claude-limits explainer has 1.45× the views of the next-best post and 5.3× the saves of the next-best post. The AI Fundamentals ideas therefore lead with a daily work problem and a mechanism, not an abstract definition.
- **Shares and saves want different shapes.** A sudden, concrete consequence drives shares: Copilot pricing (2,462 shares) and Windows breakage (1,237). Systems with a reusable explanation drive saves: Claude limits (4,464) and Reddit’s Kafka migration (836).
- **Do not over-read the newest low tail.** The lowest recent posts are only days old, so their reach is not comparable yet. The durable lesson from the archive is clearer: an unusual mechanism with a concrete consequence beats company history or a generic product announcement.

## Deliberate exclusions

- No Windows/Microsoft breakage: the BitLocker update and VLC plugin-cache stories are already produced or active.
- No Copilot/Cursor/Claude token-pricing thesis, Claude limits, context rot, or generic prompt-injection explainer: all are already produced or proposed.
- No OpenAI/Hugging Face agent-security incident, Mythos cluster, Claude watermark, Figma PGKeeper, Canva session revocations, GitHub case folding, Kafka-to-Kubernetes migration, or Dropbox cloud-exit variation.
- No crowded historical-security artifact such as Heartbleed, Log4Shell, Rowhammer, 42.zip, Billion Laughs, Stuxnet, Ariane 5, or Therac-25.
- No Hot Takes: the available first-person candidates duplicate active GitHub Desktop, commit-message, worktree, Windows-breakage, or AI-vs-math material. A fabricated opinion would be worse than an incomplete section.

## updates — Tech & AI Updates (5)

*Pattern: `[Company] just [surprising action]` — a current consequence first, then the technical mechanism.*

1. **AliExpress was silently running audio in your browser.** [share]

   Two hidden Web Audio graphs made an inaudible oscillator, analysed its output, set the gain to zero, and still connected to the audio destination. That supplied one signal in a larger browser fingerprint and, on the investigator’s setup, kept Bluetooth multipoint headphones treating the PC as active. The video should distinguish what the client-side investigation proves (collection and transmission) from what it cannot prove (server-side retention or use).

   - **Source:** [The Silent WebAudio Fingerprint That Hijacked Bluetooth Multipoint](https://0xgosu.dev/blog/aliexpress-silent-webaudio-fingerprinting/) — 0xgosu, 21 August 2026.
   - **Why:** Same instantly visible consequence as the Windows winner, but with a weird enough mechanism to earn the explanation.
   - **Notes:** Re-check the observed Bluetooth behaviour before production; it varies by browser, operating system, and headphones.

2. **Claude’s new browser tool can target a button, not just a pixel.** [share]

   Anthropic has made computer use, Skills, and Files generally available, while adding browser use: the agent can read page structure and act on a particular form field or button rather than guessing from screenshot coordinates. The body should explain why structure plus multi-action turns reduces brittleness, then separate that from the still-necessary permission and review boundaries around web agents.

   - **Source:** [Build production agents with computer use, the Skills API, and the Files API](https://claude.com/blog/computer-use-skills-api-files-api) — Anthropic, 20 August 2026.
   - **Why:** Directly adjacent to the channel’s biggest practical-AI winner, with a concrete new capability rather than another model-release claim.
   - **Notes:** Fresh platform announcement — verify availability and rate-limit details at production time.

3. **Grok can leak your chats because it decrypts its own instructions.** [share]

   Researchers showed an encrypted instruction can pass a static text guardrail, be decrypted inside the model’s code-execution environment, then arrive as trusted-looking tool output. The core explanation is not “encryption beats AI”; it is that a guardrail which only reads text cannot inspect the plaintext an agent creates during its own tool run.

   - **Source:** [Grok exfiltrates user data when malicious instructions are encrypted](https://arstechnica.com/security/2026/08/grok-exfiltrates-user-data-when-malicious-instructions-are-encrypted/) — Ars Technica, 20 August 2026.
   - **Why:** It turns an abstract AI-security warning into one sharp architectural boundary: input filtering versus runtime output.
   - **Notes:** Keep the explanation defensive and high-level; do not reproduce attack payloads or operational steps. Re-check remediation status before production.

4. **Your AI glasses can be found by their Bluetooth fingerprint.** [share]

   Civil-defence apps identify known smart-glasses models by Bluetooth service identifiers and estimate proximity from signal strength. That can show a device is nearby, not prove it is recording. The useful technical story is the trade-off: background detection is constrained by mobile operating systems, identifiers can be missing, and false positives are unavoidable.

   - **Source:** [As demand for Meta AI glasses explodes, it’s harder to avoid creepy recordings](https://arstechnica.com/tech-policy/2026/08/meta-ai-glasses-may-get-creepier-and-apps-that-detect-them-arent-perfect/) — Ars Technica, 21 August 2026.
   - **Why:** It has a clear personal consequence and an explorable mechanism, unlike a generic privacy-policy story.
   - **Notes:** Be explicit that Bluetooth detection is imperfect and does not establish active recording.

5. **A car stereo updater was installing a botnet.** [share]

   Researchers found Android automotive head units whose legitimate updater accepted MQTT-delivered app-install instructions. That created a chain from firmware updater to a multi-stage downloader and proxy-botnet payload. The video should centre the design error—an update channel that could install an absent app—not the malware’s operational details.

   - **Source:** [First Android malware targeting automotive head units](https://securelist.com/android-head-unit-malware/121106/) — Kaspersky Securelist, August 2026.
   - **Why:** A familiar object with an unexpected attack surface is exactly the concrete-failure shape that people share.
   - **Notes:** Keep the account at an architectural level; do not include indicators, payload configuration, or reproduction detail. Re-check vendor remediation before production.

## tbbt — Tech Behind Big Tech (3)

*Pattern: a named company makes an absurdly specific engineering choice, then the machinery earns the surprise.*

1. **Waymo put a data centre in a car trunk.** [save]

   Waymo’s driver has to process 13 high-resolution cameras, lidar, and radar onboard within milliseconds, in heat, vibration, and without a human fallback. Its answer is a heterogeneous computer built around a custom 5nm ASIC with more than 1,000 TOPS for front-end sensor processing, plus two independent compute paths that can take over on fault. The video is about why low-batch, physical-world inference cannot just borrow a cloud stack.

   - **Source:** [A look under our trunk: what’s in our compute](https://waymo.com/blog/2026/08/look-under-our-trunk) — Waymo, 20 August 2026.
   - **Why:** It has the Dropbox-style “boring physical constraint changes the architecture” reversal, but in an entirely different system.

2. **Grab makes its AI choose a job before it answers.** [save]

   Grab’s merchant assistant can sound polished while recommending the wrong intervention. Before it loads data or writes an answer, a routing model selects the task shape, allowed context, metrics, tool path, and guardrails. The useful reveal is that a slower first token prevents the much more expensive failure: confidently sending more orders to a merchant whose real problem is paused outlets.

   - **Source:** [Building Jarvis Pro: Route first, answer later](https://engineering.grab.com/jarvis-pro-route-firsr-answer-later) — Grab Tech, 21 August 2026.
   - **Why:** It turns “AI hallucination” into a specific system-design decision with a satisfying operational payoff.

3. **Cloudflare lets you uncheck what an AI agent can touch.** [save]

   An OAuth client can ask for several permissions, but Cloudflare now lets the developer mark some as optional and lets the user deselect them at consent time. The resulting token carries only the granted scopes, so an agent has to work with the narrower capability rather than assuming it received everything it requested.

   - **Source:** [From all-or-nothing to task-based OAuth consent](https://blog.cloudflare.com/task-based-oauth-consent/) — Cloudflare, 20 August 2026.
   - **Why:** It gives the agent-security conversation a concrete interface and a mechanism viewers can immediately recognise.

## interesting-tech — Interesting Tech (3)

*Pattern: name a strange, concrete artifact first; withhold the explanation until the mechanism does the work.*

1. **What is a thunderquake and why can it map the ground?** [save]

   Penn State researchers used thunder-generated seismic waves and an existing 2.5-mile telecoms cable to image shallow ground. A laser measures tiny strain-induced changes in backscattered light along the fibre, turning the cable into hundreds of closely spaced sensors. The surprise is that thunder supplies the seismic source that expensive survey gear or earthquakes normally provide.

   - **Source:** [Thunderquakes: A new way to image the Earth’s subsurface](https://e3.eurekalert.org/news-releases/1140444) — Penn State / EurekAlert!, 21 August 2026.
   - **Why:** Like 42.zip, it starts with an object viewers think they understand, then reveals an unexpected use for it.

2. **What is SELF and why can a SQLite database run like an app?** [save]

   SELF is a prototype executable format where the program’s loadable segments, symbols, imports, and dynamic-linking data live in SQLite tables. Linux’s `binfmt_misc` recognises the SQLite header plus a custom application ID, then hands the file to an interpreter that maps segments and jumps to the entry point. The payoff: tools such as `strip` or `ldd` become database operations and queries.

   - **Source:** [ELF is a database that refuses to admit it](https://fzakaria.com/2026/08/23/your-executable-is-a-sqlite-database) — F. Zakaria, 23 August 2026.
   - **Why:** It is an unfamiliar physical artifact with a visual hook and a mechanism substantial enough for a full minute.
   - **Notes:** Present it as a working prototype, not a replacement for ELF; the source documents latency and page-sharing trade-offs.

3. **What is seL4 and why did it take a proof to finish it?** [save]

   Proofcraft says seL4’s AArch64 implementation now has functional-correctness, integrity, and confidentiality proofs. The point is not that the kernel has fewer bugs; it is a mathematical claim that, under stated assumptions, one application cannot learn another application’s information without authorisation. Explain why proving an implementation matches a security property is a different category from running a large test suite.

   - **Source:** [seL4 security proofs now complete on AArch64](https://proofcraft.systems/news-2026/#2026-08-21) — Proofcraft, 21 August 2026.
   - **Why:** It is a named artifact with a deceptively huge consequence, without repeating the channel’s exploit-heavy incident pool.

## tech-in-one-breathe — Tech in One Breath (3)

*Pattern: recognition first—one familiar-but-unexplained primitive, one clean analogy, no detour.*

1. **What is sensor fusion and why does a self-driving car need more than a camera?** [save]

   Explain that sensor fusion is the process of combining different sensors’ incomplete views into one world model: cameras bring colour and texture, lidar gives geometry, radar helps with range and motion. The trick is reconciling them quickly enough that the car acts on one coherent scene rather than three competing guesses.

   - **Source:** [A look under our trunk: what’s in our compute](https://waymo.com/blog/2026/08/look-under-our-trunk) — Waymo, 20 August 2026.

2. **What is distributed acoustic sensing and why can a fibre cable hear thunder?** [save]

   Explain DAS as a laser sent down an ordinary fibre cable: tiny stretches change the returning light, so each segment acts like a microphone for strain in the ground. It is not recording sound through the cable; it is measuring how the cable itself is disturbed.

   - **Source:** [Thunderquakes: A new way to image the Earth’s subsurface](https://e3.eurekalert.org/news-releases/1140444) — Penn State / EurekAlert!, 21 August 2026.

3. **What is formal verification and why is it stronger than a test suite?** [save]

   Explain the difference between testing a lot of examples and proving a property for every permitted execution. A test says “this input worked”; a formal proof says “given these assumptions, this class of bad state cannot occur.” Use seL4’s confidentiality proof as the concrete anchor.

   - **Source:** [seL4 security proofs now complete on AArch64](https://proofcraft.systems/news-2026/#2026-08-21) — Proofcraft, 21 August 2026.

## ai-fundamentals — AI Fundamentals (3)

*Pattern: a common AI-work pain, then the hidden mechanism that makes it happen.*

1. **Your AI can pass every test and still build the wrong thing.** [save]

   Tests can prove the implementation matches the agent’s interpretation of a requirement, not that the interpretation was correct. Explain the missing layer: write the success criteria and unresolved decisions first, then make each criterion traceable to code and a test. The hook works because anyone using a coding agent has seen a polished diff that feels wrong before they can explain why.

   - **Source:** [Why AI-Generated Code Is Easy but Engineering Trust Is Hard](https://engineering.salesforce.com/why-ai-generated-code-is-easy-but-engineering-trust-is-hard/) — Salesforce Engineering, August 2026.

2. **A helpful AI should classify your question before it searches.** [save]

   An agent asked “what should I tell this merchant?” must first decide whether it needs an operational diagnosis, an ads recap, a metric reconciliation, or a refusal. Explain routing as a contract for context, tools, and guardrails—not a fancy way to make the answer sound organised.

   - **Source:** [Building Jarvis Pro: Route first, answer later](https://engineering.grab.com/jarvis-pro-route-firsr-answer-later) — Grab Tech, 21 August 2026.

3. **An AI agent should get less access than it asks for.** [save]

   Agents often request broad permissions because they might need them. Explain why the safer design is a partial grant: the person unchecks optional scopes, the access token contains only what remains, and the agent must degrade gracefully instead of quietly retaining power it does not need.

   - **Source:** [From all-or-nothing to task-based OAuth consent](https://blog.cloudflare.com/task-based-oauth-consent/) — Cloudflare, 20 August 2026.

## hot-takes — Hot Takes (0)

No new candidates this run. The available first-person material is already active, queued, or too adjacent to an existing video. I will not manufacture a view for you just to fill the count.

## Recommended production order

1. **AliExpress was silently running audio in your browser.** Fresh, weird, personally legible, and built around a real mechanism.
2. **A car stereo updater was installing a botnet.** A strong current-failure hook with a clear, safe architectural explanation.
3. **Claude’s new browser tool can target a button, not just a pixel.** Directly useful to the audience that made Claude-limits the channel’s largest winner.
4. **Waymo put a data centre in a car trunk.** Strong evergreen systems story with a visual premise and concrete hardware constraints.
5. **Grok can leak your chats because it decrypts its own instructions.** Timely AI-security news where the model/tool boundary makes the story teachable.

---

**Total:** 17 ideas — 5 updates, 3 TBBT, 3 Interesting Tech, 3 Tech in One Breath, 3 AI Fundamentals, 0 Hot Takes.

The updates, TBBT, and Interesting Tech entries are source-verified. Tech in One Breath and AI Fundamentals are concept picks grounded in the linked primary examples. Hot Takes is deliberately empty rather than fabricated. Re-check freshness-sensitive product availability, incident status, and any live figures before producing.
