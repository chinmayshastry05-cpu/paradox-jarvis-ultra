# Paradox Jarvis Ultra — All-Repos Feature / License / Gap Matrix

> User-facing matrix. No "secure" or "ready" claim. No paid service is
> proposed. No code is proposed to be copied across incompatible licenses.

- **Date:** 2026-10-15 (IST)
- **Method:** Read actual `LICENSE` files / GitHub API license endpoints,
  repo descriptions, READMEs, and source files. Claims taken from a README
  are labelled **README-claim**, not re-verified by running tests here.
- **Delivered inventory:** All 25 entries below reconcile the inventory
  delivered in the KRS scope-expansion mail (exact owner/repo pairs;
  URLs follow those pairs exactly). No entry is omitted. Entries that
  could not be verified are marked UNVERIFIED, not assumed.
- **Status vocabulary:**
  - **IMPLEMENTED** — code exists in the fork and is tested.
  - **PLUGIN PLAN** — reachable only via an existing resolver / external
    process / config opt-in, with no code copied into the fork. A plugin
    plan does **NOT** close a gap.
  - **BLOCKED / UNTESTED** — no code, no live run, or a missing dependency.
  - **UNVERIFIED** — license or feature could not be confirmed from actual
    source. Do not treat as present.
  - **GAP: OPEN** — the capability is missing. It stays OPEN until it is
    implemented **and** tested. A plugin-plan cell never marks a gap closed.

---

## 1. License matrix (actual source evidence)

Attribution must be preserved wherever code, skills, or text is reused.
Apache-2.0 and MIT are permissive and mutually compatible for *linking /
depending* with attribution kept; that does **not** authorise copying
source-available or unlicensed code into the fork. **No license = no
permission to reuse. Unknown license is a copying blocker, not permission.**

| Repo | URL | License (verified) | Reuse rule for Paradox Jarvis Ultra |
|---|---|---|---|
| Upstream OpenJarvis | https://github.com/open-jarvis/openjarvis | **Apache-2.0** | Base of the fork. Keep LICENSE + attribution + history. |
| Paradox Jarvis Ultra fork (PRIVATE) | https://github.com/chinmayshastry05-cpu/paradox-jarvis-ultra | **Apache-2.0** (inherited) | Private personal fork. Do not strip upstream attribution. |
| Cactus | https://github.com/cactus-compute/cactus | **Source-available, NOT OSI open source** (project NOTICE; GitHub license: Other/NOASSERTION) | **Do NOT copy** Cactus engine/binding into Jarvis. A Cactus integration must be separate, explicitly licensed, with NOTICE + LICENSE intact — not assumed. |
| Open-Higgsfield-AI | https://github.com/Autom8AI/Open-Higgsfield-AI | **UNVERIFIED** — description claims MIT, but GitHub license endpoint returned null (no LICENSE file detected) | **Do NOT copy.** Description claim ≠ verified license. |
| Ponytail | https://github.com/dietrichgebert/ponytail | **MIT** | Prompt-only coding guidance. May be *followed* as a working rule (it is guidance, not code to vendor). Keep attribution if quoted. |
| Hermes Gadget SDK | https://github.com/Adolanium/hermes-gadget-sdk | **MIT** | External Hermes-ecosystem SDK (voice/text devices). Do NOT vendor into the fork. |
| Herald-OS | https://github.com/iamlukethedev/Herald-OS | **MIT** | An OS project, not a Jarvis feature. Do NOT copy. Independent project, not affiliated with Nous Research. |
| Octop | https://github.com/TencentCloud/Octop | **MIT** | A competing self-hosted assistant. Reference only. Do NOT copy. |
| VoxCPM | https://github.com/OpenBMB/VoxCPM | **Apache-2.0** | TTS model (see §2). Model weights / GPU required. Do NOT assume free local use without checking model terms. |
| Cua | https://github.com/trycua/cua | **MIT** | Candidate **external** computer-use plugin only. Do NOT vendor Cua code into the fork. Do NOT assume Cua Spaces cloud = free. |
| Rea | https://github.com/morluto/rea | **MIT** | Reverse-engineering agent tool. Unrelated to assistant features. Do NOT copy. |
| Awesome Free LLM APIs | https://github.com/mnfst/awesome-free-llm-apis | **CC0-1.0** (list) | A list, not code. Listed services have their own terms/keys. Do NOT treat "free" as verified. |
| Oh My Hermes | https://github.com/rlaope/oh-my-hermes | **MIT** | Hermes plugin (coding intelligence, memory, workflows). External plugin only. Do NOT vendor. |
| Geo Sleuth | https://github.com/Oldcircle/geo-sleuth | **MIT** | Photo-geolocation agent skill. External skill only. Privacy-sensitive — must be gated if ever used. Do NOT vendor. |
| OpenDroid | https://github.com/yashab-cyber/opendroid | **UNVERIFIED — no license detected** (GitHub: NOASSERTION) | **Do NOT copy.** No license = no reuse permission. |
| Gods Eye View | https://github.com/bilawalsidhu/gods-eye-view | **UNVERIFIED — no license detected** (GitHub: NOASSERTION) | **Do NOT copy.** A globe/visualization demo, unrelated to assistant features. |
| OpenMontage | https://github.com/calesthio/OpenMontage | **AGPL-3.0** | **Do NOT copy or link into the Apache-2.0 fork** without a licensing decision. AGPL + Apache mixing needs an explicit decision first. Do not silently mix. |
| Open Generative AI | https://github.com/Anil-matcha/Open-Generative-AI | **MIT** (GitHub API) | Image/video generation studio. Backends are MuAPI frontends — **paid/key-gated; "free" is NOT verified**. "No content filters / unrestricted" is a safety flag, not a feature to adopt. Do NOT assume free generation. |
| Hermes Agent | https://github.com/NousResearch/hermes-agent | **MIT** | **Do NOT copy Hermes source into the fork.** Use only via the existing `HermesResolver` or as a side-by-side process. Keep attribution on reused skill text. |
| Claude Code Router | https://github.com/musistudio/claude-code-router | **MIT** | Multi-model routing control plane. Reference / external only. Do NOT vendor. |
| Agentic Browser Bridge | https://github.com/chinmayshastry05-cpu/agentic-browser-bridge | **MIT** | Talk to it as an **external MCP stdio server**. Never import bridge code in-process. Keep MIT notice. |
| StudyReels | https://github.com/chinmayshastry05-cpu/studyreels | **UNVERIFIED — no license detected** | **Do NOT copy** StudyReels code into Jarvis. Separate, unlicensed project. |
| Tally LLM | https://github.com/chinmayshastry05-cpu/tally-llm | **UNVERIFIED — no license detected** | **Do NOT copy.** Separate research prototype. Tally work stays separate. |
| ClientOps AI Demo | https://github.com/chinmayshastry05-cpu/clientops-ai-demo | **UNVERIFIED — no license detected** | **Do NOT copy.** Triage-assistant demo (fictional data). |
| RiskLabs | https://github.com/chinmayshastry05-cpu/risklabs | **UNVERIFIED — no license detected** | **Do NOT copy.** College academic project, separate. |
| First Role Radar | https://github.com/ChinmaysTG/first-role-radar | **UNVERIFIED — no license detected** | **Do NOT copy.** Job-research tool (SerpApi, key-gated). |
| OpenClaw skills | https://github.com/openclaw/skills | **UNVERIFIED** | Resolver may fetch at runtime; do NOT vendor skill text into the fork. Per-skill licences must be checked before reuse. |
| Dependency licences (Kokoro, faster-whisper, Deepgram SDK, Cartesia, OpenAI SDK, Tavily, `python-telegram-bot`, Playwright, etc.) | — | **UNVERIFIED** | Do NOT assert a dependency's licence. Check each package's own LICENSE before redistributing or vendoring. |

**Compatibility holds:**
- Apache-2.0 (OpenJarvis, VoxCPM) + MIT (Hermes, Bridge, Cua, Ponytail,
  Gadget SDK, Herald-OS, Octop, Rea, Oh My Hermes, Geo Sleuth, Open
  Generative AI, Claude Code Router) — permissive pair; dependency /
  external-process use with attribution is the safe shape. Copying is
  still avoided: resolvers and MCP stdio keep the boundary.
- AGPL-3.0 (OpenMontage) — **no copying/linking into Apache-2.0** without
  an explicit licensing decision.
- Source-available Cactus and unlicensed repos — **no copying.**
- Paid/cloud services — **no paid service proposed.** Cloud-gated paths
  stay opt-in / off by default.

---

## 2. Feature matrix (all 25 delivered entries)

For each entry: **useful assistant feature** (if any) vs **unrelated /
domain project**; what OpenJarvis already has; what is missing; how it
would integrate (if at all); gap status. A plugin-plan cell never closes
a gap.

### 2a. Base + Hermes ecosystem

| Repo | Useful assistant feature / unrelated | OpenJarvis already has | Missing / gap | Integration method | Gap status |
|---|---|---|---|---|---|
| OpenJarvis (upstream) | Base assistant: CLI/server/desktop, agents, skills, tools, channels, connectors, memory, scheduler | Fork base (all upstream features as starting point) | Fork additions are in §3; upstream gaps (e.g. live-tested voice, keychain) remain | Fork (Apache-2.0, attribution kept) | — |
| Hermes Agent | Skill library (~150 skills, README-claim) + eval runner + gateway service (side-by-side) | Resolver code (`HermesResolver` walks `skills/<category>/<skill>/SKILL.md`, frontmatter only); eval-runner code | No verified end-to-end Hermes↔Jarvis integration test; gateway not configured/verified; skill contents never executed/verified; per-skill licences unchecked | Resolver / external process only; **do NOT copy source** | **GAP: OPEN** — integration test + live gateway verification |
| Hermes Gadget SDK | Voice/text device SDK (ESP32 firmware, Linux client, desktop simulator) for Hermes Agent | None (no device SDK in fork) | No device support; no ESP32/Linux-client integration | External Hermes-ecosystem SDK; **do NOT vendor** | **GAP: OPEN** — no device integration |
| Oh My Hermes | Hermes plugin: coding intelligence, long-term memory, model-optimized workflows | None of this plugin's features in fork | No plugin integration; memory-v1 in fork is separate (SQLite+FTS5, not this plugin) | External plugin only; **do NOT vendor** | **GAP: OPEN** — no plugin integration |
| Herald-OS | **Unrelated** — an agent-native OS with Hermes as interface | None (Jarvis is an app, not an OS) | Nothing to integrate; an OS is out of scope | None | N/A (unrelated domain) |
| Ponytail | Coding-guidance prompt ("laziest senior dev"): smallest complete change, no extra features | Followed as a working rule for coding tasks | Nothing to integrate (guidance, not code) | Follow as guidance; keep attribution if quoted | N/A (guidance, not a feature) |

### 2b. Voice / TTS

| Repo | Useful assistant feature / unrelated | OpenJarvis already has | Missing / gap | Integration method | Gap status |
|---|---|---|---|---|---|
| VoxCPM | TTS model: tokenizer-free multilingual speech generation, voice cloning | Voice profiles + Kokoro backend + faster-whisper/Deepgram/OpenAI-Whisper backends (see §2e) | **No verified local TTS for Kannada or Sanskrit**; VoxCPM is a model requiring weights + GPU; no integration, no real-audio test | External model only (if ever); **do NOT assume free local use**; needs explicit licensing/model-terms check + GPU | **GAP: OPEN** — Kannada/Sanskrit local TTS missing; VoxCPM not integrated or tested |
| OpenJarvis voice (fork additions) | Push-to-talk state machine, sentence TTS, barge-in, opt-in wake word, Indic WER hooks | Code: `speech/voice_state.py`, `voice_io.py`, `_voice_chat.py`, `indic.py` | Real mic/speaker/model/audio test in **none** of the four languages; live-TTY barge-in mocked only; wake word is a transcript spotter, **not wired into chat REPL**; Kokoro has no Kannada/Sanskrit `lang_code` | Code in fork; real-audio tests are a separate, unauthorised step | **GAP: OPEN** — no real-audio verification in any language |

Four-language voice detail (profiles in `speech/indic.py`):
- English: STT forwarded-untested; TTS Kokoro `af_heart` pipeline-untested.
- Hindi: STT forwarded-untested; TTS Kokoro `lang_code="h"` but **no curated voice ID** — pipeline-untested.
- Kannada: STT forwarded-untested; TTS **NO local pipeline** (Kokoro has no Kannada pipeline).
- Sanskrit: STT forwarded-untested (whether Whisper handles Sanskrit is UNVERIFIED); TTS **NO local pipeline**.
- Cloud TTS/STT (Deepgram, Cartesia, OpenAI) — backend code, key-gated, **UNTESTED**; **no paid/cloud TTS proposed**.

### 2c. System / Android / GUI control

| Repo | Useful assistant feature / unrelated | OpenJarvis already has | Missing / gap | Integration method | Gap status |
|---|---|---|---|---|---|
| Cua | Computer-use (GUI automation driver, Spaces, Lume, CUA-S1) | None in fork (no GUI-automation driver) | No GUI automation; no Cua integration | **External plugin only** (as Hermes `cua-driver` does), behind opt-in + per-action approval; **never vendored**; Cua Spaces cloud NOT proposed | **GAP: OPEN** — no GUI automation |
| OpenDroid | Android agent (accessibility-driven screen automation, self-planning) | None in fork (no Android control, no ADB) | No Android control; no integration. **No license** blocks copying in any case | None (unlicensed — do NOT copy). A future Android plugin would need a licensed, explicitly approved design | **GAP: OPEN** — no Android control |
| Jarvis gated system control (fork) | Shell (OFF by default), container shell, sandboxed Python (AST allowlist), capability RBAC | Code: `shell_exec.py`, `docker_shell_exec.py`, `code_interpreter.py`, `capabilities.py` | Live shell run UNTESTED; policy-file live enforcement UNTESTED; default-open capability policy is a risk without `default_deny` | Code in fork; gated (opt-in + per-action single-use approval) | **GAP: OPEN** — live enforcement untested |

### 2d. Video / image generation

| Repo | Useful assistant feature / unrelated | OpenJarvis already has | Missing / gap | Integration method | Gap status |
|---|---|---|---|---|---|
| OpenMontage | Agentic video production (12 pipelines, 100+ tools, 700+ skill/knowledge files) | None (no video production in fork) | No video production; **AGPL-3.0 blocks copying/linking** into Apache-2.0 without a licensing decision | None until licensing decision. Do NOT silently mix AGPL into Apache code | **GAP: OPEN** — no video production; AGPL decision pending |
| Open-Higgsfield-AI | AI image generation & cinema studio (20+ models) | None (no image generation in fork) | No image generation; **license UNVERIFIED** (description claims MIT, API null); backends are MuAPI frontends (paid/key-gated) | None (unverified license + paid backends). Do NOT assume free generation | **GAP: OPEN** — no image generation |
| Open Generative AI | AI image & video generation studio (600+ models) | None | No image/video generation; backends are MuAPI frontends (paid/key-gated); "no content filters / unrestricted" is a safety flag | None (paid backends). Do NOT assume free generation | **GAP: OPEN** — no image/video generation |

### 2e. Connectors / skills / routing / lists

| Repo | Useful assistant feature / unrelated | OpenJarvis already has | Missing / gap | Integration method | Gap status |
|---|---|---|---|---|---|
| Claude Code Router | Multi-model routing control plane (route across models, fuse capabilities, orchestrate tools) | Engine code (Ollama, MLX, cloud LLMs via keys, LiteLLM) + MCP client/loader | No router integration; no multi-model orchestration via this tool | External / reference only; **do NOT vendor** | **GAP: OPEN** — no router integration |
| Geo Sleuth | Photo-geolocation skill (OSM geometry, skylines, satellite, street view) | None (no geolocation skill) | No geolocation skill; privacy-sensitive if ever used | External skill only; **do NOT vendor**; must be gated | **GAP: OPEN** — no geolocation skill (and privacy review required first) |
| Awesome Free LLM APIs | List of free LLM APIs (keys) | None (not a feature) | Not a feature to integrate; listed services have own terms/keys | Reference list only; verify each service's terms before use | N/A (list, not a feature) |
| Rea | Reverse-engineering agent (app behaviour → native binaries) | None | Unrelated to assistant features (security-research tool) | None | N/A (unrelated domain) |
| Gods Eye View | Spy-satellite simulator / 3D globe spatial intelligence demo | None | Unrelated to assistant features (visualization demo) | None (also unlicensed) | N/A (unrelated domain) |
| Octop | Competing self-hosted multi-user, multi-agent assistant | None of Octop's features | Reference only; no integration proposed | None (do NOT copy) | N/A (competing assistant) |

### 2f. Owner projects (separate — do NOT copy into Jarvis)

| Repo | What it is | Relation to Jarvis | Gap status |
|---|---|---|---|
| Agentic Browser Bridge | MCP stdio server for browser control (32 tools); MIT | **Integrated as external MCP stdio server** (see §3). Never imported in-process. | Integrated (external); live consequential calls UNTESTED |
| StudyReels | Fully local study app (Flutter/Android, Cactus + Qwen3 0.6B) | Separate, unlicensed. **Do NOT copy** Android/Cactus code into Jarvis. | N/A (separate project) |
| Tally LLM | Research prototype: TallyPrime Q&A, plain-English → Tally XML | Separate, unlicensed. **Do NOT copy.** Tally work stays on its own branch/repo. | N/A (separate project) |
| ClientOps AI Demo | AI request-triage assistant demo (fictional data, approval-gated replies) | Separate, unlicensed. **Do NOT copy.** Approval-gating pattern is noted as consistent with the confirmation gate, not copied code. | N/A (separate project) |
| RiskLabs | Explainable-AI financial risk prediction (ML + NLP + SHAP, Streamlit) | Separate, unlicensed. **Do NOT copy.** College academic project. | N/A (separate project) |
| First Role Radar | Student job research via SerpApi Google Jobs | Separate, unlicensed. **Do NOT copy.** SerpApi is key-gated. | N/A (separate project) |

### 2g. Connectors / channels / platforms (OpenJarvis upstream features)

Counts from file listing: **41 connector modules**, **34 channel modules**,
**43 tool modules**. Code-present ≠ live-verified: no OAuth / live
credential run was done.

| Group | Implemented (code) | Blocked / Untested |
|---|---|---|
| Google (Gmail, Drive, Calendar, Contacts, Tasks) | YES — OAuth via `google_auth` / `oauth.py` | Live OAuth + live reads UNTESTED |
| Apple (Calendar, Contacts, Health, Music, Notes) | YES — local Apple APIs / CLI | Live macOS run UNTESTED |
| Messaging / channels (Telegram, Discord, Slack, WhatsApp incl. Baileys, Signal, Email, Google Chat, IRC, WebChat, Teams, Matrix, Mattermost, Feishu, BlueBubbles, Line, Viber, Messenger, Reddit, Mastodon, XMPP, RocketChat, Zulip, Twitch, Nostr, SendBlue, Webhook) | YES — channel modules; channels disabled by default | Live send/receive per channel UNTESTED |
| Productivity (Notion, Obsidian, Dropbox, GitHub notifications, Granola, HackerNews, RSS/news) | YES | Live sync UNTESTED |
| Health (Oura, Strava, Apple Health) | YES | Live sync UNTESTED |
| Media / misc (Spotify, Apple Music, weather, WhatsApp connector, iMessage, Slack connector, Outlook, IMAP) | YES | Live calls UNTESTED |
| Search (Tavily + `ddgs`, `web_search` tool) | YES | Live search UNTESTED; Tavily key-gated, opt-in only |
| Cloud LLM engines (OpenAI / Anthropic / Google / OpenRouter / LiteLLM / NVIDIA NIM) | YES — engine code, key-gated | Live cloud calls UNTESTED; **no spend authorised** |
| Local engines (Ollama, MLX, Apple Foundation Models, Gemma.cpp, vLLM) | YES — engine code | Live inference UNTESTED |
| MCP (generic client/loader/server/transport + browser bridge) | YES — code | Live consequential bridge call UNTESTED (refusal paths only) |

Telegram owner-only gateway (detail): Bot API channel (send + long-poll)
is code-present; owner-only allowlist (`allowed_chat_ids`) is code-present.
**UNTESTED live** — no bot token, no live send/receive run. A
misconfigured/empty allowlist must be treated as **not owner-only**.
Telegram user-account (MTProto / userbot) is **BLOCKED** — no MTProto
client in code; Bot API only. Do not add a userbot. Single-use approval
for consequential Telegram-triggered actions goes through the central
gate; the live Telegram→approval round-trip is UNTESTED.

Windows / WSL2 / macOS / Linux: installers + docs + per-OS keychain
backends are code-present. Live run on any target is UNTESTED. Native
Windows is Phase-1 (WSL2 is the recommended Windows path). Desktop GUI
(Tauri) is code-present; live build/run UNTESTED. Python `>=3.10,<3.14`.

---

## 3. Fork additions — security / memory / MCP-browser (current state)

### 3a. Security (corrected — stale "TOCTOU window remains" removed)

| Area | State | Evidence |
|---|---|---|
| Central single-use tool confirmation | IMPLEMENTED — `ConfirmationGate`: approvals bound to exact tool + arguments, expiring, consumed on first use; no "approve everything" mode; all auto-approve bypasses removed | `security/confirmation.py`; `ToolExecutor` is the single enforcement point; server `POST /v1/approvals/tool` (grant) + `/revoke` |
| Delivery redaction (fail-closed) | IMPLEMENTED — fail-closed ladder (Rust scanner → Python regex fallback → blocked placeholder); all outgoing text / structured fields / tool-call fragments / named SSE events redacted **before** delivery; error chunks carry fixed generic text only | `security/delivery_redaction.py`; `server/stream_bridge.py`, `routes.py`, `agent_manager_routes.py`, `research_router.py`, `ws_bridge.py`, CLI `chat_cmd` / `ask.py` |
| Split-secret holdback (streaming) | IMPLEMENTED — `StreamingRedactor` holds any suffix that could grow into a secret: complete-pattern matches at end, partial-pattern matches, literal prefixes (proper **and complete**), assignment literals + trailing whitespace. Covers **every** two-chunk split position and 1-char feeds for every pattern (regression-tested). Bare literals emitted raw at flush (not secrets). | `security/delivery_redaction.py` (`_suspicious_start`, `_ASSIGNMENT_LITERALS`); `tests/security/test_delivery_redaction.py` (exhaustive split + 1-char tests) |
| Overlong suppression | IMPLEMENTED — once an oversized suspicious suffix is dropped, the redactor stays in suppression until a safe separator (closing quote of an unclosed quoted value, else first whitespace / quote). Continuation bytes are dropped, never emitted. Memory stays bounded (suppressed bytes never buffered). | `security/delivery_redaction.py` (`_suppressing`, `_consume_suppressed`, `_unclosed_assignment_quote`); overlong regression tests |
| Canonical path / TOCTOU | IMPLEMENTED — descriptor-based open (`open_within`): component-by-component walk holding a descriptor per directory, symlinks resolved via `readlink` on descriptors, final open with `O_NOFOLLOW` anchored on the parent descriptor, dev/ino identity check. **Non-destructive write:** opened WITHOUT `O_TRUNC`, validated, then `ftruncate` on the verified fd. A file appearing between walk and open is refused. Creation uses `O_CREAT | O_EXCL`. Adversarial tests (symlink-flip races + swap-before-open for truncate/append/create) assert victim bytes unchanged. | `security/canonical_path.py`; `tests/security/test_canonical_path_toctou.py` |
| Shell | IMPLEMENTED, **OFF by default** — requires `OPENJARVIS_SHELL_ENABLED=1` or config + per-call confirmation; `docker_shell_exec` requires confirmation | `tools/shell_exec.py`, `tools/docker_shell_exec.py` |
| OS keychain vault (no file/plaintext fallback) | IMPLEMENTED — backends per OS | Real keychain backends **UNTESTED**; legacy `.vault_key` migration has no direct test |
| Output scanning boundary (residual) | **Known limitation:** already-emitted segments cannot be retracted; a secret split across two *discrete* named events (neither half matching a pattern) is not reconstructed; patterns outside the scanner list are not recognised. Persisted agent content in the managed-agent DB and trace store is still raw model output (storage, not delivery) — delivery paths are redacted, stored copies are not. | Documented in `security/delivery_redaction.py` |
| TOCTOU residual | **Known limitation:** the descriptor-based fix covers `canonical_path` consumers (`file_read`, `file_write`, `apply_patch`). Other path-by-string opens (e.g. shell tool, storage backends) are unchanged. | Documented in code |

### 3b. Memory v1

IMPLEMENTED — SQLite + FTS5 facts (source/provenance, timestamps, scopes,
dedupe/supersede/correction/deletion, ranked relevant retrieval);
`remember` / `forget` / `show` / `correct` / `summary` commands;
source-linked summaries, bounded retention, deletion across retrieval
indexes. 100-query benchmark (developer benchmark only — **NOT** proof of
lifelong perfect recall). UNTESTED: Rust-backed doc backends,
cross-process writers, large-corpus ranking, JSONL→SQLite migration.
Superseded facts' text stays in DB (status-filtered, never retrievable);
only `forget` hard-deletes.

### 3c. MCP / browser via agentic-browser-bridge

IMPLEMENTED — guarded stdio server entry (`browser_bridge.py`); default
allowlist = read-only + reversible tools; navigation refused unless origin
allowlisted (default loopback + `https://example.com`); consequential
tools (click/type/navigate) need an operator confirmer or are refused
fail-closed; native browser tools OFF by default. Live smoke: stdio
handshake + `tools/list` passed (32 tools); `browser_click` refuses
without confirmer; `browser_navigate` to a non-allowlisted origin
refuses. UNTESTED: no real consequential bridge call end-to-end; no
navigation beyond `about:blank` snapshot.

### 3d. Agents / skills / scheduler / A2A

Code-present (8 built-in agents; `agents/`, `skills/`, `scheduler/`,
`a2a/`). Skills from Hermes / OpenClaw / GitHub resolvers (no copying).
Live multi-agent / scheduled runs UNTESTED. Skill counts are README-claims.

### 3e. CI / workflows

**BLOCKED (known caveat):** `.github/workflows/` excluded from the fork's
pushed history (token lacked `workflow` scope); CI files need restoration
by someone with workflow scope.

---

## 4. Gaps that remain OPEN (not closed by a plugin-plan cell)

1. Independent security review of the fail-closed redaction + TOCTOU fixes
   (archive + logs provided for that review).
2. Live testing everywhere: Telegram allowlist, connectors OAuth, keychain
   backends, real audio (all four languages), live shell/tool runs, live
   MCP consequential calls, live desktop/server agent runs, live install
   on any OS.
3. Kannada / Sanskrit local TTS — no backend in the repo provides it.
   VoxCPM is a model requiring weights + GPU, not integrated or tested.
4. GUI automation — no driver in the fork.
5. Android control — no driver in the fork; OpenDroid is unlicensed.
6. Video / image production — no code in the fork; OpenMontage is AGPL
   (licensing decision pending); Higgsfield / Open Generative AI backends
   are paid/key-gated and their licenses are unverified/flagged.
7. Hermes↔Jarvis end-to-end integration test + live gateway verification.
8. Hermes Gadget SDK device integration — no code.
9. Oh My Hermes plugin integration — no code.
10. Claude Code Router integration — no code.
11. Geo Sleuth skill integration — no code (and privacy review required).
12. CI workflows — excluded from pushed history, need restoration.
13. Real-audio voice verification in all four languages; wake word not
    wired into the chat REPL.
14. Persisted agent DB / trace store still holds raw model output
    (storage, not delivery).
15. TOCTOU fix covers `canonical_path` consumers only; other
    path-by-string opens unchanged.

---

## 5. Rules for any follow-up build (binding constraints)

- Keep upstream Apache-2.0 LICENSE + attribution in the fork; keep MIT
  notices on Bridge / Hermes / Cua artefacts.
- Do **not** copy code from Cactus (source-available), OpenMontage
  (AGPL), OpenDroid / Gods Eye View / StudyReels / Tally LLM / ClientOps
  / RiskLabs / First Role Radar (unlicensed), or any unverified-license
  repo into Jarvis.
- Do **not** propose paid services (cloud LLMs, cloud TTS/STT, Tavily paid
  tiers, SendBlue paid tiers, Cua Spaces cloud, MuAPI frontends). Key-gated
  cloud paths stay opt-in, off by default, and are never the default.
- Hermes, Cua, and the browser bridge stay **external** (resolver / stdio /
  side-by-side process), never vendored into the fork.
- Owner-only Telegram = allowlist set + live-tested from the owner chat
  only; empty allowlist = not owner-only. No MTProto userbot.
- System control stays gated (opt-in + per-action single-use approval);
  Android control and GUI automation do not exist — they need a new,
  explicitly approved, gated plugin, not a copy.
- Four-language voice must not be claimed until real-audio tests pass per
  language; Kannada/Sanskrit local TTS is a known missing backend.
- No "secure" / "ready" claim. Every feature above is code-present,
  plugin-planned, or blocked/untested as tabled. A plugin plan never
  closes a gap.
