# Video Ideas — Backlog

The standing backlog of unproduced video ideas, 115 entries. Unlike the dated `VIDEO_IDEAS_<date>.md` banks this is not a proposal run — most entries have no source URL, and none carry a series. `/produce-script` resolves an entry from here the same way it resolves any root idea bank; `/video-ideas` dedups against it.

## 1. The 404 Page that Saves Lives

**The most useful 404 page in the world.**

- EU: many websites use 404 pages to display photos of missing children
- Instead of dead end, use "NotFound" API
- Turn wasted traffic into search party
- _slug:_ `404-missing-children`  _created:_ 18-03-2026

## 2. Emotions Anthropic Article


_Reference_

- [Anthropic Emotions Article](https://transformer-circuits.pub/2026/emotions/index.html)
- _slug:_ `Emotions Anthropic Article`  _created:_ 06-04-2026

## 3. Google Spanner and Gmail Account Changes

- Google Spanner — Google's globally distributed relational database
- Video angle: how Spanner powers something as user-facing as Gmail account name/email changes
- Gmail now lets you change your account name/email — trace the distributed systems challenge behind this
- Key topics: distributed transactions, TrueTime, external consistency, schema migrations at scale

_Reference_

- Google, Gmail, Google Spanner, distributed databases, cloud infrastructure
- _slug:_ `Google Spanner and Gmail Account Changes`  _created:_ 04-04-2026

## 4. Pretext software

- Amazing no one has done this in ~10 years
- Pretext — reference https://youtu.be/vd14EElCRvs

_Reference_

- **Source:** https://youtu.be/vd14EElCRvs
- _slug:_ `Pretext software`  _created:_ 09-04-2026

## 5. The "Un-hackable" Air-Gapped PC

**How to hack a computer that isn't even connected to the internet.**

- Intelligence agencies use "Air-Gapping" (no Wi-Fi, no cables)
- Researchers figured out counter-hack
- Listen to fan noise of PC
- Heat it gives off
- Translate fluctuations back into binary
- Extract data
- _slug:_ `air-gapped-hacking`  _created:_ 18-03-2026

## 6. Airbnb's Search Stack

**Why Airbnb built their own ranking with Elasticsearch, Kafka, and ML models to match 7 million listings to your exact travel vibe.**

- Custom ranking system
- Elasticsearch, Kafka
- ML models
- 7 million listings
- Personalized search at scale
- _slug:_ `airbnb-search-stack`  _created:_ 18-03-2026

## 7. Why Amazon Destroys Millions of Unsold Products

**The dark side of 'Prime' shipping.**

- Cheaper for Amazon to destroy laptop than ship back or store
- Storage fees for 3rd party sellers so high
- "Liquidation through Destruction" is most "efficient" algorithm
- _slug:_ `amazon-destroys-products`  _created:_ 18-03-2026

## 8. How Amazon Uses Robots to Redesign Warehouses Around Algorithms

**When software dictates physical architecture.**

- Robots and algorithms reshape warehouse
- Software drives physical design
- Warehouse layout changes based on algorithms
- _slug:_ `amazon-robots-redesign-warehouses`  _created:_ 18-03-2026

## 9. APIs Explained in One Breath

**An API is a contract — it defines exactly how two pieces of software can talk to each other.**

- API = Application Programming Interface
- A menu at a restaurant: you don't go into the kitchen, you just order from the menu
- The kitchen (server) does the work, gives you back exactly what the menu promised
- REST API: uses HTTP methods (GET, POST, PUT, DELETE) over URLs
- GET /users/123 → returns user 123's data. POST /users → creates a new user.
- Responses in JSON — readable by both humans and machines
- API key: your identity card for using someone else's API
- Rate limits stop you from making too many requests
- Public APIs (Stripe, Twilio, Google Maps) are entire businesses — you pay per call
- Every app you use talks to dozens of APIs you never see
- _slug:_ `apis-in-one-breath`  _created:_ 24-03-2026

## 10. Why Apple Secretly Built a Global CDN

**Apple controls software delivery end-to-end.**

- Apple built global CDN secretly
- Control entire software delivery pipeline
- End-to-end ownership
- _slug:_ `apple-global-cdn`  _created:_ 18-03-2026

## 11. [x] Create Atomic Habits takeaways, focused on the goals framing.

- _slug:_ `atomic habits goals`  _created:_ '2026-03-14'

## 12. Authentication vs Authorization Explained

**Authentication asks "who are you?" Authorization asks "what are you allowed to do?" They sound similar. They're completely different problems.**

- Authentication (AuthN): proving your identity — login with password, Google SSO, biometrics
- Authorization (AuthZ): what you're permitted to access after you've proven who you are
- Example: you authenticate to your company's system with your password
- Authorization then decides: can you access the HR dashboard? The production database? Other users' data?
- You can be authenticated but not authorized (logged in, but can't access that page — 403 Forbidden)
- You can have authorization without authentication (public read access to a repo)
- Common authZ patterns: RBAC (Role-Based Access Control), ABAC (Attribute-Based), ACLs
- JWT handles authN. OAuth handles authZ. OpenID Connect layers authN on top of OAuth.
- Getting these confused is how security vulnerabilities happen
- _slug:_ `auth-vs-authz`  _created:_ 24-03-2026

## 13. Read a book → video on 3 key takeaways + explain why the book is so popular/valuable.

- _slug:_ `book takeaways`  _created:_ '2026-03-14'

## 14. Position intro video as a "breaking into big tech" guide.

- Look at quant_kyle for reference/positioning
- _slug:_ `breaking into big tech`  _created:_ '2026-03-14'

## 15. Caching Explained in One Breath

**Caching saves expensive results so future requests are faster.**

- Compute something once, store the result, serve it instantly next time
- Exists at every layer: CPU cache, browser cache, CDN cache, application cache, database cache
- Cache hit: result found, served instantly. Cache miss: had to go compute it.
- Cache eviction: when the cache is full, old items are removed (LRU = Least Recently Used)
- TTL (Time To Live): how long a cached item is valid before it expires
- The hard problem: cache invalidation — knowing when cached data is stale
- "There are only two hard things in CS: cache invalidation and naming things" — Phil Karlton
- Over-caching: users see outdated data. Under-caching: your database gets hammered.
- Redis and Memcached are the most common application-level caches
- _slug:_ `caching-in-one-breath`  _created:_ 24-03-2026

## 16. CDNs Explained in One Breath

**CDNs cache content close to users so pages load faster and origin servers get less traffic.**

- Your server might be in Virginia. A user in Tokyo gets slow responses — speed of light is real.
- CDN: a network of servers spread across the world (edge nodes)
- Static content (images, JS, CSS, video) gets copied to edge nodes near users
- User in Tokyo gets served from the CDN node in Tokyo, not Virginia
- Cache hit: served from edge instantly. Cache miss: edge fetches from origin, caches it for next time.
- CDNs also absorb DDoS attacks — Cloudflare can absorb multi-terabit attacks
- GitHub's 1.35 Tbps DDoS was mitigated by Akamai's CDN
- Major CDNs: Cloudflare, Akamai, Fastly, AWS CloudFront
- Not just for static assets — modern CDNs run code at the edge (Cloudflare Workers)
- _slug:_ `cdns-in-one-breath`  _created:_ 24-03-2026

## 17. How I use Claude Code to create videos — end-to-end workflow demo.


_Related angles_

- 3 things that levelled up my use of Claude Code
- Claude Code top 3 tips

_Tips to cover_

- Switching models invalidates cache (everything reloads into context)
- Ask Claude to ask clarifying questions if something doesn't make sense or contradicts
- Use the status bar (comment for status bar script)
- _slug:_ `claude code workflow`  _created:_ '2026-03-14'

## 18. **SCRIPT**

- Everyone says AI can build your app but no one explains how Claude Code actually clicks through the UI to verify it works.
- So you ask Claude to build a macOS menu bar app. It writes the Swift, compiles it, launches it. And then — this is the part people skip over — it clicks every button, checks every control, and screenshots any errors. No Xcode. No manual testing. You just watch.
- That's Claude Code's new computer use feature. And it's not magic, it's a deliberate fallback chain.
- When you trigger it from the terminal via /mcp, Claude figures out what tool it needs. It tries MCP servers first, then Bash commands, then browser automation. Screen control is the last resort — only when nothing else works.
- The clever part is the safety model. Before Claude touches any app, it asks your permission, per app, per session. Only one terminal session can control your screen at a time. The terminal itself is excluded from screenshots so Claude can't read its own context. And if anything feels off, one press of Escape kills it globally, from anywhere on your machine.
- So next time you're building something with a UI, you don't have to manually click through every state to check it. Claude does that loop for you.
**REFERENCES:**
- **Source:** https://code.claude.com/docs/en/computer-use
- **Source:** https://www.reddit.com/r/ClaudeCode/comments/1s7wl6s/computer_use_is_now_in_claude_code/
- _slug:_ `claude-code-computer-use`

## 19. Cloudflare vs. The Leap Second

**How one extra second almost broke the entire internet.**

- 2012 and 2017: "Leap Seconds" added to atomic clocks
- Keep up with Earth's rotation
- Many Linux kernels and databases couldn't handle clock "repeating" second
- CPU spikes took down Reddit, Gawker, Cloudflare
- Google and Amazon now use "Leap Smearing"
- Slowly add milliseconds throughout day
- Servers never notice the jump
- _slug:_ `cloudflare-leap-second`  _created:_ 18-03-2026

## 20. The "Boring" Language Running the Banks

**The 65-year-old coding language that still controls your bank account.**

- 80% of in-person banking transactions
- 95% of ATM swipes run on COBOL
- 220+ billion lines of COBOL in production
- Every time bank tries to replace it, too complex
- Usually give up and hire 80-year-old consultants to fix it
- _slug:_ `cobol-banking`  _created:_ 18-03-2026

## 21. The cold start problem for recommendation systems in big tech.

- Not about lambdas
- _slug:_ `cold start problem`  _created:_ '2026-03-14'

## 22. Explainer on common tech buzzwords — Firebase, real-time, etc.

- _slug:_ `common tech buzzwords`  _created:_ '2026-03-14'

## 23. The "Silent" Data Corruption

**The invisible cosmic rays flipping bits in your phone right now.**

- High-energy particles from space hit transistor
- Flip a 0 to a 1
- "ECC RAM" (Error Correction Code) exists because of this
- 2003: Belgian election, candidate got 4,096 extra votes
- Single cosmic ray bit-flip
- _slug:_ `cosmic-ray-bit-flip`  _created:_ 18-03-2026

## 24. The "Delete" Button that Costs Millions

**Why Big Tech hates it when you click 'Delete'.**

- When you delete file on S3 or Google Drive, not "gone"
- Deleting trillions of objects creates "Tombstones" (markers)
- Actually slows down databases
- Companies run "Compaction" jobs
- Massive background processes
- Millions in electricity just to actually remove data you already deleted
- _slug:_ `delete-button-costs-millions`  _created:_ 18-03-2026

## 25. Discord's "Garbage" Problem

**How Discord saved your chat history by deleting their database.**

- Discord used MongoDB
- MongoDB stores data creating "garbage" (unused memory)
- Every few minutes system would freeze to clean up garbage
- Migrated billions of messages to ScyllaDB (C++ rewrite of Cassandra)
- ScyllaDB doesn't pause for garbage collection
- Stop trying to optimize wrong tool
- Just change the tool
- _slug:_ `discord-garbage-collection-problem`  _created:_ 18-03-2026

## 26. Discord's Low-Latency Architecture

**How Discord uses Elixir, Rust, and ScyllaDB to handle 15 million concurrent voice users without lag.**

- Elixir, Rust, ScyllaDB
- 15 million concurrent voice users
- Low-latency real-time voice
- Voice at massive scale
- _slug:_ `discord-low-latency-architecture`  _created:_ 18-03-2026

## 27. DNS in One Breath

**DNS explained in one breath.**

- Every time you type a URL, your computer has no idea where to go
- The internet only understands numbers, not names
- "google.com" gets translated to something like 142.250.80.46
- DNS is the internet's phone book
- Request goes to a DNS resolver (usually run by ISP)
- Resolver asks a chain of other servers, each one pointing closer
- Last server owns the record and hands back the number
- Browser connects
- Whole lookup takes ~11 milliseconds
- Answer gets cached for next time (short-term memory)

_Reference_

- **Source:** https://www.cloudflare.com/learning/dns/what-is-dns/
- **Source:** https://www.cloudflare.com/application-services/products/dns/
- **Source:** https://www.icann.org/root-server-system-en
- _slug:_ `dns-in-one-breath`  _created:_ 18-03-2026

## 28. Docker Down vs Docker Stop

**`docker-compose down` isn't just stopping your containers—it's deleting them.**

- Most developers use these commands interchangeably — big mistake
- One pauses your work, the other nukes it
- If not careful, your local database vanishes
- `docker stop` sends shutdown signal to containers
- Containers stop running but stay on disk
- All data, configs, state preserved
- `docker-compose down` stops containers then removes them entirely
- Networks gone
- With `-v` flag, volumes disappear too
- Local Postgres you've been testing with? Wiped.
- Stop pauses, Down destroys

_Reference_

- **Source:** https://docs.docker.com/reference/cli/docker/compose/down/
- **Source:** https://www.geeksforgeeks.org/devops/docker-compose-up-down-stop-start-difference/
- **Source:** https://medium.com/@laurap_85411/docker-compose-stop-vs-down-e4e8d6515a85
- _slug:_ `docker-down-vs-stop`  _created:_ 18-03-2026

## 29. Docker Explained in One Breath

**Docker packages your app and its dependencies into a container so it runs the same everywhere.**

- "Works on my machine" — Docker makes that phrase extinct
- Container = your app + runtime + libraries + config, all bundled together
- Not a virtual machine — shares the host OS kernel, so it's much lighter
- Dockerfile: a recipe for building your container image
- Image: the blueprint. Container: a running instance of that image.
- Run 10 containers from the same image — each isolated from the others
- Docker Hub: public registry of pre-built images (nginx, postgres, redis, etc.)
- Compose: run multiple containers together with one command
- Why it matters: dev, staging, and prod all run identical environments — no more "it works on my machine"
- Kubernetes takes this further: orchestrates thousands of containers across many machines
- _slug:_ `docker-in-one-breath`  _created:_ 24-03-2026

## 30. DoorDash's DeepRed ML System

**ML-powered dispatch making millions of delivery decisions daily.**

- DeepRed ML system
- Delivery dispatch
- Millions of decisions daily
- Machine learning at scale
- _slug:_ `doordash-deepred-ml`  _created:_ 18-03-2026

## 31. Why Dropbox Left the Cloud (And Saved Millions)

**The "Magic Pocket" infrastructure migration.**

- Magic Pocket infrastructure
- Dropbox left cloud
- Built own storage infrastructure
- Saved millions
- _slug:_ `dropbox-magic-pocket`  _created:_ 18-03-2026

## 32. Create videos based on top questions/threads from r/explainlikeimfive.

- _slug:_ `eli5 videos`  _created:_ '2026-03-14'

## 33. Event-Driven Architecture Explained in One Breath

**Instead of calling services directly, systems emit events and react to them asynchronously.**

- Traditional: Service A calls Service B directly. B must be up and respond immediately.
- Problem: if B is slow or down, A is stuck. They're coupled.
- Event-driven: A emits an event ("order placed") to a message bus. B, C, D all listen and react independently.
- A doesn't know or care who's listening — loose coupling
- Events are immutable facts: "this happened" — not commands, not questions
- Kafka is the dominant event streaming platform for this pattern
- Benefits: services can be added/removed without changing producers, natural audit log, replay events to rebuild state
- Costs: harder to trace what happened (distributed tracing needed), eventual consistency, more infrastructure
- Used by: Uber (all ride events), Netflix (stream processing), LinkedIn (activity feeds)
- _slug:_ `event-driven-in-one-breath`  _created:_ 24-03-2026

## 34. The Excel Mistake That Cost Billions

**The most dangerous database in the world is... Microsoft Excel.**

- 2020: UK's COVID tracking system lost 16,000 cases
- Tracked cases using Excel file (XLS)
- Old file format had hard limit of 65,000 rows
- Hit row 65,001, data vanished
- Scalability isn't just about servers
- It's about file formats
- _slug:_ `excel-mistake-covid-cases`  _created:_ 18-03-2026

## 35. gemma 4

- Gemma 4 — new model from Google

_Reference_

- **Source:** https://www.instagram.com/reel/DWsixc9CWFB/?igsh=MTVwejZpeGNmcnR4bg==
- _slug:_ `gemma-4`  _created:_ 05-04-2026

## 36. Git Worktrees vs Git Branches

**Git branches vs git worktrees — in one breath.**

- Git branches: you make changes on a branch and merge back to main
- Fine when it's just you
- Problem: running multiple AI coding agents in parallel
- Would have to clone entire repo once per agent
- Three separate copies on your machine
- Worktrees fix this
- Each worktree on its own branch
- Git enforces this
- Each agent works in isolation on its own branch
- All share same underlying git history with no duplication
- Branches are for tracking history
- Worktrees are for running agents in parallel without cloning the world

_Reference_

- **Source:** https://git-scm.com/docs/git-worktree
- _slug:_ `git-worktrees-vs-branches`  _created:_ 18-03-2026

## 37. GitHub's 1,200 MySQL Hosts at 5.5M QPS

**Zero-downtime upgrades across massive MySQL infrastructure.**

- 1,200 MySQL hosts
- 5.5 million queries per second
- Zero-downtime upgrades
- Database scaling at massive scale
- _slug:_ `github-1200-mysql-hosts`  _created:_ 18-03-2026

## 38. The Github Arctic Vault

**Your bad code is currently buried 250 meters inside an Arctic mountain.**

- 2020: GitHub took snapshot of all active public repositories
- Printed code onto silver-halide film (lasts 1,000 years)
- Locked in decommissioned coal mine in Svalbard, Norway
- Next to Global Seed Vault
- In the apocalypse, aliens will find pyramids and your unfinished To-Do app
- _slug:_ `github-arctic-vault`  _created:_ 18-03-2026

## 39. How GitHub Survived the Largest DDoS Attack in History

**What happened during the 1.35 Tbps attack.**

- Largest DDoS attack in history
- 1.35 Tbps
- GitHub survived
- DDoS mitigation infrastructure
- _slug:_ `github-ddos-attack`  _created:_ 18-03-2026

## 40. Why Google's Data Center Network Had to Grow 7x in 5 Years

**Hook:** "AI isn't just a GPU problem. It's a networking problem — and Google had to rewire their entire data center to solve it."
- Most people think AI scaling = more GPUs. Real bottleneck is moving data between 100,000+ GPUs fast enough
- Jupiter fabric now hits 13 Petabits/second — more bandwidth than most countries' entire internet
- WAN bandwidth grew 7x from 2020–2025
- Switched from vertical to horizontal multi-shard scaling → 50x greater reliability
- Open loop: "If your GPUs can't talk to each other fast enough, training grinds to a halt — so how do you wire 100,000 of them?"

_Reference_

- **Source:** https://cloud.google.com/blog/products/networking/google-global-network-principles-and-innovations
- _slug:_ `google datacenter network`  _created:_ 18-03-2026

## 41. Deep dive into Google's monorepo approach — how it works and why they use it.

- _slug:_ `google monorepo`  _created:_ '2026-03-14'

## 42. Google's Caffeine Index

**The 100-million-gigabyte index that updates hundreds of thousands of GB daily.**

- 100 million gigabyte index
- Updates hundreds of thousands of GB daily
- Real-time search indexing
- Google's search infrastructure
- _slug:_ `google-caffeine-index`  _created:_ 18-03-2026

## 43. Google Maps Routing

**Why Google uses C++, Pregel graph processing, and custom hardware to calculate billions of routes considering live traffic.**

- C++, Pregel graph processing
- Custom hardware
- Billions of routes daily
- Live traffic data
- Real-time routing optimization
- _slug:_ `google-maps-routing`  _created:_ 18-03-2026

## 44. The Map "Trap" (Paper Towns)

**Why Google Maps includes fake streets that don't exist.**

- To catch people stealing data, mapmakers include "Trap Streets"
- Fake cul-de-sacs or misspelled towns
- If competitor's map has same fake street
- Open-and-shut copyright case
- _slug:_ `google-maps-trap-streets`  _created:_ 18-03-2026

## 45. Why Google Built Its Own Internet (And Bypassed ISPs)

**Inside Google's private global fiber network.**

- Google built private global fiber network
- Bypass ISPs entirely
- Control own destiny
- Global infrastructure
- _slug:_ `google-private-internet`  _created:_ 18-03-2026

## 46. Why Google Designed Its Own AI Chips (TPUs)

**When renting GPUs wasn't enough.**

- Google designed TPUs (Tensor Processing Units)
- Custom AI chips
- Better than renting GPUs
- Hardware innovation
- _slug:_ `google-tpu-ai-chips`  _created:_ 18-03-2026

## 47. Google vs. Sharks

**Why Google had to armor-plate the internet against sharks.**

- Google laid thousands of miles of fiber optic cables on ocean floor
- Data packets started dropping
- Sharks attracted to electromagnetic fields of high-voltage repeaters
- Thought it was fish in distress
- Google had to wrap trans-pacific cables in Kevlar-like material
- Stop shark bites
- _slug:_ `google-vs-sharks`  _created:_ 18-03-2026

## 48. gRPC Explained in One Breath

**gRPC is binary, schema-based RPC over HTTP/2 that's faster than REST and built for service-to-service communication.**

- REST sends JSON (human-readable text). gRPC sends Protocol Buffers (binary) — much smaller, much faster to parse.
- RPC = Remote Procedure Call — you call a function on another server like it's local code
- Schema-first: you define your API in a .proto file, and code is auto-generated for any language
- HTTP/2: multiplexed, bidirectional streaming — one connection handles many concurrent calls
- Supports 4 patterns: unary (one request, one response), server streaming, client streaming, bidirectional streaming
- Used internally at: Google, Netflix, Uber, Square
- Perfect for: microservices talking to each other where you control both sides
- Not great for: browser-to-server (browsers don't natively support HTTP/2 gRPC), or when you need a human-readable API
- _slug:_ `grpc-in-one-breath`  _created:_ 24-03-2026

## 49. m                                                     Opinion piece arguing against PDFs as a format.

- _slug:_ `hot take pdfs`  _created:_ '2026-03-14'

## 50. How X (Twitter) Uses AI to Rank Every Tweet

**Grok AI replaced the entire X recommendation system in October 2025.**

- X replaced entire recommendation system with Grok AI
- Every tweet now ranked through AI
- Real-time ranking at scale
- _slug:_ `how-x-uses-ai-to-rank-tweets`  _created:_ 18-03-2026

## 51. HTTP Explained in One Breath

**HTTP is a stateless request-response protocol where clients ask for resources and servers reply.**

- Every time you load a webpage, your browser is making HTTP requests
- Stateless: each request is independent — server doesn't remember previous requests
- Methods: GET (read), POST (create), PUT/PATCH (update), DELETE (remove)
- Response codes: 200 OK, 201 Created, 404 Not Found, 500 Server Error, 429 Too Many Requests
- Headers carry metadata: content type, auth tokens, caching instructions
- HTTP/1.1: one request at a time per connection
- HTTP/2: multiplexing — multiple requests over one connection, much faster
- HTTP/3: built on QUIC (UDP-based), eliminates head-of-line blocking
- HTTPS = HTTP + TLS encryption — the padlock in your browser
- _slug:_ `http-in-one-breath`  _created:_ 24-03-2026

## 52. The 1,000-Year Clock (The Long Now)

**Jeff Bezos is building a computer that only ticks once a year.**

- Deep in Texas mountain
- 500-foot mechanical clock
- Designed to run 10,000 years without human intervention
- Uses thermal expansion from day/night cycles to power itself
- No batteries, no grid, just physics
- _slug:_ `jeff-bezos-1000-year-clock`  _created:_ 18-03-2026

## 53. The $1 Billion Spreadsheet Mistake

**How a copy-paste error in Excel lost JP Morgan $6 Billion.**

- "London Whale" trading disaster
- Model used sum of two rates instead of average
- Real-world "Production" isn't always fancy CI/CD pipeline
- Sometimes it's just a guy named Dave with unprotected .xlsx file
- _slug:_ `jp-morgan-spreadsheet-disaster`  _created:_ 18-03-2026

## 54. Kubernetes Explained in 60 Seconds

**Kubernetes explained in 60 seconds.**

- You have an app running in containers
- Containers crash, traffic spikes, servers fail
- Someone needs to manage all this
- Kubernetes is a container orchestrator
- You tell it what you want: "run 5 copies of my app"
- It makes it happen
- Cluster has two parts:
- Control plane: the brain (decides where containers run, monitors everything)
- Worker nodes: the muscle (actually run containers)
- Containers live inside pods (smallest unit Kubernetes manages)
- When a pod crashes, Kubernetes restarts it automatically
- When traffic spikes, it spins up more pods
- When a node dies, it moves workloads to healthy nodes
- You describe desired state, Kubernetes maintains it
- You declare, it delivers

_Reference_

- **Source:** https://kubernetes.io/docs/concepts/architecture/
- **Source:** https://kodekloud.com/blog/kubernetes-architecture-explained/
- **Source:** https://anynines.com/blog/intro-kubernetes-container-orchestration/
- _slug:_ `kubernetes-explained-60-seconds`  _created:_ 18-03-2026

## 55. LinkedIn's Job Matching AI (360Brew)

**The January 2025 AI model that understands entire career trajectories.**

- January 2025 AI model
- Called 360Brew
- Understands entire career trajectories
- Job matching at scale
- _slug:_ `linkedin-job-matching-ai`  _created:_ 18-03-2026

## 56. Load Balancing Explained in One Breath

**Load balancers distribute traffic across servers so no single machine gets overwhelmed.**

- If you have one server, it eventually falls over under traffic
- Load balancer sits in front of your server fleet — every request hits it first
- It picks a server and forwards the request
- Strategies: Round Robin (take turns), Least Connections (send to least busy), IP Hash (same user, same server)
- Also does health checks — stops sending traffic to servers that are down
- Layer 4 (TCP) vs Layer 7 (HTTP) load balancing
- Layer 7 can make smarter decisions: route /api to API servers, /static to CDN
- AWS ALB, Nginx, HAProxy, Cloudflare are all load balancers
- Without load balancing, horizontal scaling is impossible
- _slug:_ `load-balancing-in-one-breath`  _created:_ 24-03-2026

## 57. Three Ways to Reduce Your Context When Using MCPs

**Your MCP tools are eating your context window alive—here's how to stop the bleeding.**

- Every MCP server dumps entire tool catalog into context
- 10 servers? 50,000+ tokens gone before you start working
- Anthropic shipped a fix that cut context bloat by 98%
- Three strategies:
**Load tools on demand**
- Don't read every tool definition upfront
- Browse tools like files in a folder
- Only pull definitions when needed
**Use tool search with detail levels**
- Request just tool names first
- Then descriptions
- Then full schemas
- Progressive disclosure keeps context lean
**Filter data in execution, not in context**
- Process large datasets in code before returning
- 10,000 rows become 5 results
- Context never sees the waste

_Reference_

- **Source:** https://www.anthropic.com/engineering/code-execution-with-mcp
- **Source:** https://medium.com/@joe.njenga/claude-code-just-cut-mcp-context-bloat-by-46-9-51k-tokens-down-to-8-5k-with-new-tool-search-ddf9e905f734
- _slug:_ `mcp-context-reduction-tips`  _created:_ 18-03-2026  _status:_ done

## 58. Meta's Gigawatt AI Cluster: Connecting Thousands of GPUs

**Meta is building an AI cluster that uses as much power as a nuclear reactor.**

- A gigawatt = ~1 nuclear power plant's output
- Meta building clusters of 100,000+ GPUs for training Llama models
- The real engineering problem isn't compute — it's the network
- GPUs sit idle if they can't talk to each other fast enough
- Meta built custom high-speed interconnects (RDMA over Ethernet)
- Also designed custom optical switches for low-latency GPU-to-GPU comms
- Entire data centers architected around network topology, not just racks
- One misconfigured switch = thousands of idle GPUs = millions wasted per hour
- No one has solved networking at this scale before

_Reference_

- **Source:** https://engineering.fb.com/
- _slug:_ `meta-gigawatt-ai-cluster`  _created:_ 24-03-2026

## 59. Meta Says Agentic AI Broke Software Testing — Here's Their Fix

**AI agents can now write code. The problem? Traditional testing wasn't designed for code that writes itself.**

- Agentic AI systems generate code dynamically at runtime
- Traditional unit tests assume static, predictable code paths
- Meta's AI agents were producing code that passed tests but failed in production
- The problem: tests were written for human-authored code, not AI-generated logic
- Meta's solution: JiTTesting (Just-in-Time Testing)
- Instead of pre-written tests, JiTTesting generates tests at runtime based on what the agent actually produced
- Tests are created, run, and discarded dynamically — no human writes them
- Catches issues that static test suites would never see
- Opens a new category of software engineering: testing systems that test themselves

_Reference_

- **Source:** https://engineering.fb.com/
- _slug:_ `meta-jittesting-agentic-ai`  _created:_ 24-03-2026

## 60. How Meta Uses Undersea Cables to Control Its Own Destiny

**Why Meta invested billions in submarine infrastructure.**

- Meta invested billions in undersea cables
- Control own global connectivity
- Infrastructure independence
- _slug:_ `meta-undersea-cables`  _created:_ 18-03-2026

## 61. Why Meta Rewrote WhatsApp's Security Layer in Rust for 2B Users

**Meta just shipped Rust to 2 billion phones — and most users have no idea.**

- WhatsApp's original security layer written in Erlang/C
- Memory safety bugs are the #1 source of security vulnerabilities
- Rust eliminates entire classes of memory bugs at compile time
- Meta rewrote the cryptographic security layer in Rust
- Challenge: Rust had to run on the oldest, cheapest Android phones on earth
- Had to keep binary size tiny — no room for bloat
- Result: same security guarantees, zero memory safety CVEs in Rust code
- Ships to 2B users across iOS, Android, desktop
- Shows Rust is production-ready at the most demanding scale

_Reference_

- **Source:** https://engineering.fb.com/
- _slug:_ `meta-whatsapp-rust-rewrite`  _created:_ 24-03-2026

## 62. Microservices Explained in One Breath

**Microservices split an app into small independent services that communicate over the network.**

- Monolith: one codebase does everything — simple to start, painful to scale
- Microservices: each feature is its own service (auth service, payment service, notification service)
- Each service can be deployed, scaled, and updated independently
- Teams can own individual services — less coordination needed
- Services talk via HTTP/REST, gRPC, or message queues
- Netflix has 500+ microservices. Amazon famously mandated them in 2002.
- The cost: now you have distributed system problems — network failures, latency, data consistency
- You need service discovery, load balancing, distributed tracing, and circuit breakers
- Rule of thumb: start with a monolith. Break it apart when you hit specific pain points.
- _slug:_ `microservices-in-one-breath`  _created:_ 24-03-2026

## 63. The Underwater Data Center

**Microsoft threw a data center into the ocean... and it worked BETTER.**

- Project Natick
- Data centers fail from heat, oxygen corrosion, humans bumping things
- Filled capsule with nitrogen (no oxygen = no rust)
- Dumped off coast of Scotland
- Left for two years
- Failure rate was 1/8th of land-based data centers
- Ocean naturally cooled it
- Humans are the biggest bug in the system
- _slug:_ `microsoft-underwater-data-center`  _created:_ 18-03-2026

## 64. How Netflix Built for 65M Live Viewers — and Still Partially Failed

**Hook:** "Netflix spent 3 years preparing for the Tyson fight. 65 million people watched. It still buffered."
- Live streaming is fundamentally different from on-demand streaming
- Netflix had to invent a custom Live Origin server — the internet has no multicast, every viewer needs their own copy
- Hit 200Gbps+ through EVCache
- Built 4-path redundant ingest
- Eventually delivered to 100M devices in under 1 minute
- Open loop: "Why can't you just do what YouTube does?" — latency requirements are totally different

_Reference_

- **Source:** https://netflixtechblog.com/netflix-live-origin-41f1b0ad5371
- _slug:_ `netflix live streaming`  _created:_ 18-03-2026

## 65. How Netflix Chaos-Tests Its Own Production With "Chaos Monkey"

**Why intentionally breaking servers makes the platform stronger.**

- Chaos Monkey tool
- Intentionally breaks servers in production
- Chaos engineering practice
- Engineers build systems resilient to failure
- _slug:_ `netflix-chaos-monkey`  _created:_ 18-03-2026

## 66. Netflix Real-Time Distributed Graph

**Every time you switch from your phone to your TV on Netflix, a real-time graph silently connects those two sessions, processing 5 million record updates a second.**

- Netflix no longer just streaming app
- Ads, live events, mobile games
- You might watch Stranger Things on phone, switch to TV, open game on tablet
- Netflix runs hundreds of microservices, each managing own data
- Knowing three different events were one person used to be manual nightmare
- Power of real-time distributed graph
**How it works:**
- Graph = web of dots and lines
- Dots = entities (account, show)
- Lines = relationships between them
- Every action written to Apache Kafka (message queue handling 1M+ events/sec)
- Apache Flink jobs consume events, convert to graph updates
**The problem:**
- Microservice architecture great until you want to stitch all data together

_Reference_

- **Source:** https://netflixtechblog.com/how-and-why-netflix-built-a-real-time-distributed-graph-part-1-ingesting-and-processing-data-80113e124acc
- _slug:_ `netflix-real-time-distributed-graph`  _created:_ 18-03-2026

## 67. Netflix's Video Delivery Pipeline

**Why Netflix uses AWS, Open Connect CDN, and FreeBSD to stream 250 million hours of content daily without buffering.**

- AWS, Open Connect CDN, FreeBSD
- 250 million hours daily
- Zero buffering
- Video delivery at massive scale
- _slug:_ `netflix-video-delivery-pipeline`  _created:_ 18-03-2026

## 68. Nginx In One Breath

**nginx explained in one breath.**

- 32% of all websites run on it (TikTok, Airbnb, Slack)
- Traditional servers collapse under load
- nginx built for exactly that
**Traditional servers:**
- Spawn new thread for every single connection
- At scale: thousands of threads eating memory
- Constant context-switching
**nginx:**
- Runs few worker processes (one per CPU core)
- Each worker runs event loop
- Never blocking
- Fires through events as fast as they arrive
- 10,000 idle connections use just 2.5 MB of memory
**The difference:**
- Other servers add threads
- nginx adds events

_Reference_

- **Source:** https://nginx.org/en/
- **Source:** https://blog.nginx.org/blog/inside-nginx-how-we-designed-for-performance-scale
- **Source:** https://w3techs.com/technologies/details/ws-nginx
- **Source:** https://nginx.org/en/docs/events.html
- _slug:_ `nginx-in-one-breath`  _created:_ 18-03-2026

## 69. OAuth Explained in One Breath

**OAuth lets apps access your data without your password by exchanging short-lived tokens instead of credentials.**

- Old way: give a third-party app your Google password — terrible idea
- OAuth: you log into Google directly, Google gives the app a token
- Token only grants specific permissions (e.g. read calendar, not delete email)
- Token expires — even if stolen, it has a short window
- You can revoke access from Google's dashboard without changing your password
- "Login with Google/GitHub" = OAuth
- Roles: Resource Owner (you), Client (the app), Authorization Server (Google), Resource Server (Google's API)
- The app never sees your password — only the token
- OAuth is about authorization (what can this app do), not authentication (who are you) — that's OpenID Connect on top
- _slug:_ `oauth-in-one-breath`  _created:_ 24-03-2026

## 70. How OpenAI Scales GPT Training Across Tens of Thousands of GPUs

**Cluster orchestration and failure tolerance at massive scale.**

- Tens of thousands of GPUs
- GPT training at scale
- Cluster orchestration
- Failure tolerance
- Distributed training
- _slug:_ `openai-gpt-training-scale`  _created:_ 18-03-2026

## 71. How OpenAI Scaled PostgreSQL to 800M ChatGPT Users

**Every developer uses Postgres. Here's how OpenAI bent it to serve 800 million people.**

- ChatGPT went from 0 to 800M users in ~2 years
- Most devs assume Postgres breaks at scale — OpenAI proved otherwise
- Key moves: aggressive connection pooling with PgBouncer
- Read replicas for every region to reduce primary load
- Partitioned massive tables by date to keep queries fast
- Horizontal sharding for different feature domains
- Vacuum and autovacuum tuning to prevent table bloat
- Used Citus (distributed Postgres) for multi-tenant isolation
- The takeaway: scaling Postgres is an ops discipline, not a database swap

_Reference_

- **Source:** https://openai.com/blog
- _slug:_ `openai-postgresql-800m-users`  _created:_ 24-03-2026

## 72. Why Pinterest Moved Off the Cloud

**The $2 million mistake: Why Pinterest left the Cloud.**

- Most startups dream of being on AWS
- Pinterest got so big, "Cloud bill" became biggest expense
- Moved to own hardware (Colocation)
- Saved $20 million a year
- Cloud is for speed, Hardware is for profit
- _slug:_ `pinterest-left-cloud`  _created:_ 18-03-2026

## 73. Pinterest's Sharding Strategy for 150B Objects

**The one 2012 decision that saved them from database hell.**

- 150 billion objects
- 2012 sharding decision
- Database scaling strategy
- Critical infrastructure decision
- _slug:_ `pinterest-sharding-strategy`  _created:_ 18-03-2026

## 74. Rate Limiting Explained in One Breath

**Rate limiting controls how often clients can hit an API to prevent abuse and outages.**

- Without rate limiting: one bad actor can send millions of requests and take down your service
- Common rule: 100 requests per minute per user
- Algorithms: Token Bucket (refill tokens over time), Sliding Window (count requests in rolling window), Fixed Window (count resets every minute)
- Stored in Redis — fast counters that expire automatically
- HTTP 429 "Too Many Requests" is the standard response
- Applied at different levels: per IP, per API key, per user, per endpoint
- Defensive uses: stop scraping, brute-force login protection, DDoS mitigation
- Also used for fair usage in free tiers — GitHub API gives 60 req/hour unauthenticated, 5000 authenticated
- Cloudflare, Kong, and API gateways handle this at scale
- _slug:_ `rate-limiting-in-one-breath`  _created:_ 24-03-2026

## 75. Why Reddit Rebuilt Its Entire Backend After One Traffic Spike

**The scaling lessons from viral growth.**

- Traffic spike forced backend rebuild
- Scaling lessons
- Viral growth architecture
- _slug:_ `reddit-traffic-spike`  _created:_ 18-03-2026

## 76. Redis Explained in One Breath

**Redis is a super-fast in-memory data store you use to cache, rate-limit, and share state so your database doesn't fall over.**

- Lives entirely in RAM — microsecond read/write speeds
- Your database is slow because it reads from disk; Redis reads from memory
- Use case 1: Cache — store expensive query results so you don't re-compute them
- Use case 2: Rate limiting — count API calls per user per second
- Use case 3: Session storage — share login state across multiple servers
- Use case 4: Pub/Sub message broker between services
- Data evicted automatically when memory fills up (LRU policy)
- Not a replacement for your database — a layer in front of it
- Instagram, Twitter, GitHub all rely on Redis at massive scale
- _slug:_ `redis-in-one-breath`  _created:_ 24-03-2026

## 77. Relational vs Non-Relational Databases

**Relational vs non-relational databases in one breath.**

- Every app stores data, two main options
**Relational databases:**
- Store data in tables (rows, columns, fixed structure)
- Like giant spreadsheet with rules
- Examples: MySQL, Postgres
- Tables link through relationships
- Ask complex questions across data with SQL
- Great when accuracy matters and data shape is predictable
- Banking, e-commerce, transactional
**Non-relational databases (NoSQL):**
- Ditch rigid structure
- Data as flexible documents, key-value pairs, or graphs
- Examples: MongoDB, Redis, DynamoDB
- No fixed schema
- Data shape can evolve without breaking everything
- No complex joins = scale out across many servers fast
- Social feeds, real-time apps, rapid growth
**When to choose:**
- Relational: clear relationships, need consistency
- Non-relational: need flexibility or scale fast

_Reference_

- **Source:** https://blog.purestorage.com/purely-technical/relational-vs-non-relational-databases/
- **Source:** https://www.sprinkledata.com/blogs/relational-database-vs-non-relational-understanding-the-differences
- _slug:_ `relational-vs-non-relational-db`  _created:_ 18-03-2026

## 78. Roblox's Custom Lua (Luau)

**Why Roblox forked Lua and made it faster for 380M players.**

- Forked Lua language
- Created Luau
- 380 million players
- Game engine optimization
- _slug:_ `roblox-custom-lua`  _created:_ 18-03-2026

## 79. The Secret Cables Under New York

**Why traders spend $300 million to be 1 millisecond faster.**

- High-frequency traders (HFT) don't use standard internet
- Dug private, perfectly straight fiber-optic tunnel Chicago to New York
- Spread Networks
- Shave 3 milliseconds off round trip
- At that scale, 3ms = Billions of dollars
- _slug:_ `secret-cables-new-york`  _created:_ 18-03-2026

## 80. Why Shopify Runs "Flash Sales Simulators" Year-Round

**Engineering for Black Friday every day.**

- Flash sales simulators
- Run year-round
- Test for Black Friday traffic
- Ensure reliability
- _slug:_ `shopify-flash-sales-simulator`  _created:_ 18-03-2026

## 81. Shopify's Pod Architecture

**Shopify hasn't had a global outage in years—and it's because of one disaster they call "Redismageddon."**

- Shopify handles 284 million requests per minute on Black Friday
- One bad server used to take down everything
- Rebuilt entire architecture around one idea: total isolation
**Pod structure:**
- Fully isolated copy of Shopify
- Own MySQL database
- Own Redis
- Own cache
- Nothing shared
**Isolation benefits:**
- If one pod fails, only stores on that pod go down
- Everyone else keeps running
- Over 100 pods now
- Can be deployed in any region
- Operates completely independently
**Before:**
- All database shards shared one Redis instance
- When Redis died, everything died
**Now:**
- Outages stay local
- Blast radius shrinks to one pod
**The philosophy:**
- They didn't try to prevent failures
- Just made sure failures couldn't spread

_Reference_

- **Source:** https://shopify.engineering/e-commerce-at-scale-inside-shopifys-tech-stack
- **Source:** https://shopify.engineering/a-pods-architecture-to-allow-shopify-to-scale
- **Source:** https://blog.bytebytego.com/p/shopify-tech-stack
- **Source:** https://shopify.engineering/bfcm-readiness-2025
- _slug:_ `shopify-pod-architecture`  _created:_ 18-03-2026

## 82. Shopify + Ruby on Rails

**Everyone said Ruby on Rails couldn't scale—Shopify just processed 284 million requests per minute with it.**

- While tech companies rushed to microservices, Shopify did the opposite
- Doubled down on one massive Rails app
- 2.8 million lines of code
- One codebase
- Millions of stores
- But how do they stop one viral product launch from crashing everyone else?
**The answer: Pods**
- Shopify splits monolith into isolated clusters
- Each pod runs independently with own database
- If one merchant's flash sale explodes, only that pod feels it
- Other pods don't notice
**YJIT compiler:**
- Custom compiler makes Ruby run 20% faster
- No code changes needed
- Just flip a switch
**The lesson:**
- Shopify didn't abandon Rails
- They made Rails faster
- Proved the monolith can win at scale

_Reference_

- **Source:** https://shopify.engineering/shopify-monolith
- **Source:** https://railsatscale.com/2025-01-10-yjit-3-4-even-faster-and-more-memory-efficient/
- **Source:** https://blog.bytebytego.com/p/shopify-tech-stack
- **Source:** https://shopify.engineering/ruby-yjit-is-production-ready
- _slug:_ `shopify-ruby-on-rails-monolith`  _created:_ 18-03-2026

## 83. Slack's 5 Million WebSocket Problem

**How Slack maintains real-time messaging with 5M simultaneous connections.**

- 5 million simultaneous connections
- Real-time messaging at scale
- WebSocket infrastructure
- _slug:_ `slack-5-million-websocket-problem`  _created:_ 18-03-2026

## 84. Slack Cut Customer Impact Hours by 90% With a Deploy Safety Program

**Slack deployments used to regularly take down features for users. Here's how they made that almost never happen.**

- Deployments are the #1 cause of production incidents at most companies
- Slack built a "Deploy Safety Program" — a system of automated checks before any deploy goes live
- Canary deployments: roll out to 1% of users first, watch metrics for 10 minutes
- Automated rollback triggers if error rate or latency spikes
- Feature flags on everything — deploy code dark, enable for customers separately
- Strict deployment windows aligned with low-traffic periods
- Result: 90% reduction in customer-impacting hours from deployments
- Lesson: the safest deploy is one nobody notices

_Reference_

- **Source:** https://slack.engineering/
- _slug:_ `slack-deploy-safety-program`  _created:_ 24-03-2026

## 85. How SpaceX Streams Rocket Telemetry From Space in Real Time

**Ground stations, satellites, and low-latency data pipelines.**

- Real-time rocket telemetry
- Ground stations
- Satellites
- Low-latency pipelines
- _slug:_ `spacex-rocket-telemetry`  _created:_ 18-03-2026

## 86. Why Spotify Built "Backstage" to Run Its Engineering Org

**The internal developer portal that became its own product.**

- Backstage internal developer portal
- Spotify uses to run engineering org
- Became own product
- Internal tool gone external
- _slug:_ `spotify-backstage`  _created:_ 18-03-2026

## 87. SQL vs NoSQL Explained in One Breath

**SQL prioritizes structure and relationships. NoSQL prioritizes flexibility and scale.**

- SQL (relational): data lives in tables with strict schemas. Rows, columns, foreign keys.
- Great for: financial data, user accounts, anything with relationships between entities
- PostgreSQL, MySQL, SQLite — battle-tested, ACID compliant, great tooling
- NoSQL: documents, key-value pairs, graphs, or wide columns. No fixed schema.
- Great for: high write volume, flexible data shapes, horizontal sharding
- MongoDB (documents), Redis (key-value), Cassandra (wide column), Neo4j (graph)
- The myth: NoSQL is faster. Reality: it depends entirely on the access pattern.
- Most companies use both: Postgres for core data, Redis for caching, Cassandra for time-series
- 90% of the time, reach for Postgres first. Scale the problem before scaling the database.
- _slug:_ `sql-vs-nosql-in-one-breath`  _created:_ 24-03-2026

## 88. What Is SSL, TLS and HTTPS

**That padlock in your browser? It means your data is encrypted in transit — and here's exactly how.**

- HTTP sends data as plain text — anyone on the network can read it
- HTTPS = HTTP + encryption. The S stands for Secure.
- TLS (Transport Layer Security) is the encryption protocol — SSL was the old name, TLS is what's actually used today
- TLS handshake: client and server agree on encryption method and exchange keys
- Uses asymmetric encryption (public/private keys) to establish a shared secret, then symmetric encryption for speed
- Certificate: proves the server is who it says it is — issued by a Certificate Authority (CA)
- Your browser ships with a list of trusted CAs. If the cert isn't signed by one, you get a warning.
- Let's Encrypt made TLS free in 2016 — no excuse for HTTP-only sites now
- TLS 1.3 (2018): faster handshake, stronger ciphers, drops old broken ones
- _slug:_ `ssl-tls-https`  _created:_ 24-03-2026

## 89. Stack Overflow's "One Web Server"

**How Stack Overflow serves 50 million developers with just 9 servers.**

- Everyone else building "Microservices" with 500 containers
- Stack Overflow runs monolithic architecture
- 50 million developers
- 9 servers total
- "Primary" SQL server handles nearly everything
- Optimized code better than scaling horizontally with messy code
- _slug:_ `stack-overflow-one-server`  _created:_ 18-03-2026

## 90. Beginner-focused video actually walking through how to use Claude effectively.

- _slug:_ `start using claude`  _created:_ '2026-03-14'

## 91. How Stripe Detects Fraud in Milliseconds

**Machine learning pipelines that decide before checkout completes.**

- Real-time fraud detection
- Millisecond response time
- ML pipelines
- Payment fraud prevention
- _slug:_ `stripe-fraud-detection`  _created:_ 18-03-2026

## 92. Stripe's 800ms Payment Infrastructure

**How Stripe processes payments in 0.8 seconds with real-time fraud detection.**

- Processes payments in 0.8 seconds
- Real-time fraud detection
- 800ms SLA
- _slug:_ `stripe-payment-infrastructure`  _created:_ 18-03-2026

## 93. Stripe's Payment Reliability

**How Stripe uses Ruby, Postgres, and idempotency keys to process $1 trillion annually with 99.999% uptime.**

- Ruby on Rails
- Postgres
- Idempotency keys
- $1 trillion annual volume
- 99.999% uptime
- Payment infrastructure reliability
- _slug:_ `stripe-payment-reliability`  _created:_ 18-03-2026

## 94. TCP vs UDP and Why You Should Care

**TCP makes sure every packet arrives. UDP just fires and forgets. That difference determines how most of the internet works.**

- Both are transport protocols — how data moves across the internet
- TCP: connection-oriented. Handshake first. Every packet acknowledged. Packets reordered if needed.
- TCP guarantees delivery — perfect for: web pages, emails, file downloads, banking
- UDP: no handshake. Send and move on. No guarantee packets arrive or arrive in order.
- UDP is faster — no overhead, no waiting for acknowledgment
- UDP is perfect for: video calls, gaming, live streaming, DNS lookups
- In a video call, a dropped frame is better than pausing to retransmit it — use UDP
- HTTP/3 (QUIC) runs on UDP but adds its own reliability — best of both worlds
- Rule of thumb: correctness → TCP. Speed → UDP.
- _slug:_ `tcp-vs-udp`  _created:_ 24-03-2026

## 95. Why Tesla Built a Dojo Supercomputer Instead of Using the Cloud

**Training autonomy models at hyperscale.**

- Tesla built Dojo supercomputer
- Instead of cloud
- Custom hardware for AI training
- Autonomous vehicle training
- _slug:_ `tesla-dojo-supercomputer`  _created:_ 18-03-2026

## 96. Why TikTok Replicates Data Across Continents in Real Time

**The infrastructure behind ultra-fast video feeds.**

- Real-time data replication across continents
- Ultra-fast video feeds
- Global distribution
- _slug:_ `tiktok-realtime-replication`  _created:_ 18-03-2026

## 97. TikTok's Recommendation Engine

**How TikTok uses PyTorch, Redis, and a custom CDN to serve personalized videos to 1 billion users in milliseconds.**

- PyTorch, Redis, custom CDN
- 1 billion users
- Personalized recommendations
- Millisecond latency
- _slug:_ `tiktok-recommendation-engine`  _created:_ 18-03-2026

## 98. TikTok's Video Processing Pipeline

**Near-instant video processing across distributed GPUs for millions of daily uploads.**

- Millions of daily uploads
- Near-instant processing
- Distributed GPU processing
- Video encoding at scale
- _slug:_ `tiktok-video-processing-pipeline`  _created:_ 18-03-2026

## 99. tokens and tokenisation


_Tokens and Tokenisation_

- Why the same prompt costs different amounts depending on which model you use.
- Explain what a token actually is (not a word, not a character), how models break text into tokens differently, and explain how some models token are more expensive. Use a concrete example: show the same prompt tokenised by two different models side by side. End with the practical takeaway for developers choosing between models.
- _slug:_ `tokens-and-tokenisation`

## 100. Twitch's Edge Network

**The invisible infrastructure of 100 data centers processing millions of streams.**

- 100 data centers
- Edge network infrastructure
- Millions of concurrent streams
- Live streaming at scale
- _slug:_ `twitch-edge-network`  _created:_ 18-03-2026

## 101. Twitter's Timeline Stack

**How Twitter rebuilt with GraphQL, Manhattan DB, and vector embeddings to rank 500 million tweets per day in real-time.**

- GraphQL
- Manhattan DB
- Vector embeddings
- 500 million tweets daily
- Real-time ranking at scale
- _slug:_ `twitter-timeline-stack`  _created:_ 18-03-2026

## 102. How Uber Upgraded 16,000 Database Nodes Without Taking Anything Offline

**Hook:** "You've delayed a MySQL version upgrade before. Uber couldn't — and it took a full year."
- 2,100+ clusters across 3 regions
- Built a full automation framework just for this
- End result: 33% p99 latency improvement on reads, 47% on writes
- Open loop: "How do you upgrade a database that 20 million people are actively using?"

_Reference_

- **Source:** https://uber.com/blog/upgrading-ubers-mysql-fleet
- _slug:_ `uber mysql upgrade`  _created:_ 18-03-2026

## 103. Why Uber Decided Google Search Wasn't Good Enough and Built Their Own

**Hook:** "Uber threw out their search engine and built one from scratch — because Google couldn't solve their problem."
- Uber's search problem is unique — searching things that are physically moving in real time (drivers, restaurants, availability)
- No off-the-shelf engine handles live physical-world state + traditional relevance simultaneously
- Custom engine "Sia" uses a "Live Index" that buffers and flushes every 30 minutes alongside real-time availability data
- Open loop: "What's different about searching for a moving car vs. a webpage?"

_Reference_

- **Source:** https://uber.com/blog/evolution-of-ubers-search-platform
- _slug:_ `uber search engine`  _created:_ 18-03-2026

## 104. How Uber Predicts Demand Before You Open the App

**Real-time surge pricing algorithms.**

- Predict demand before app opened
- Real-time surge pricing
- ML algorithms
- _slug:_ `uber-demand-prediction`  _created:_ 18-03-2026

## 105. Uber's Real-Time Dispatch System

**How Uber uses Kafka, Node.js microservices, and PostgreSQL/Redis to match 20+ million rides per day in under 2 seconds.**

- Kafka message queue
- Node.js microservices
- PostgreSQL, Redis
- 20+ million rides per day
- Under 2 seconds matching
- _slug:_ `uber-dispatch-system`  _created:_ 18-03-2026

## 106. Uber's Real-Time Matching

**How Uber connects millions of drivers in under 500 milliseconds using bipartite graph algorithms.**

- Need to connect millions of drivers in under 500ms
- Uses bipartite graph algorithms
- Real-time matching at massive scale
- _slug:_ `uber-real-time-matching`  _created:_ 18-03-2026

## 107. /usa/Multi-part series breaking down AI fundamentals.


_Episodes_

- 1. How a basic LLM works
- 2. Machine learning
- 3. Context engineering
- _slug:_ `understanding ai series`  _created:_ '2026-03-14'

## 108. How Valve Updates Millions of Games Without Breaking the Internet

**Inside the global infrastructure behind Steam downloads.**

- Updates millions of games
- Without breaking internet
- Global Steam infrastructure
- Download distribution network
- _slug:_ `valve-steam-updates`  _created:_ 18-03-2026

## 109. Vercel Custom Domain Setup

**So it turns out hosting and deploying a website is way easier than I thought.**

- Used Vercel to host
- Connect GitHub repo, push code, automatically builds and deploys
- Want real domain instead of .vercel.app URL? That's where DNS comes in
- DNS = internet's address book (maps domain name to server)
**Setup process:**
- 1. Buy domain from Namecheap or GoDaddy
- 2. Go to Vercel project settings, add custom domain
- 3. Vercel gives two records to configure in DNS settings
**A Record:**
- Points domain to Vercel's servers
- Tell internet: send anyone visiting my domain to IP 76.76.21.21
- That's Vercel's IP
- Just paste it in
**TXT Record:**
- Unique string from Vercel
- Add to DNS settings to verify you own domain
**After configuring:**
- Go to DNS Checker
- Shows world map of how far records have spread globally
- That's "propagation"
- Usually takes few minutes to few hours
- Two records, one tool to verify, site is live on real domain

_Reference_

- **Source:** https://vercel.com/docs/projects/domains/add-a-domain
- **Source:** https://dnschecker.org/
- _slug:_ `vercel-custom-domain-setup`  _created:_ 18-03-2026

## 110. The "Nyan Cat" Ransomware Fix

**The hacker who stopped a global cyberattack with a $10 domain.**

- WannaCry ransomware destroying hospitals and banks in 2017
- Researcher found "Kill Switch" in code
- Hardcoded URL
- Virus checked if URL existed
- If it did, stopped spreading
- Bought domain for $10.69
- Saved the world's data
- _slug:_ `wannacry-ransomware-10-dollar-fix`  _created:_ 18-03-2026

## 111. WebSockets Explained in One Breath

**WebSockets keep one open connection so the server can push data instantly instead of the client constantly asking "anything yet?"**

- Normal HTTP: client asks, server answers, connection closes. Repeat forever.
- That's fine for loading a webpage — terrible for live chat or stock prices
- WebSocket: client and server do a one-time handshake, then leave the connection open
- Either side can send a message at any time — no more polling
- Used by: Slack (messages), Figma (cursor positions), trading platforms (prices), multiplayer games
- One WebSocket connection can handle thousands of messages per second
- The downside: keeping millions of open connections is expensive — each one holds server memory
- Slack had to solve the "5 million simultaneous WebSocket connections" problem
- _slug:_ `websockets-in-one-breath`  _created:_ 24-03-2026

## 112. What Is a Vector Database

**Regular databases search by exact match. Vector databases search by meaning — and that's why every AI app uses one.**

- Traditional DB: find rows where name = "coffee". Exact match only.
- AI problem: you want to find things that are *similar* — images that look alike, text that means the same thing
- Vectors: AI models convert anything (text, images, audio) into a list of numbers (a vector) that captures meaning
- "Cat" and "kitten" have similar vectors. "Cat" and "stock market" have very different vectors.
- Vector DB stores these number lists and finds nearest neighbors instantly
- Used for: semantic search, recommendation engines, image similarity, RAG (Retrieval-Augmented Generation)
- Every ChatGPT plugin that "remembers" your documents uses a vector database
- Popular options: Pinecone, Weaviate, Qdrant, pgvector (Postgres extension)
- The AI boom made vector databases one of the fastest-growing categories in infrastructure
- _slug:_ `what-is-a-vector-database`  _created:_ 24-03-2026

## 113. WhatsApp's 50 Engineers Handling 40B Messages

**How Erlang enabled 3B users with a tiny team.**

- 50 engineers
- 40 billion messages
- 3 billion users
- Erlang language
- "Let it crash" philosophy
- _slug:_ `whatsapp-50-engineers-40b-messages`  _created:_ 18-03-2026

## 114. WhatsApp's Encryption Infrastructure

**Why WhatsApp chose Erlang and the Signal Protocol to send 100 billion messages daily with zero access to content.**

- Erlang language
- Signal Protocol
- 100 billion messages daily
- End-to-end encryption
- Zero knowledge architecture
- _slug:_ `whatsapp-encryption-infrastructure`  _created:_ 18-03-2026

## 115. The "Let It Crash" Philosophy

**How WhatsApp served 900M users with only 50 engineers.**

- 50 engineers
- 900 million users
- Didn't use Java or C++
- Used Erlang (telecom switch language from 80s)
- "Let it crash" philosophy
- If process bugs out, don't catch error
- Just kill it and respawn instantly
- Self-healing at scale
- Built a zombie code army that refuses to die
- _slug:_ `whatsapp-let-it-crash`  _created:_ 18-03-2026
