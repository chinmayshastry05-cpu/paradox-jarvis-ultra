# Paradox Jarvis Ultra — All-Repos Feature / License / Gap Matrix

> Research-only document. No code was pushed to GitHub. The checkout at
> `~/workspace/openjarvis-merge` was NOT modified (read-only inspection).
> No "secure" or "ready" claim is made. No paid service is proposed.
> No code is proposed to be copied across incompatible licenses.

- **Date:** 2026-10-15 (IST)
- **Method:** Read actual `LICENSE` files, `package.json` / `pyproject.toml`
  license fields, README/docs, and source files in local checkouts; checked
  public GitHub API license endpoints (no auth, metadata only) for upstream
  repos. Claims taken from a README are labelled **README-claim**, not
  re-verified by running tests here.
- **Delivered inventory:** Searched `~/workspace` (maxdepth 3) for
  `*inventory*`, `*paradox*jarvis*`, `*jarvis*ultra*`. **No delivered-inventory
  file was found.** This matrix is therefore built from source evidence, not
  from any prior inventory or message claims.
- **Status vocabulary used below:**
  - **IMPLEMENTED** — code exists in the inspected checkout.
  - **PLUGIN PLAN** — reachable only via an existing resolver / external
    process / config opt-in, with no code copied into the fork.
  - **BLOCKED / UNTESTED** — no code, no live run, or a missing dependency.
  - **UNVERIFIED** — license or feature could not be confirmed from actual
    source in this pass. Do not treat as present.

---

## 1. License matrix (actual source evidence)

Attribution must be preserved wherever code, skills, or text is reused.
Apache-2.0 and MIT are permissive and mutually compatible for *linking /
depending* with attribution kept; that does **not** authorise copying
source-available or unlicensed code into the fork.

| Repo / system | License (verified) | Evidence | Reuse rule for Paradox Jarvis Ultra |
|---|---|---|---|
| Upstream OpenJarvis (`open-jarvis/OpenJarvis`) | **Apache-2.0**, Copyright 2025 The OpenJarvis Authors | Local `LICENSE` in `openjarvis-merge` (full Apache-2.0 text + copyright line); GitHub API: `Apache-2.0`; `pyproject.toml` `license = {text = "Apache-2.0"}` | Base of the fork. Keep LICENSE + attribution + history. |
| Paradox Jarvis Ultra fork (`chinmayshastry05-cpu/paradox-jarvis-ultra`, PRIVATE) | **Apache-2.0** (inherited) | Local checkout `openjarvis-merge` LICENSE = Apache-2.0; README states base = upstream commit `74694cdb`, attribution kept; `git remote` = `chinmayshastry05-cpu/paradox-jarvis-ultra.git` | Private personal fork. Do not strip upstream attribution. Private repo license not checkable via public API (expected 404/denied) — local LICENSE governs. |
| `openjarvis-mcp-browser` local checkout | **Apache-2.0** | Local LICENSE (Apache-2.0); `pyproject.toml` Apache-2.0 | Earlier branch snapshot of `openjarvis-personal` (remote `chinmayshastry05-cpu/openjarvis-personal`), head `f99f2a6` (bridge MCP integration). Same upstream lineage — do NOT treat as a separate project or re-license. |
| `openjarvis-security-job` local checkout | **Apache-2.0** | Local LICENSE (Apache-2.0); `pyproject.toml` Apache-2.0 | Earlier branch snapshot of `openjarvis-personal`, head `0d011db8` (confirmation/keychain/shell work). Same lineage as above. |
| Hermes Agent (`NousResearch/hermes-agent`) | **MIT** | GitHub API: `MIT` | **Do NOT copy Hermes source into the fork.** Use only via the existing `HermesResolver` (git-cache skill import, see §2) or as a side-by-side process. Keep Hermes copyright/attribution on any skill text reused. |
| Local `~/workspace/hermes-agent` | **UNVERIFIED (no LICENSE present)** | Directory contains **only `install.sh`** — no LICENSE, no `skills/`, no agent source | Nothing in this local dir proves Hermes features. Feature claims below rest on `install.sh` + OpenJarvis resolver code only. |
| Agentic Browser Bridge (`chinmayshastry05-cpu/agentic-browser-bridge`) | **MIT**, Copyright (c) 2026 chinmayshastry05-cpu | Local LICENSE (MIT) + `package.json` `"license": "MIT"`; GitHub API: `MIT` | Talk to it as an **external MCP stdio server** (`src/openjarvis/mcp/browser_bridge.py`). Never import bridge code in-process. Keep MIT notice. |
| Cua (`trycua/cua`, local `~/workspace/cua`) | **MIT**, Copyright (c) 2025 Cua AI, Inc. | Local `LICENSE.md` (MIT) | Candidate **external** computer-use plugin only (see §2). Do NOT vendor Cua code into the fork without keeping its LICENSE/attribution, and do NOT assume Cua Spaces cloud = free. |
| StudyReels (`chinmayshastry05-cpu/studyreels`) | **UNVERIFIED — no LICENSE file found** | No `LICENSE` locally; GitHub license endpoint returned 404 (no detected license) | **Do NOT copy StudyReels code into Jarvis.** No license = no permission to reuse. Treat as separate, unlicensed project. |
| Cactus (used by StudyReels via `third_party/cactus`) | **Source-available, NOT OSI open source** (README-stated) | StudyReels `README.md` NOTICE: free grant for individuals / education / non-commercial / orgs under $2M funding AND under $2M revenue; commercial licence otherwise; `third_party/cactus/LICENSE` cited but **not** independently opened in this pass | **Do NOT copy the Cactus binding or engine into Jarvis.** If Jarvis ever needs on-device LLM via Cactus, it must be a separate, explicitly licensed integration with the NOTICE + LICENSE intact — not assumed. |
| Paradox Clipper Pro (`chinmayshastry05-cpu/paradox-clipper-pro`) | **MIT** | GitHub API: `MIT` | Out of Jarvis scope; listed only because it shares the owner. No copying proposed. |
| `paradox-agent`, `risklabs`, `tally-llm`, `blockads-apk`, `clientops-ai-demo`, `morphe-microg-apk` (GitHub user `chinmayshastry05-cpu`) | **UNVERIFIED — no license detected** | GitHub license endpoint 404 for `paradox-agent` / `studyreels`; public repo list shows `license: null` for the rest | Do NOT copy code from these into Jarvis. No license = no reuse permission. |
| OpenClaw skills (`openclaw/skills`) | **UNVERIFIED** | OpenJarvis resolver points at `https://github.com/openclaw/skills.git`; GitHub API lookup returned 404 in this pass | Resolver may fetch at runtime; do NOT vendor OpenClaw skill text into the fork. Per-skill licences (if any) must be checked before reuse. |
| Dependency licences (Kokoro, faster-whisper, Deepgram SDK, Cartesia, OpenAI SDK, Tavily, `python-telegram-bot`, Playwright, etc.) | **UNVERIFIED in this pass** | Not opened per-package | Do NOT assert a dependency's licence. Check each package's own LICENSE before redistributing or vendoring. |
| `brag_skill`, `geo-sleuth`, `oj-mem-delivery` (local dirs) | MIT / MIT / Apache-2.0 respectively (local LICENSE files) | Local LICENSE reads | Not part of Jarvis; no reuse proposed. Listed only to avoid confusion with similarly named local dirs. |

**Compatibility holds enforced in this matrix:**
- Apache-2.0 (OpenJarvis) + MIT (Hermes, Bridge, Cua) — permissive pair;
  dependency / external-process use with attribution is the safe shape.
  Copying is still avoided: resolvers and MCP stdio keep the boundary.
- Source-available Cactus and unlicensed repos — **no copying proposed.**
- Paid/cloud services — **no paid service proposed** anywhere in this matrix.
  Cloud-gated paths are marked as such and stay opt-in / off by default.

---

## 2. Feature matrix

Columns: **Implemented** = code in `openjarvis-merge` (the Paradox fork
checkout). **Plugin plan** = reachable via an existing resolver / external
process / config, without copying code. **Blocked / Untested** = missing,
untested live, or gated.

### 2a. Hermes features

| Feature | Implemented | Plugin plan (no copy) | Blocked / Untested | License / cost gate | Evidence |
|---|---|---|---|---|---|
| Hermes skill import (~150 skills — README-claim, count UNVERIFIED) | YES — resolver code | `HermesResolver` (`src/openjarvis/skills/sources/hermes.py`): git-caches `NousResearch/hermes-agent`, walks `skills/<category>/<skill>/SKILL.md`, reads frontmatter only | Skill *contents* never executed/verified here; per-skill licences unchecked | Hermes MIT; keep attribution on reused skill text | `skills/sources/hermes.py`; README `jarvis skill install hermes:arxiv` |
| Hermes eval runner / comparison | YES — runner code | `src/openjarvis/evals/backends/external/hermes_agent.py`, `_runners/hermes_runner.py` | Requires `HERMES_AGENT_PATH`-style external checkout; `live_external` pytest marker = spawns real foreign subprocesses — not run here | MIT (external process) | Eval backend files; `pyproject.toml` pytest markers |
| Hermes gateway service | NO | Side-by-side only: local `hermes-agent/install.sh` stages include `gateway` (`hermes gateway install --if-missing`), skipped when non-interactive | **UNTESTED** — no gateway configured/verified in this pass; no gateway code in the fork | MIT; no spend proposed | `~/workspace/hermes-agent/install.sh` stages `prerequisites repository venv python-deps config products setup gateway complete` |
| Hermes package manager (`hermes pm`), products, desktop app | NO | Side-by-side only: `install.sh` references `hermes pm install`, products stage, `--include-desktop` | **UNVERIFIED** — only `install.sh` present locally; no Hermes source to confirm behaviour | MIT; no spend proposed | `install.sh` (`pm_args`, `--include-desktop`, `--skip-browser`, `--skip-computer-use`) |
| Hermes browser tools (agent-browser + Chromium) | NO in fork | Side-by-side only via Hermes `pm install agent-browser` | **UNTESTED**; Jarvis side already has its own guarded bridge (see §2c) — do not run two browser drivers against one profile | MIT | `install.sh` `--skip-browser` |
| Hermes computer-use driver (`cua-driver`) | NO in fork | Side-by-side only via Hermes `pm install cua-driver` / `--without cua-driver` | **UNTESTED**; see §2c for the gated system-control plan | Cua MIT (see §1); no vendoring | `install.sh` `--skip-computer-use` |

**Gap:** There is no verified, end-to-end Hermes↔Jarvis integration test in
this pass. Hermes is a *neighbour system + skill source*, not a merged
component. Do not claim "Hermes features work in Jarvis" beyond the resolver
+ eval-runner code above.

### 2b. Telegram owner-only gateway

| Feature | Implemented | Plugin plan | Blocked / Untested | License / cost gate | Evidence |
|---|---|---|---|---|---|
| Telegram Bot API channel (send + long-poll receive) | YES — code | — | **UNTESTED live** — no bot token, no live send/receive run in this pass | Free Bot API; token is a secret — never in chat/logs | `src/openjarvis/channels/telegram.py` (`TelegramChannel`, `ChannelRegistry.register("telegram")`); `pyproject.toml` extra `channel-telegram = ["python-telegram-bot>=21.0"]` |
| Owner-only allowlist | YES — code | Set `allowed_chat_ids` (comma-separated chat IDs); `_poll_loop` drops messages from unlisted chats | **UNTESTED live** — allowlist enforcement is code-read, not live-proven; a misconfigured/empty allowlist must be treated as **not owner-only** | Config-gated | `telegram.py`: `_allowed_chat_ids` + allowlist check in `_handle_msg`; `drop_pending_updates=True` |
| Channels disabled by default | YES — docs + config contract | Enable per-channel in config only after credentials + allowlist are set | — | — | `docs/user-guide/channels.md`: "`[channel]` defaults to `enabled = false`" |
| Telegram user-account (MTProto / userbot) access | NO | **None proposed** | **BLOCKED** — no MTProto client in code; Bot API only. Do not add a userbot. | — | Grep: only Bot API (`api.telegram.org/bot…`) in `telegram.py` |
| Single-use approval for consequential Telegram-triggered actions | YES — central gate (see §2f) | Telegram handlers go through the same `ConfirmationGate` as other tools | Live Telegram→approval round-trip **UNTESTED** | — | `src/openjarvis/security/confirmation.py` |

**Gap / required before use:** Set exactly one owner chat ID in
`allowed_chat_ids`, verify with a live send/receive test from that chat only,
and confirm non-allowlisted chats are ignored. Until that live test exists,
"owner-only gateway" is code-present, not proven.

### 2c. Optional gated system / Android control

| Feature | Implemented | Plugin plan (gated, opt-in) | Blocked / Untested | License / cost gate | Evidence |
|---|---|---|---|---|---|
| Shell execution | YES — code, **OFF by default** | Opt-in only: `OPENJARVIS_SHELL_ENABLED=1` or `security.shell_enabled = true`, **plus** single-use argument-bound approval per call; sanitised env; 100 KB/stream cap; 300 s max | Live shell run **UNTESTED** here; `agent ask --yes` removed per README | Free / local; fail-closed | `src/openjarvis/tools/shell_exec.py` (`SHELL_OPT_IN_ENV_VAR`, `requires_confirmation=True` per docstring) |
| Full system access preset | YES — example config only | `configs/openjarvis/examples/full-system-access.toml` (shell + file read/write + patch + interpreter) — header warns: no allowlist/denylist/workdir restriction | **UNTESTED**; must never be the default | — | That file, verbatim warning |
| Container-scoped shell | YES — code | `docker_shell_exec`: runs only in the active TB v2.1 task container; refuses with no active container; explicitly not a host-shell alternative | Docker runtime **UNTESTED** here | — | `src/openjarvis/tools/docker_shell_exec.py` |
| Sandboxed Python execution | YES — code | `code_interpreter`: AST allowlist (`json`, `math`, `time` only), blocked `eval/exec/open/getattr…`, isolated child `-I -B -S`, resource limits; Docker boundary is the real containment per docstring | Live run **UNTESTED** here | — | `src/openjarvis/tools/code_interpreter.py` |
| Capability RBAC (`file:read/write`, `network:fetch`, `code:execute`, `channel:send`, `system:admin`, …) | YES — code | `CapabilityPolicy` with `default_deny` option; default is open unless `default_deny=True` | Policy-file live enforcement **UNTESTED** here; default-open is a risk if relied on without `default_deny` | — | `src/openjarvis/security/capabilities.py` |
| Native GUI automation (pyautogui / xdotool / UIAutomation / Accessibility) | NO | **None in-repo** | **BLOCKED / NO CODE** — grep of `src/openjarvis/tools` found no GUI-automation driver | — | Grep: `cua|computer-use|pyautogui|xdotool|uiautomation` → no hits in tools |
| Android control (ADB / Termux / Android app / AndroidManifest / Kotlin / Flutter in Jarvis) | NO | **None in-repo** | **BLOCKED / NO CODE** — grep found only incidental matches (e.g. "Android" inside unrelated text / SMS docs). No ADB, no device bridge, no Android APK in the Jarvis fork | — | Grep across `src/` + `docs/`; StudyReels (Flutter/Android) is a **separate, unlicensed** project — do NOT copy its Android code into Jarvis |
| Android / desktop control via external Cua Driver | NO in fork | **Plugin plan only:** run Cua Driver as an external process (as Hermes `cua-driver` does), behind the same opt-in + single-use approval gate as `shell_exec`; never vendored | **UNTESTED** — no integration code, no live device run; Cua Spaces cloud path is NOT proposed | Cua MIT; keep attribution; no paid/cloud path proposed | Local `~/workspace/cua/README.md` (Spaces / Driver / Lume / CUA-S1); Hermes `install.sh` `cua-driver` reference |

**Gap:** "System/Android control" in Paradox Jarvis Ultra today = **gated
local shell + container shell only**. There is no Android control and no GUI
automation. Any such control must arrive as a new, explicitly gated plugin
(external process + opt-in + per-action approval), not by copying Cua /
StudyReels code into the fork.

### 2d. Connectors

Counts from file listing: **41 connector modules** in
`src/openjarvis/connectors/`, **34 channel modules** in
`src/openjarvis/channels/`, **43 tool modules** in `src/openjarvis/tools/`.
Code-present ≠ live-verified: no OAuth / live credential run was done here.

| Connector group | Implemented (code) | Plugin plan / gating | Blocked / Untested | License / cost gate | Evidence |
|---|---|---|---|---|---|
| Google: Gmail, Drive, Calendar, Contacts, Tasks (`gcalendar`, `gdrive`, `gmail`, `gmail_imap`, `gcontacts`, `google_tasks`, `google_auth`, `oauth`) | YES | OAuth via `google_auth` / `oauth.py`; one OAuth covers Gmail/Calendar/Tasks per README preset | Live OAuth + live reads **UNTESTED** | Free Google APIs; OAuth secrets — never in chat | `src/openjarvis/connectors/*.py`; README `jarvis connect gdrive` |
| Apple: Calendar, Contacts, Health, Music, Notes (`apple_*`) | YES | Local Apple APIs / CLI | Live macOS run **UNTESTED** | Apple platform-gated | `src/openjarvis/connectors/apple_*.py` |
| Messaging / channels (27 documented in `docs/user-guide/channels.md`: Telegram, Discord, Slack, WhatsApp incl. Baileys, Signal, Email, Google Chat, IRC, WebChat, Teams, Matrix, Mattermost, Feishu, BlueBubbles, Line, Viber, Messenger, Reddit, Mastodon, XMPP, RocketChat, Zulip, Twitch, Nostr, SendBlue, Webhook) | YES — channel modules | Per-channel extras in `pyproject.toml` (e.g. `channel-discord`, `channel-slack`, `channel-line`…); channels disabled by default | Live send/receive per channel **UNTESTED** | Tokens/secrets per platform; SendBlue has a free tier per docs — **no paid tier proposed** | `docs/user-guide/channels.md` table; `src/openjarvis/channels/*.py`; `pyproject.toml` channel extras |
| Productivity / notes: Notion, Obsidian, Dropbox, GitHub notifications, Granola, HackerNews, RSS/news | YES | Per-connector config + tokens | Live sync **UNTESTED** | Per-service terms; no paid tier proposed | `src/openjarvis/connectors/{notion,obsidian,dropbox,github_notifications,granola,hackernews,news_rss}.py` |
| Health / fitness: Oura, Strava, Apple Health | YES | Tokens / HealthKit | Live sync **UNTESTED** | — | `connectors/{oura,strava,apple_health}.py` |
| Media / misc: Spotify, Apple Music, weather, WhatsApp connector, iMessage, Slack connector, Outlook, IMAP | YES | Tokens / local access | Live calls **UNTESTED** | — | `connectors/{spotify,apple_music,weather,whatsapp,imessage,slack_connector,outlook,imap}.py` |
| Search: Tavily + `ddgs` (`tools-search` extra), `web_search` tool | YES — code | `tools-search = ["tavily-python", "ddgs"]` | Live search **UNTESTED**; Tavily is key-gated (cloud) — stays opt-in, never default | Tavily key-gated; `ddgs` free path exists — no paid plan proposed | `pyproject.toml`; `src/openjarvis/tools/web_search.py` |
| Cloud LLM engines (OpenAI / Anthropic / Google / OpenRouter / LiteLLM / NVIDIA NIM) | YES — engine code | Only when a key is in env (`OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY`); local-first is default with no key | Live cloud calls **UNTESTED**; **no spend authorised** | **Paid/key-gated — NOT proposed**; LiteLLM pinned `==1.104.2` per security comment | `src/openjarvis/engine/{cloud,litellm,nim,openai_compat_engines}.py`; `docs/getting-started/install.md` cloud quick-path |
| Local engines: Ollama, MLX (macOS), Apple Foundation Models, Gemma.cpp, vLLM | YES — engine code | Installer pulls Ollama + starter model (`qwen3.5:2b` per install docs — README-claim) | Live inference **UNTESTED** here | Free / local | `src/openjarvis/engine/{ollama,apple_fm,gemma_cpp}.py`; `pyproject.toml` extras `inference-mlx`, `inference-vllm`, `inference-gemma`, `afm` |
| MCP: generic client/loader/server/transport + browser bridge | YES — code | External MCP servers via config (`tools.mcp.servers`); bridge allowlisted (see §2f) | Live consequential bridge call **UNTESTED** (README: refusal paths only) | Bridge MIT | `src/openjarvis/mcp/*.py` |

### 2e. Windows / WSL2 / macOS / Linux

| Platform | Implemented (installer/docs/code) | Plugin plan | Blocked / Untested | Evidence |
|---|---|---|---|---|
| macOS | YES — bash installer + docs + Keychain backend (`security` CLI) + launchd | — | Live macOS install/run **UNTESTED**; real Keychain backend untested per README | `docs/getting-started/install.md`, `macos.md`; `security/keychain.py` `MacOSKeychainBackend` |
| Linux | YES — bash installer + docs + Secret Service backend (`secret-tool`) + systemd | — | Live Linux systemd run **UNTESTED**; `secret-tool` backend untested (no keychain daemon in test VM per README) | `install.md`, `linux.md`; `keychain.py` Linux backend |
| WSL2 on Windows | YES — bash installer run inside Ubuntu + docs | **Recommended Windows path** per `windows-native.md` | Live WSL2 run **UNTESTED** | `install.md` WSL2 row; `docs/getting-started/wsl2.md` |
| Native Windows | YES — PowerShell installer (`install.ps1`) + scheduled-task service + Credential Vault backend (`CredReadW`/`CredWriteW` via ctypes) + docs marked "Phase-1" | — | **UNTESTED** — README: "Windows ctypes backend untested"; native Windows is Phase-1, WSL2 smoother per docs | `docs/getting-started/windows-native.md`; `keychain.py` Windows backend; `deploy/windows/` in wheel force-include |
| Desktop GUI | YES — code (Tauri `desktop/src-tauri`, `frontend/` Vite app) + release downloads claimed (.exe/.dmg/.deb/.rpm/.AppImage) | — | Live desktop build/run **UNTESTED**; release-download links are README/docs claims, not verified here | `desktop/`, `frontend/`; `docs/getting-started/installation.md` |
| Python support | `>=3.10,<3.14` (3.14 excluded: no numpy Windows wheels — `pyproject.toml` comment) | — | — | `pyproject.toml` `requires-python` |

**Gap:** Cross-platform support is installer/docs/code-level. No live run on
any of the four targets was performed in this pass; Keychain on all three OS
families is explicitly untested upstream in this fork's README.

### 2f. Four-language voice — Kannada, Hindi, English, Sanskrit

Source of truth: `src/openjarvis/speech/indic.py` (profiles state what the
code actually wires up; its own honesty rules forbid upgrading "forwarded"
into "supported"). Test counts below are README-stated, not re-run here.

| Language | STT | TTS (local) | Implemented (code) | Blocked / Untested | Evidence |
|---|---|---|---|---|---|
| English (`en`) | Forwarded-untested (`whisper_code="en"`) | Kokoro `lang_code="a"`, voice `af_heart` — **pipeline-untested** | YES — profile + Kokoro backend + faster-whisper/Deepgram/OpenAI-Whisper backends | No real mic/speaker/model/audio test in any language | `speech/indic.py` `VOICE_LANGUAGES["en"]`; `speech/kokoro_tts.py`; `speech/faster_whisper.py` |
| Hindi (`hi`) | Forwarded-untested (`"hi"`) | Kokoro `lang_code="h"` but **no curated voice ID** — pipeline-untested; operator must set `speech.voice_id` from installed Kokoro release | YES — profile only | No real Hindi audio/model test; no curated Hindi voice in repo | `indic.py` `VOICE_LANGUAGES["hi"]` |
| Kannada (`kn`) | Forwarded-untested (`"kn"` → Whisper) | **NO local pipeline** — Kokoro has no Kannada pipeline; repo curates no voice | YES — profile (explicitly unsupported for local TTS) | No real Kannada audio test; **local Kannada TTS does not exist** | `indic.py` `VOICE_LANGUAGES["kn"]` (`kokoro_lang_code=None`, `tts_status="no-local-pipeline"`) |
| Sanskrit (`sa`) | Forwarded-untested (`"sa"` → Whisper) — whether installed Whisper handles Sanskrit is **UNVERIFIED** | **NO local pipeline** — no backend has a Sanskrit pipeline or voice | YES — profile (explicitly unsupported for TTS) | No real Sanskrit audio test; do NOT claim Sanskrit speech works | `indic.py` `VOICE_LANGUAGES["sa"]` |

| Voice feature | Implemented | Plugin plan | Blocked / Untested |
|---|---|---|---|
| Push-to-talk state machine, sentence TTS, barge-in | YES — code (`speech/voice_state.py`, `voice_io.py`, `_voice_chat.py`) | — | Real audio **UNTESTED**; live-TTY barge-in mocked only (README) |
| Opt-in wake word ("jarvis") | YES — transcript spotter, **OFF by default**, local-only | Enable explicitly; never sends audio to cloud for wake-word | **Not wired into chat REPL**; not an always-on keyword model; costs one local transcription per window (per `indic.py`) |
| Indic QA (native-script, code-switch, names/numbers, cancellation/privacy) | YES — tests only (`tests/indic_qa/`) | — | README-stated: 71 passed, 5 xfailed; no real audio/model/device tests |
| Cloud TTS/STT (Deepgram, Cartesia, OpenAI TTS/Whisper) | YES — backend code, key-gated | Only when user explicitly configures provider + key | **UNTESTED**; **no paid/cloud TTS proposed** — cloud TTS is never claimed to work for a language on this module's say-so (`indic.py`) |
| Kokoro quirks | — | — | README: Kokoro has no Kannada/Sanskrit `lang_code` (falls back to American English); no explicit cancel token for in-flight extraction |

**Gap (largest voice gap):** There is **no verified local TTS for Kannada or
Sanskrit**, and no verified STT/TTS in any of the four languages with real
audio. A four-language voice claim today would be false. The honest shape is:
English/Hindi = local pipeline present-but-untested; Kannada/Sanskrit =
STT-code-forwarded-only, TTS missing. Closing this needs a new, explicitly
licensed TTS backend for Kannada/Sanskrit (not copying, not paid-by-default)
plus real-audio tests — none proposed here.

### 2g. Security / memory / MCP-browser (fork additions — README-stated status, code-confirmed shape)

| Area | Implemented | Plugin plan | Blocked / Untested | Evidence |
|---|---|---|---|---|
| Central single-use tool confirmation | YES — `ConfirmationGate`: approvals bound to exact tool + arguments, expiring, consumed on first use; no "approve everything" mode | — | No live desktop/server end-to-end agent run (TestClient-level only per README); TOCTOU window between path check and file open remains (documented in code) | `security/confirmation.py`; README Personal Build Status table |
| OS keychain vault (no file/plaintext fallback) | YES — backends per OS (see §2e) | — | Real keychain backends **UNTESTED**; legacy `.vault_key` migration has no direct test (README) | `security/keychain.py` ("NO file/plaintext fallback… fail closed") |
| Memory v1 (SQLite + FTS5 facts, scopes, supersede/correct/delete, ranked retrieval) | YES — `memory/sqlite_facts.py`, `service.py`, `store.py` | — | Benchmark is developer-only (README: 125 tests incl. 100-query benchmark — README-stated, not re-run); Rust doc backends, cross-process writers, large-corpus ranking, JSONL→SQLite migration untested; superseded text stays in DB status-filtered (only `forget` hard-deletes) | `memory/`; README table |
| MCP / browser via agentic-browser-bridge | YES — guarded stdio server entry | `bridge_server_entry()` builds `tools.mcp.servers` entry; default allowlist = read-only + reversible tools; navigation refused unless origin allowlisted (default loopback + `https://example.com`); consequential tools (click/type/navigate) need an operator confirmer or are refused fail-closed; native browser tools OFF by default | No real consequential bridge call end-to-end; no navigation beyond `about:blank` snapshot (README) | `mcp/browser_bridge.py` (`BRIDGE_READ_ONLY_TOOLS`, `BRIDGE_CONSEQUENTIAL_TOOLS`, `allowed_origins`) |
| Agents / skills / scheduler / A2A | YES — code (8 built-in agents per README: morning_digest, deep_research, monitor_operative, orchestrator, native_react, operative, native_openhands, simple; `agents/`, `skills/`, `scheduler`, `a2a/`) | Skills from Hermes / OpenClaw / GitHub resolvers (no copying) | Live multi-agent / scheduled runs **UNTESTED** here; skill counts are README-claims | `src/openjarvis/agents/`, `skills/`, `a2a/`; README Built-in Agents table |
| CI / workflows | — | — | **BLOCKED (known caveat):** `.github/workflows/` excluded from this fork's pushed history (token lacked `workflow` scope); CI files need restoration by someone with workflow scope (README) | README Known caveats |

---

## 3. Gaps that could NOT be verified (do not assume)

1. **No delivered-inventory file** found in `~/workspace` — nothing to
   reconcile against.
2. **Hermes runtime features** (gateway, pm, desktop, agent-browser,
   cua-driver behaviour) — only `install.sh` exists locally; no Hermes
   source, LICENSE, or skills tree inspected.
3. **Skill counts** ("~150 Hermes skills", "~13,700 OpenClaw skills") —
   README claims, not counted here; per-skill licences unchecked.
4. **Live behaviour everywhere**: no live Telegram send/receive, no live
   connector OAuth, no live shell/tool run, no live MCP bridge consequential
   call, no live desktop/server agent run, no live install on any OS, no
   real-audio voice test in any language.
5. **Licences**: all dependency licences; OpenClaw skills repo licence;
   Cactus `third_party/cactus/LICENSE` full text (README NOTICE only);
   StudyReels / paradox-agent / risklabs / tally-llm and other owner repos
   (no LICENSE detected — treated as unlicensed, not public domain).
6. **Test counts in README** (41 security, 125 memory, 45 MCP/browser,
   46 voice, 71 Indic QA) — README-stated; the 667 test files in
   `tests/` were counted by filename only, suites were **not** re-run here.
7. **Android control** — affirmatively absent from the Jarvis fork; no
   design, driver, or device test exists to verify.
8. **Kannada / Sanskrit local TTS** — affirmatively absent; no backend in
   the repo provides it.
9. **Private fork remote state** — `paradox-jarvis-ultra` is private; its
   remote contents were not inspected (only the local checkout + its
   `origin` remote URL). Nothing was pushed.

---

## 4. Rules for any follow-up build (binding constraints from this matrix)

- Keep upstream Apache-2.0 LICENSE + attribution in the fork; keep MIT
  notices on Bridge / Hermes / Cua artefacts.
- Do **not** copy code from Cactus (source-available), StudyReels,
  paradox-agent, risklabs, tally-llm, or any unlicensed repo into Jarvis.
- Do **not** propose paid services (cloud LLMs, cloud TTS/STT, Tavily paid
  tiers, SendBlue paid tiers, Cua Spaces cloud). Key-gated cloud paths stay
  opt-in, off by default, and are never the default.
- Hermes, Cua, and the browser bridge stay **external** (resolver / stdio /
  side-by-side process), never vendored into the fork.
- Owner-only Telegram = allowlist set + live-tested from the owner chat
  only; empty allowlist = not owner-only.
- System control stays gated (opt-in + per-action single-use approval);
  Android control and GUI automation do not exist — they need a new,
  explicitly approved, gated plugin, not a copy.
- Four-language voice must not be claimed until real-audio tests pass per
  language; Kannada/Sanskrit local TTS is a known missing backend.
- No "secure" / "ready" claim. Every feature above is code-present,
  plugin-planned, or blocked/untested as tabled.
