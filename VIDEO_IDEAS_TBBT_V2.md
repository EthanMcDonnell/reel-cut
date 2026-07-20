# New Video Ideas (round 2) — tbbt, updates, interesting-tech, tech-in-one-breathe, ai-fundamentals

The round-1 ideas in `VIDEO_IDEAS.md` weren't landing. This doc is the fresh batch across
every series. tbbt and updates are pulled from real articles and verified against the full
text (not the RSS blurb); interesting-tech leans on real, fact-checked incidents but branches
away from the "malware/exploit" rut the existing list was stuck in; tech-in-one-breathe and
ai-fundamentals are manually sourced per their series files (no DB for those two) and checked
against the existing backlog so nothing here duplicates a queued idea.

## tbbt — 10 New Video Ideas

The tbbt ideas in `VIDEO_IDEAS.md` weren't landing. This is a fresh batch, pulled straight
from unread/unscored articles in `scrape/db/influencer.db` (`tbbt` table) and verified by
scraping each full article — not just the RSS blurb — so the numbers below are real, not
guessed. Modeled on the two best tbbt videos shipped so far (Dropbox's Magic Pocket /
"quit the cloud" story and Reddit's live Kafka-to-Kubernetes migration): a real
architectural decision, a concrete outcome, told to engineers who don't need the 101.
**Dropbox and Reddit are deliberately excluded** — both companies already have shipped
videos; don't reuse them.

Dedup checked against: `series/tbbt.md`, `VIDEO_IDEAS.md`, the Obsidian vault (`Videos To
Do` / `Videos Completed` / `Video Ideas`). None of the 10 below overlap with anything
already shipped, queued, or previously proposed.

---

1. **"What happens when GitHub goes down and the only way to fix it is GitHub?"** — GitHub hosts its own source on github.com, so a deploy script fixing a `github.com` outage can quietly depend on `github.com` itself (a "hidden" or "transient" dependency, e.g. a tool checking for updates mid-incident). They can't just block github.com from the hosts — those machines are still serving live production traffic during the incident. Solved with eBPF: selectively monitoring and blocking exactly the calls that create the circular dependency, without cutting the host off from everything else.
   - **Source:** [How GitHub uses eBPF to improve deployment safety](https://github.blog/engineering/infrastructure/how-github-uses-ebpf-to-improve-deployment-safety/) (The GitHub Blog, Apr 2026)

2. **"So Pinterest's GPU training jobs kept crashing because of literal zombies living inside the machine."** — A 3-month investigation into intermittent network resets killing expensive Ray/GPU training runs (some jobs saw a >25% drop in success rate). Root cause: ~70,000 "zombie" memory cgroups tracked by the kernel vs. only 240 actually in use, built up by a crash-looping AWS ECS Agent that had no business running on their Kubernetes nodes in the first place — a leftover default from the base AMI. Iterating that zombie list starved a CPU core for seconds at a time, which reset the network driver mid-job.
   - **Source:** [Finding zombies in our systems: A real-world story of CPU bottlenecks](https://medium.com/pinterest-engineering/finding-zombies-in-our-systems-a-real-world-story-of-cpu-bottlenecks-ea4722e552eb) (Pinterest Engineering, Apr 2026)

3. **"Cloudflare's billing pipeline slowed to a crawl and every metric they checked said nothing was wrong."** — The daily ClickHouse aggregation jobs behind hundreds of millions of dollars in usage billing suddenly got slow after a migration. I/O, memory, rows scanned, parts read — all normal. The actual bottleneck was buried in ClickHouse's internals (query plan lock contention); Cloudflare tracked it down and shipped three patches upstream to fix it.
   - **Source:** [Our billing pipeline was suddenly slow. The culprit was a hidden bottleneck in ClickHouse](https://blog.cloudflare.com/clickhouse-query-plan-contention/) (Cloudflare Blog, May 2026)

4. **"Airbnb ingests 50 million data points a second, and shuffles them like a deck of cards so one bad app can't blind everyone else."** — 1.3 billion active time series, 50M samples/sec, 2.5PB of data, after Airbnb moved off a hosted metrics provider. The trick to surviving that scale without one noisy or attacked tenant taking down monitoring for the whole company: shuffle sharding, so each tenant's writes and queries only ever hit a random subset of nodes.
   - **Source:** [Building a fault-tolerant metrics storage system at Airbnb](https://medium.com/airbnb-engineering/building-a-fault-tolerant-metrics-storage-system-at-airbnb-26a01a6e7017) (Airbnb Engineering, Apr 2026)

5. **"What is steganography and why is Datadog hiding secret URLs inside every screenshot you share?"** — Screenshots of dashboards lose all context (time range, query, dashboard state) compared to a live share link — but people take screenshots anyway because they're fast and simple. Datadog's fix: invisibly encode the widget's metadata into the screenshot's pixels itself, watermarking that survives copy-paste, color profiles, and different screen densities, at a rate of over a billion watermarks rendered per day without slowing the app down.
   - **Source:** [Steganography at scale: Embedding share URLs in Datadog widget screenshots](https://www.datadoghq.com/blog/engineering/steganography-at-scale/) (Datadog, 2026)

6. **"So Meta is already rewriting its encryption to beat hackers who are stealing data they can't even read yet."** — "Store now, decrypt later": adversaries harvest encrypted traffic today, betting that quantum computers will crack it within 10-15 years. Meta's response is a multi-year, already-underway migration to post-quantum cryptography (NIST's ML-KEM/Kyber and ML-DSA/Dilithium) across its internal infrastructure — defending data that hasn't been broken yet, against a computer that doesn't exist yet.
   - **Source:** [Post-Quantum Cryptography Migration at Meta: Framework, Lessons, and Takeaways](https://engineering.fb.com/2026/04/16/security/post-quantum-cryptography-migration-at-meta-framework-lessons-and-takeaways/) (Engineering at Meta, Apr 2026)

7. **"So Figma borrowed a trick from network routers to stop Postgres from falling over."** — Figma outgrew PgBouncer: it's single-threaded, has no way to prioritize important traffic over misbehaving traffic, and offers no protection against connection-storm pile-ons after an overload. Their replacement, PGKeeper, borrows CoDel — a load-shedding algorithm originally built for congested network routers — and applies it in front of their entire Postgres fleet instead.
   - **Source:** [PGKeeper: Building the bouncer we needed for Postgres](https://www.figma.com/blog/pgkeeper-building-the-bouncer-we-needed-for-postgres/) (Figma Engineering, May 2026)

8. **"So Grab makes its containers start running code before the image even finishes downloading."** — Large Airflow/Spark container images were taking minutes to pull, wrecking cold-start times and auto-scaling. Grab's fix (Docker lazy loading via SOCI) doesn't shrink the download — it reorders it, letting the container start executing while the rest of the image streams in behind it. Result in production: 30-40% faster startup times for both services.
   - **Source:** [Docker lazy loading at Grab: Accelerating container startup times](https://engineering.grab.com/docker-lazy-loading) (Grab Tech, 2026)

9. **"So Databricks forked an open-source database just to survive ingesting 10 trillion data points a day."** — 5 billion active time series, 10 trillion samples ingested daily, and the #1 reliability problem was that their old time-series databases couldn't be scaled up fast enough — something Databricks needed to do almost daily. Their fix: fork the open-source Thanos project into their own system (codenamed Pantheon), now running 160+ instances across three cloud providers, cutting monitoring downtime by roughly 5x and saving millions in annual cloud costs.
   - **Source:** [10 trillion samples a day: Scaling beyond traditional monitoring infra at Databricks](https://www.databricks.com/blog/10-trillion-samples-day-scaling-beyond-traditional-monitoring-infra-databricks) (Databricks Engineering, 2026)

10. **"So Meta secretly ran two versions of the same library at once just to escape its own code fork."** — Meta had forked WebRTC internally for years to hit its performance needs for Messenger, Instagram, and Quest — but a permanent fork drifts further from upstream every year until merging becomes too expensive to ever do again (the "forking trap"). Meta's way out: a modular dual-stack architecture that runs both the old fork and the latest upstream simultaneously inside one library, letting them A/B test each new upstream release before fully switching over — across 50+ internal use cases.
    - **Source:** [Escaping the Fork: How Meta Modernized WebRTC Across 50+ Use Cases](https://engineering.fb.com/2026/04/09/developer-tools/escaping-the-fork-how-meta-modernized-webrtc-across-50-use-cases/) (Engineering at Meta, Apr 2026)

---

*All 10 are unverified-for-video (not yet run through `/produce-script`) but source-verified —
every fact above came from the full article text, not the feed description. Run through
`/produce-script --series tbbt` when ready to pick one; re-check the source for anything
that reads like it needs a live number confirmed (e.g. exact current instance counts).*

---

## updates — 5 New Video Ideas

Pulled from the `updates` table — most of what's queued there right now is unscored Reddit
noise, but a handful of real stories surfaced. All five are still fresh as of today
(2026-07-13); **re-check freshness at produce time**, per this series' own rule — an "update"
decays fast, and two of these share one source article, so don't ship both back to back.

1. **"The EU just gave Meta an ultimatum: kill autoplay and infinite scroll, or pay up to 6% of its global revenue."** — The European Commission's preliminary finding: Meta "did not adequately assess the risks of its addictive design," and its existing teen protections (15-minute screen caps, etc.) "failed to effectively tackle the risks." If Meta doesn't change course before the EC's final decision, it risks a fine of up to 6% of global annual turnover under the Digital Services Act.
   - **Source:** [Disable autoplay and infinite scroll or risk massive fines, EU tells Meta](https://arstechnica.com/tech-policy/2026/07/disable-auto-play-and-infinite-scroll-or-risk-massive-fines-eu-tells-meta/) (Ars Technica, 2026-07-10)

2. **"29 US states are suing Meta for up to $1.4 trillion — a number Reuters says is uncomfortably close to Meta's entire market cap."** — Same underlying story as #1, different angle: Meta failed to get a 29-state lawsuit over kids' social media addiction thrown out; trial starts in August, and the states may seek penalties nearly as large as Meta's ~$1.5T market capitalization.
   - **Source:** same as #1 (Ars Technica, 2026-07-10)

3. **"Meta just released an AI that mines public Instagram photos to make deepfakes — and opted most users in automatically."** — Meta's new model, Muse, pulls from public Instagram feeds to generate images/video; NBC News testing found it can produce celebrity and regular-person deepfakes that Meta's own detection doesn't always catch. Users were opted in by default (except already-private profiles and some under-18 settings) — opting out takes a manual trip through "sharing and reuse" settings.
   - **Source:** same as #1 (Ars Technica, 2026-07-10) — note this is the secondary story inside the same article; verify it hasn't already been covered elsewhere before scripting.

4. **"Anthropic just poached a Nobel Prize winner and a Berkeley computer science department chair — in the same two weeks."** — Between late June and early July 2026, Anthropic hired four heavyweight researchers in rapid succession: AlphaFold lead and 2024 Nobel Chemistry laureate John Jumper, two Gemini core researchers (Jonas Adler, Alexander Pritzel), and UC Berkeley EECS division chair Jelani Nelson (who's keeping his faculty position on leave-of-absence).
   - **Source:** [Nobel laureate John Jumper is leaving DeepMind for rival Anthropic](https://techcrunch.com/2026/06/20/nobel-laureate-john-jumper-is-leaving-deepmind-for-anthropic/) (TechCrunch, 2026-06-20) + [Anthropic Hires Berkeley CS Chair Jelani Nelson](https://www.techtimes.com/articles/319500/20260702/anthropic-hires-berkeley-cs-chair-jelani-nelson-signaling-new-phase-ai-race.htm) (Tech Times, 2026-07-02)

5. **"Anthropic just admitted it built a Claude model too dangerous to ever ship."** — In its own engineering writeup on how it contains Claude across products, Anthropic reveals that "Claude Mythos Preview" was shelved in April 2026 because its potential blast radius was deemed too high — and separately, that telemetry showed users approve roughly 93% of Claude Code's permission prompts, meaning the human-in-the-loop safety check people rely on barely works because nobody reads it anymore.
   - **Source:** [How we contain Claude across products](https://www.anthropic.com/engineering/how-we-contain-claude) (Anthropic Engineering, 2026)

---

## interesting-tech — 7 Alt-Angle Ideas

The shipped/candidate list for this series is entirely malware and exploits (Stuxnet,
Heartbleed, Rowhammer, Morris Worm, EternalBlue, Log4Shell, Slowloris, Therac-25, logic
bomb). These 7 branch out on purpose — aviation, finance, space hardware, cryptography, and
a detective story with zero malware involved — while keeping the series' actual bar: a real,
concrete, named artifact/incident, fact-checked, that survives the thumbnail.

1. **"Why do Boeing 787s have to be switched off and on every 51 days?"** — A rounding error in a 32-bit timing counter means that after 51 days of continuous power, the plane's common core system stops filtering out stale data — misleading airspeed, altitude, and engine readings can be shown to pilots, and the stall warning horn stops working. The FAA's fix isn't a patch: it's a standing order to reboot the aircraft.
   - **Verified:** [Boeing 787s must be turned off and on every 51 days to prevent 'misleading data' being shown to pilots](https://www.theregister.com/2020/04/02/boeing_787_power_cycle_51_days_stale_data/) (The Register)

2. **"A 75-cent accounting error is how one sysadmin caught a KGB spy hacking US military computers."** — 1986, Lawrence Berkeley Lab: Clifford Stoll was asked to resolve a 75-cent billing discrepancy in the computer usage logs. Instead of writing it off, he traced it to an unauthorized user — and spent the next ten months tracking the intrusion through a modem connection back to a hacker (Markus Hess) who was selling what he found to Soviet intelligence.
   - **Verified:** [The Cuckoo's Egg (book) — Wikipedia](https://en.wikipedia.org/wiki/The_Cuckoo's_Egg_(book))

3. **"Scientists had to rename human genes because Microsoft Excel kept mistaking them for dates."** — Gene symbols like MARCH1 ("Membrane Associated Ring-CH-Type Finger 1") get auto-converted by Excel into "1-Mar" the instant they're typed into a cell. It happened often enough — over a fifth of a 3,597-paper sample had corrupted gene names — that the official naming body (HGNC) renamed 27+ genes (MARCH1 → MARCHF1, WARS → WARS1) specifically to dodge Excel's autoformatting.
   - **Verified:** [Scientists had to rename human genes because Microsoft Excel confuses them as dates](https://variablemag.com/news/excel-confuses-genes-as-dates/) (Variable) + [HGNChelper paper, PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7856679/)

4. **"One line of reused code blew up a rocket 37 seconds after launch."** — Ariane 5's maiden flight in 1996: the guidance software converting a velocity value from 64-bit float to 16-bit integer overflowed, because Ariane 5 flew faster than the Ariane 4 code it was copied from was ever designed to handle. Both the primary and backup navigation computers — running the same unprotected code — shut down within milliseconds of each other, and the flight computer misread the shutdown diagnostics as real flight data, commanding the rocket to tear itself apart.
   - **Verified:** [Ariane flight V88 — Wikipedia](https://en.wikipedia.org/wiki/Ariane_flight_V88)

5. **"Two lines removed from a code audit quietly broke almost every SSH key ever generated on Debian."** — In 2006, tools flagged some "uninitialized memory" lines in Debian's OpenSSL package as a bug and a maintainer removed them — except that memory was the actual source of randomness feeding key generation. For nearly two years, every SSH, SSL, and VPN key generated on Debian or Ubuntu could only take one of 32,767 possible values, discovered in 2008.
   - **Verified:** [Predictable random number generator discovered in the Debian version of OpenSSL — Wikinews](https://en.wikinews.org/wiki/Predictable_random_number_generator_discovered_in_the_Debian_version_of_OpenSSL)

6. **"A trading firm lost $440 million in 45 minutes because nobody deleted some old code."** — Knight Capital reused a deprecated order-type flag from 2003 for a new feature in 2012 — but their deployment script silently failed to update one of ten production servers, and failed *silently*, reporting success anyway. That one leftover server ran the old dead code live, buying and selling with no risk limits, racking up $7 billion in unwanted positions before anyone could shut it down.
   - **Verified:** [Knight Capital Group — Wikipedia](https://en.wikipedia.org/wiki/Knight_Capital_Group)

7. **"A NASA probe 15 billion miles from Earth started sending back gibberish, and the chip that broke was older than the Space Shuttle."** — Late 2023: Voyager 1, launched in 1977, began transmitting corrupted telemetry. NASA traced it to roughly 3% of the Flight Data Subsystem's memory chip going bad — after 46 years of continuous operation — and engineers fixed a spacecraft they can't physically touch by relocating the affected code to different memory, entirely by remote command.
   - **Verified:** [NASA Figured Out Why Its Voyager 1 Probe Has Been Glitching for Months](https://gizmodo.com/nasa-voyager-corrupted-hardware-chip-anomaly-gibberish-1851390354) (Gizmodo)

---

## tech-in-one-breathe — 4 New Ideas

Heads up: the Obsidian vault already has ~17 unproduced "-in-one-breath" ideas queued
(CDN, caching, DNS, Docker, event-driven, gRPC, HTTP, load balancing, microservices, Nginx,
OAuth, rate limiting, Redis, SQL vs NoSQL, TCP vs UDP, WebSockets, APIs) — most of what's
"missing" from this series is really just an existing backlog nobody's scripted yet. These 4
are genuinely new tools not already covered by that backlog or `VIDEO_IDEAS.md`.

1. **"What is WebAssembly and why is it about to make the browser as fast as a native app?"** — Wasm: a sandboxed, near-native-speed bytecode format that lets languages other than JavaScript run in the browser (or outside it) — why Figma, AutoCAD, and Photoshop can now run as web apps.
2. **"Everyone lists vector databases on their resume now but no one explains what they're actually storing."** — Pinecone/Weaviate/pgvector: storing embeddings, not rows, and doing nearest-neighbor search instead of exact match — the thing every RAG pipeline sits on top of.
3. **"What is consistent hashing and why does almost every distributed cache secretly depend on it?"** — how you add or remove a server from a cluster without reshuffling every single key — the trick behind Cassandra, DynamoDB, and memcached client libraries.
4. **"What is a Bloom filter and why do databases check one before they ever touch the disk?"** — a probabilistic "definitely not here" check that lets systems skip an expensive lookup entirely — used inside Cassandra, Postgres, and browsers checking malicious-URL lists.

---

## ai-fundamentals — 5 New Ideas

The series file already has "context windows" and "agents vs. skills vs. commands" queued —
these 5 are deliberately different topics so nothing here steps on those two.

1. **"Everyone says to just 'lower the temperature' but no one explains what it's actually doing to the model."** — temperature/top-p reshape the probability distribution over the next token; it's not a dial for "more accurate," it's a dial for "more predictable."
2. **"Why does shrinking a model to run on your laptop suddenly make it worse at math?"** — quantization: compressing model weights to fewer bits per number trades a little accuracy for a lot less memory — and math/reasoning degrades faster than fluent conversation does.
3. **"Everyone talks about distillation but no one explains how a tiny model learns from a giant one."** — teacher/student training: the small model isn't trained on raw text, it's trained to mimic the big model's output distribution — why a distilled model can punch above its parameter count.
4. **"What actually happens between you asking an AI to 'check the weather' and it giving you an answer?"** — tool use / function calling: the model never runs code — it outputs a structured request, your application executes it, and the result gets fed back in as more text for the model to read.
5. **"Everyone says AI gets dumber the longer your conversation runs, but no one explains why adding more context can make it worse, not better."** — "context rot" / lost-in-the-middle: distinct from the 101 "what is a context window" explainer already queued — this is the practical symptom devs hit today (stuffing more docs in doesn't help, and can actively hurt retrieval of the one fact that matters).

---

*updates and interesting-tech above are fact-checked against real sources (linked inline).
tech-in-one-breathe and ai-fundamentals have no source DB by design (per their series
files) — these are concept picks, not news, so no citation is expected the way tbbt/updates
require one.*
