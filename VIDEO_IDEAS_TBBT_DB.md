# tbbt DB shortlist — 2026-09-25

Top 15 articles left in `scrape/db/influencer.db` (`tbbt` table) after the 2026-09-25 cull,
which removed 1,351 marketing, announcement, research-paper and changelog rows. Ranked on
title alone. **None of these has been scraped or verified yet**, so each needs
`scrape/single_scrape.py` and a mechanism check before `/produce-script`.

All 15 were checked against every `*VIDEO_IDEA*.md` bank and `series/*.md`; none is already
queued. Excluded because an idea already exists: OpenAI goblins (`series/updates.md`),
Datadog prefix trie (`VIDEO_IDEAS_2026-08-20.md`), OpenAI ARC-AGI-3 settings and Atlassian
Kinesis→Kafka (`VIDEO_IDEAS_2026-07-30.md`), OpenAI/Hugging Face eval incident
(`VIDEO_IDEAS_2026-08-25.md` exclusion list).

## tbbt — Tech Behind Big Tech (15)

1. **OpenAI: Core dump epidemiology — fixing an 18-year-old bug**
   An 18-year-old bug makes the hook, and "epidemiology" suggests a clever way they tracked it down.
   - **Source:** [Core dump epidemiology: fixing an 18-year-old bug](https://openai.com/index/core-dump-epidemiology-data-infrastructure-bug) (OpenAI, 2026-06-30)

2. **Datadog: When upserts don't update but still write**
   A Postgres behaviour people wouldn't expect, found while debugging performance at scale.
   - **Source:** [When upserts don't update but still write: Debugging Postgres performance at scale](https://www.datadoghq.com/blog/engineering/debugging-postgres-performance/) (Datadog, 2026-03-23)

3. **Cloudflare: The .de TLD DNSSEC outage**
   A whole country's domains broke. Pairs with .AL's broken rollover for a "happened twice" angle.
   - **Source:** [When DNSSEC goes wrong: how we responded to the .de TLD outage](https://blog.cloudflare.com/de-tld-outage-dnssec/) (Cloudflare, 2026-05-06)
   - **Source:** [A broken DNSSEC rollover took down .AL](https://blog.cloudflare.com/dnssec-nta-ede-33/) (Cloudflare, 2026-07-14)

4. **Meta: Ultra-narrow batteries for AI glasses**
   A physical hardware limit, which is rare for tbbt and good for visuals.
   - **Source:** [How Meta Engineered Ultra-Narrow Batteries for AI Glasses](https://engineering.fb.com/2026/06/23/production-engineering/how-meta-built-ultra-narrow-batteries-for-ai-glasses-meta-tech-podcast/) (Meta, 2026-06-23)

5. **Anthropic: Eval awareness in Opus 4.6's BrowseComp performance**
   The model realised it was being tested, which is a strong hook.
   - **Source:** [Eval awareness in Claude Opus 4.6's BrowseComp performance](https://www.anthropic.com/engineering/eval-awareness-browsecomp) (Anthropic, 2026-03-06)

6. **Cloudflare: Remote Spectre attacks on Workers, revisited**
   A CPU side-channel attack against thousands of customers sharing one machine.
   - **Source:** [A revisit of remote Spectre attacks on Cloudflare Workers](https://blog.cloudflare.com/revisiting-spectre-attacks-on-workers/) (Cloudflare, 2026-08-19)

7. **Airbnb: How we knew COVID was over**
   Models trained on pandemic behaviour that then had to unlearn it; easy for anyone to follow.
   - **Source:** [How we knew COVID was over (and what our models had to unlearn)](https://medium.com/airbnb-engineering/how-we-knew-covid-was-over-and-what-our-models-had-to-unlearn-c606b9bdb0ab) (Airbnb, 2026-08-19)

8. **Cloudflare: A bug in the hyper HTTP library**
   A detective story in a library that half the Rust ecosystem uses.
   - **Source:** [How we found a bug in the hyper HTTP library](https://blog.cloudflare.com/hyper-bug/) (Cloudflare, 2026-06-22)

9. **Reddit: Whack-a-mole with slow machines**
   Tracking down slow individual machines in a big fleet, a relatable kind of incident.
   - **Source:** [Whack-A-Mole with slow machines](https://www.reddit.com/r/RedditEng/comments/1rvl0vy/whackamole_with_slow_machines/) (Reddit, 2026-03-16)

10. **Apple: One neuron is enough to bypass safety alignment**
    A striking claim with a clear mechanism; could also fit ai-fundamentals.
    - **Source:** [A Single Neuron Is Sufficient to Bypass Safety Alignment in Large Language Models](https://machinelearning.apple.com/research/single-neuron-safety-alignment) (Apple, 2026-07-07)

11. **GitHub: Better tools made Copilot code review worse**
    A result that runs against intuition.
    - **Source:** [Better tools made Copilot code review worse. Here's how we actually improved it.](https://github.blog/ai-and-ml/github-copilot/better-tools-made-copilot-code-review-worse-heres-how-we-actually-improved-it/) (GitHub, 2026-07-10)

12. **Datadog: Agent Go binaries up to 77% smaller**
    A concrete number, and Go binary bloat is something developers recognise.
    - **Source:** [How we reduced the size of our Agent Go binaries by up to 77%](https://www.datadoghq.com/blog/engineering/agent-go-binaries/) (Datadog, 2026-02-18)

13. **OpenAI: Responding to the TanStack npm supply chain attack**
    A supply-chain attack on a popular package, told from the victim's side.
    - **Source:** [Our response to the TanStack npm supply chain attack](https://openai.com/index/our-response-to-the-tanstack-npm-supply-chain-attack) (OpenAI, 2026-05-13)

14. **bitdrift on AWS: 121 million concurrent gRPC connections**
    A shocking scale number from live sporting events.
    - **Source:** [How bitdrift scaled to 121 million concurrent gRPC connections on Amazon CloudFront](https://aws.amazon.com/blogs/architecture/how-bitdrift-scaled-to-121-million-concurrent-grpc-connections-on-amazon-cloudfront-for-live-telemetry-sporting-events/) (AWS, 2026-07-15)

15. **Airbnb: When history fails you, borrow from geography**
    Forecasting with no history by borrowing from nearby places.
    - **Source:** [When history fails you, borrow from geography](https://medium.com/airbnb-engineering/when-history-fails-you-borrow-from-geography-915a72b91b5c) (Airbnb, 2026-06-02)
