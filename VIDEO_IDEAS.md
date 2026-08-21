# Video Ideas — 10 per Series

Generated against each series' proven hook pattern and the channel's real top-performers
(see `series/*.md` and `.claude/voice/proven-hooks.md`). Each idea is a **hook** (in the
series' winning template) plus the **angle** it has to deliver. Dedup against
`VIDEO_IDEAS_BACKLOG.md` and `assets/*/script.md` before producing.

Reference winners this is modelled on:
- `interesting-tech` — "What is 42.zip and why was it so dangerous?" (101k views, 5038 eng)
- `ai-fundamentals` — "Everyone tells you to use Claude but no one explains how the token limits actually work." (122k views, #1 channel-wide)
- `tbbt` — "So Netflix literally ships free servers to ISPs around the world." (36k views)
- `updates` — "GitHub just raised the price of Copilot by 900%." (92k views)

---

## tbbt — Tech Behind Big Tech
*Pattern: named tech/company first → shocking number, counter-intuitive reframe, or "So [Company] literally [absurd action]." Audience is engineers — surprise them, don't 101 them. Every idea below is backed by a source article that carries the full story.*

1. **"So Discord moved a trillion messages off Cassandra and onto a database that needed less than half the servers."** — the ScyllaDB migration: Rust data-services layer, the Rust migrator that cut a 3-month job to 9 days, 177 → 72 nodes, p99 reads from 40–125ms to 15ms.
   - **Source:** [How Discord Stores Trillions of Messages](https://discord.com/blog/how-discord-stores-trillions-of-messages) (official Discord blog)
3. **"So Google buried atomic clocks in its data centers just to keep one database in sync."** — Spanner's TrueTime: GPS + atomic-clock time masters, the uncertainty interval, and how bounded clock error gives global consistency.
   - **Source:** [Spanner: Google's Globally-Distributed Database](https://research.google/pubs/spanner-googles-globally-distributed-database/) (OSDI 2012 paper)
5. **"So Netflix pays its own engineers to randomly kill its servers in production, on purpose."** — Chaos Monkey and the Simian Army, why deliberately terminating instances during business hours is how they stay up. *(counter-intuitive reframe)*
   - **Source:** [The Netflix Simian Army](https://netflixtechblog.com/the-netflix-simian-army-16e57fbab116) (Netflix Tech Blog)
6. **"WhatsApp served 900 million people with an engineering team you could fit in one room."** — how Erlang's lightweight processes (2M+ connections per server), Mnesia, and FreeBSD let ~50 engineers hold that load.
   - **Source:** [The WhatsApp Architecture Facebook Bought For $19 Billion](https://highscalability.com/the-whatsapp-architecture-facebook-bought-for-19-billion/) (High Scalability, from Rick Reed's Erlang Factory talk)
7. **"So Cloudflare answers every request on earth from the closest machine using a single IP address."** — anycast routing: many data centers announcing the same IP, BGP steering you to the nearest, and why it also absorbs DDoS.
   - **Source:** [A Brief Primer on Anycast](https://blog.cloudflare.com/a-brief-anycast-primer/) (Cloudflare blog)
8. **"Stripe makes sure you never get charged twice even if your connection dies mid-payment."** — idempotency keys: the client-generated key, server-side dedup, saving the first response so retries return the same result.
   - **Source:** [Designing robust and predictable APIs with idempotency](https://stripe.com/blog/idempotency) (Stripe blog)
9. **"Figma lets a hundred people edit the same file at once without a single change getting lost."** — the multiplayer engine: a custom server-authoritative system inspired by CRDTs (not full OT), WebSockets, offline edits reapplied on reconnect.
   - **Source:** [How Figma's multiplayer technology works](https://www.figma.com/blog/how-figmas-multiplayer-technology-works/) (Figma blog)
10. **"So Shopify keeps one crashing store from taking down the millions of others by sealing each into its own pod."** — pods architecture: sharded isolated datastores, the "Sorting Hat" router, and Pod Mover relocating a pod between data centers in under a minute.
   - **Source:** [A Pods Architecture To Allow Shopify To Scale](https://shopify.engineering/a-pods-architecture-to-allow-shopify-to-scale) (Shopify Engineering)

---

## updates — Tech & AI Updates
*Pattern: "[Company/person] just [did X]." The action is the surprise — short, quirky, under 12 words. Timeliness is the whole value, so each idea is pinned to a dated source. **Re-check freshness at produce time** — an "update" decays fast.*

*Note: 5 of the original 10 were deleted for failing the source test — see the deletion log at the bottom of this section.*

1. **"Cloudflare just made blocking AI crawlers the default for the whole internet."** — Content Independence Day: from Sept 15 2026 Cloudflare blocks mixed-use AI crawlers on ad-supported pages by default, plus pay-per-crawl. *(freshest — July 2026)*
   - **Source:** [Content Independence Day: no AI crawl without compensation!](https://blog.cloudflare.com/content-independence-day-no-ai-crawl-without-compensation/) + [TechCrunch, 2026-07-01](https://techcrunch.com/2026/07/01/cloudflares-new-policy-pushes-ai-companies-to-pay-for-publishers-content/)
2. **"Google just made AI the default for every search on earth."** — I/O 2026: AI Mode becomes the global default over blue links, Gemini 3.5 Flash under it, ~93% zero-click rate, 1B monthly users.
   - **Source:** [Google Search's I/O 2026 updates](https://blog.google/products-and-platforms/products/search/search-io-2026/) + [TechCrunch: "Google Search as you know it is over", 2026-05-19](https://techcrunch.com/2026/05/19/google-search-as-you-know-it-is-over/)
3. **"OpenAI's Codex just coded for 25 hours straight without a human touching it."** — long-horizon agents: one run, ~25 hours, ~13M tokens, ~30k lines of code, and what "autonomy" actually buys.
   - **Source:** [Run long horizon tasks with Codex](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex) (OpenAI Developers)
4. **"Anthropic just proved you can poison any AI with just 250 documents."** — the backdoor study: 250 malicious docs backdoor models from 600M to 13B params regardless of size, killing the "attackers need a % of the data" assumption. *(Oct 2025 — verify it still reads as "recent," or move to `interesting-tech`)*
   - **Source:** [A small number of samples can poison LLMs of any size](https://www.anthropic.com/research/small-samples-poison) (Anthropic research, w/ UK AISI + Alan Turing Institute)
5. **"Nvidia just became the first company on earth worth 5 trillion dollars."** — the milestone and why the entire AI boom funnels through one GPU line. *(weakest recency — it's been #1 for a year; lead on the fresh $5T print or cut)*
   - **Source:** [Nvidia becomes first company to hit $4 trillion valuation](https://www.nbcnews.com/business/business-news/nvidia-becomes-first-company-worth-4-trillion-what-to-know-rcna217721) (NBC) + [live market cap](https://companiesmarketcap.com/nvidia/marketcap/)

**Deletion log (failed the source test):**
- ~~"GitHub just let Copilot open and merge its own pull requests."~~ — **contradicted by source.** Copilot's coding agent opens PRs but a human always merges ("Copilot not Autopilot"). The merge claim is false.
- ~~"Microsoft just shipped an AI that screenshots your PC every few seconds." (Recall)~~ — **stale.** 2024/2025 feature, no recent article to make it an "update."
- ~~"Anthropic just gave Claude control of your actual computer." (computer use)~~ — **stale.** Shipped Oct 2024; no fresh peg.
- ~~"Meta just gave away its most powerful AI model for free."~~ — **no anchoring event.** Ongoing open-weights strategy, no specific recent article with the full story.
- ~~"Someone just got an AI to run an entire open source project with millions of users."~~ — **no single source.** Only generic 2026 agent roundups exist; nothing that carries a concrete, video-ready story.

---

## tech-in-one-breathe — Tech in One Breath
*Pattern: "What is X and why is it everywhere?" or "Everyone lists X on their resume but no one can explain what it does." Lead with the real tool name — recognition is the hook. Under 120 words, 60 seconds.*

1. **"What is Redis and why is it hiding behind almost every fast app you use?"** — in-memory store, caching, why it makes things feel instant.
2. **"What is Nginx and why is it sitting in front of half the internet?"** — reverse proxy / load balancer, the thing between you and the actual server.
3. **"Everyone lists Docker on their resume but no one can explain what a container actually is."** — "works on my machine" solved, images vs. VMs.
4. **"What is Kafka and why is it in every architecture diagram you've ever seen?"** — the log / event stream that decouples everything. *(named example from the series file)*
5. **"What is Postgres and why do senior engineers keep saying 'just use Postgres'?"** — the boring database that quietly does everything.
6. **"What is gRPC and why did big companies quietly ditch REST for it?"** — binary protocol, why service-to-service calls moved off JSON.
7. **"What is a message queue and why is one running inside almost every app you touch?"** — RabbitMQ / SQS, work you don't want to do on the request.
8. **"What is Elasticsearch and why is it powering every search bar you've ever typed into?"** — inverted index, search vs. a database `LIKE`.
9. **"Everyone lists Terraform on their resume but no one explains what 'infrastructure as code' means."** — describing servers in a file instead of clicking.
10. **"What is a service mesh and why did it suddenly appear in every diagram?"** — Envoy / sidecars, moving networking logic out of your app.

---

## interesting-tech — Interesting Tech
*Pattern: "What is X and why was it so dangerous?" Name the impossible-sounding artifact, withhold the explanation. The hook has to survive the thumbnail — a concrete exploit/bug/file, never an abstract concept.*

1. **"What is Stuxnet and how did a piece of code physically destroy a nuclear facility?"** — the worm that jumped an air gap and spun centrifuges apart.
2. **"What is Heartbleed and why did it quietly leak the secrets of half the internet?"** — one missing bounds check in OpenSSL, and how it bled memory.
3. **"What is Rowhammer and how does hammering memory let you break into a computer you don't own?"** — flipping bits in a neighbouring row with pure physics.
4. **"What is the Morris Worm and how did one grad student accidentally take down the early internet?"** — the first worm, and the bug that made it spread out of control.
5. **"What is EternalBlue and how did a leaked NSA tool cause billions in damage?"** — the exploit behind WannaCry, and why unpatched machines fell instantly.
6. **"What is Log4Shell and why did the entire internet scramble to patch it overnight?"** — a logging line that let a string run code on your server.
7. **"What is Slowloris and how did it take down web servers using almost no bandwidth?"** — holding connections open forever until nothing else can connect.
8. **"What is the Therac-25 and how did a software bug end up killing people?"** — a race condition in a radiation machine, and the missing hardware interlock.
10. **"What is a logic bomb and why could one already be sitting in the code you run?"** — malicious code that waits for a date or a trigger before it detonates.

---

## ai-fundamentals — AI Fundamentals
*Pattern: Hidden Knowledge ("Everyone tells you to X but no one explains Y") or a practical-confusion question devs hit daily. Register can go casual/native — that's what drove the #1 video. Comment-bait CTA fits the practical ones.*

1. **"Everyone tells you to give the AI more context but no one explains why it suddenly gets worse."** — context windows and "lost in the middle": more isn't free.
2. **"Everyone talks about tokens but no one explains why the AI can't count the letters in 'strawberry'."** — tokenization, and why the model never sees letters.
3. **"Everyone tells you to cache your prompts but no one explains how it quietly halves your bill."** — prompt caching: what gets reused and what doesn't.
4. **"Why does AI confidently make things up, and why can it never fully stop?"** — hallucination as a property of next-token prediction, not a bug to be patched.
5. **"What is an embedding and why is it the whole reason AI can 'understand' meaning?"** — turning words into coordinates, and why similar things end up close together.
6. **"Everyone says 'just use RAG' but no one explains what it actually does to your data."** — retrieval, chunking, and why it's search bolted onto a model.
7. **"Everyone throws around 'AI agent' but no one explains what makes it different from a chatbot."** — the loop: tools, observations, and deciding the next step.
8. **"Why do the biggest AI models only use a fraction of their brain for each answer?"** — mixture-of-experts, and how sparsity makes huge models cheap to run.
9. **"Everyone tells you to fine-tune your model but no one explains why you probably shouldn't."** — fine-tuning vs. prompting vs. RAG, and when each is the wrong tool.
10. **"Everyone says reasoning models are smarter but no one explains what 'thinking' actually does."** — chain-of-thought / inference-time compute, and what those hidden tokens buy.

---

*45 ideas (tbbt + updates are now source-backed; 5 updates topics were deleted for failing
the source test). The other three series are unverified idea pools — vet before scripting.
Run each through `/produce-script` with the series slug so it inherits the right voice,
length, and CTA.*
