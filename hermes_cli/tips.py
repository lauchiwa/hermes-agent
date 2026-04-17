     1|"""Random tips shown at CLI session start to help users discover features."""
     2|
     3|import random
     4|
     5|
     6|# ---------------------------------------------------------------------------
     7|# Tip corpus — one-liners covering slash commands, CLI flags, config,
     8|# keybindings, tools, gateway, skills, profiles, and workflow tricks.
     9|# ---------------------------------------------------------------------------
    10|
    11|TIPS = [
    12|    # --- Slash Commands ---
    13|    "/btw <question> asks a quick side question without tools or history — great for clarifications.",
    14|    "/background <prompt> runs a task in a separate session while your current one stays free.",
    15|    "/branch forks the current session so you can explore a different direction without losing progress.",
    16|    "/compress manually compresses conversation context when things get long.",
    17|    "/rollback lists filesystem checkpoints — restore files the agent modified to any prior state.",
    18|    "/rollback diff 2 previews what changed since checkpoint 2 without restoring anything.",
    19|    "/rollback 2 src/file.py restores a single file from a specific checkpoint.",
    20|    "/title \"my project\" names your session — resume it later with /resume or hermes -c.",
    21|    "/resume picks up where you left off in a previously named session.",
    22|    "/queue <prompt> queues a message for the next turn without interrupting the current one.",
    23|    "/undo removes the last user/assistant exchange from the conversation.",
    24|    "/retry resends your last message — useful when the agent's response wasn't quite right.",
    25|    "/verbose cycles tool progress display: off → new → all → verbose.",
    26|    "/reasoning high increases the model's thinking depth. /reasoning show displays the reasoning.",
    27|    "/fast toggles priority processing for faster API responses (provider-dependent).",
    28|    "/yolo skips all dangerous command approval prompts for the rest of the session.",
    29|    "/model lets you switch models mid-session — try /model sonnet or /model gpt-5.",
    30|    "/model --global changes your default model permanently.",
    31|    "/personality pirate sets a fun personality — 14 built-in options from kawaii to shakespeare.",
    32|    "/skin changes the CLI theme — try ares, mono, slate, poseidon, or charizard.",
    33|    "/statusbar toggles a persistent bar showing model, tokens, context fill %, cost, and duration.",
    34|    "/tools disable browser temporarily removes browser tools for the current session.",
    35|    "/browser connect attaches browser tools to your running Chrome instance via CDP.",
    36|    "/plugins lists installed plugins and their status.",
    37|    "/cron manages scheduled tasks — set up recurring prompts with delivery to any platform.",
    38|    "/reload-mcp hot-reloads MCP server configuration without restarting.",
    39|    "/usage shows token usage, cost breakdown, and session duration.",
    40|    "/insights shows usage analytics for the last 30 days.",
    41|    "/paste checks your clipboard for an image and attaches it to your next message.",
    42|    "/profile shows which profile is active and its home directory.",
    43|    "/config shows your current configuration at a glance.",
    44|    "/stop kills all running background processes spawned by the agent.",
    45|
    46|    # --- @ Context References ---
    47|    "@file:path/to/file.py injects file contents directly into your message.",
    48|    "@file:main.py:10-50 injects only lines 10-50 of a file.",
    49|    "@folder:src/ injects a directory tree listing.",
    50|    "@diff injects your unstaged git changes into the message.",
    51|    "@staged injects your staged git changes (git diff --staged).",
    52|    "@git:5 injects the last 5 commits with full patches.",
    53|    "@url:https://example.com fetches and injects a web page's content.",
    54|    "Typing @ triggers filesystem path completion — navigate to any file interactively.",
    55|    "Combine multiple references: \"Review @file:main.py and @file:test.py for consistency.\"",
    56|
    57|    # --- Keybindings ---
    58|    "Alt+Enter (or Ctrl+J) inserts a newline for multi-line input.",
    59|    "Ctrl+C interrupts the agent. Double-press within 2 seconds to force exit.",
    60|    "Ctrl+Z suspends Hermes to the background — run fg in your shell to resume.",
    61|    "Tab accepts auto-suggestion ghost text or autocompletes slash commands.",
    62|    "Type a new message while the agent is working to interrupt and redirect it.",
    63|    "Alt+V pastes an image from your clipboard into the conversation.",
    64|    "Pasting 5+ lines auto-saves to a file and inserts a compact reference instead.",
    65|
    66|    # --- CLI Flags ---
    67|    "hermes -c resumes your most recent CLI session. hermes -c \"project name\" resumes by title.",
    68|    "hermes -w creates an isolated git worktree — perfect for parallel agent workflows.",
    69|    "hermes -w -q \"Fix issue #42\" combines worktree isolation with a one-shot query.",
    70|    "hermes chat -t web,terminal enables only specific toolsets for a focused session.",
    71|    "hermes chat -s github-pr-workflow preloads a skill at launch.",
    72|    "hermes chat -q \"query\" runs a single non-interactive query and exits.",
    73|    "hermes chat --max-turns 200 overrides the default 90-iteration limit per turn.",
    74|    "hermes chat --checkpoints enables filesystem snapshots before every destructive file change.",
    75|    "hermes --yolo bypasses all dangerous command approval prompts for the entire session.",
    76|    "hermes chat --source telegram tags the session for filtering in hermes sessions list.",
    77|    "hermes -p work chat runs under a specific profile without changing your default.",
    78|
    79|    # --- CLI Subcommands ---
    80|    "hermes doctor --fix diagnoses and auto-repairs config and dependency issues.",
    81|    "hermes dump outputs a compact setup summary — great for bug reports.",
    82|    "hermes config set KEY VALUE auto-routes secrets to .env and everything else to config.yaml.",
    83|    "hermes config edit opens config.yaml in your default editor.",
    84|    "hermes config check scans for missing or stale configuration options.",
    85|    "hermes sessions browse opens an interactive session picker with search.",
    86|    "hermes sessions stats shows session counts by platform and database size.",
    87|    "hermes sessions prune --older-than 30 cleans up old sessions.",
    88|    "hermes skills search react --source skills-sh searches the skills.sh public directory.",
    89|    "hermes skills check scans installed hub skills for upstream updates.",
    90|    "hermes skills tap add myorg/skills-repo adds a custom GitHub skill source.",
    91|    "hermes skills snapshot export setup.json exports your skill configuration for backup or sharing.",
    92|    "hermes mcp add github --command npx adds MCP servers from the command line.",
    93|    "hermes mcp serve runs Hermes itself as an MCP server for other agents.",
    94|    "hermes auth add lets you add multiple API keys for credential pool rotation.",
    95|    "hermes completion bash >> ~/.bashrc enables tab completion for all commands and profiles.",
    96|    "hermes logs -f follows agent.log in real time. --level WARNING --since 1h filters output.",
    97|    "hermes backup creates a zip backup of your entire Hermes home directory.",
    98|    "hermes profile create coder creates an isolated profile that becomes its own command.",
    99|    "hermes profile create work --clone copies your current config and keys to a new profile.",
   100|    "hermes update syncs new bundled skills to ALL profiles automatically.",
   101|    "hermes gateway install sets up Hermes as a system service (systemd/launchd).",
   102|    "hermes memory setup lets you configure an external memory provider (Honcho, Mem0, etc.).",
   103|    "hermes webhook subscribe creates event-driven webhook routes with HMAC validation.",
   104|
   105|    # --- Configuration ---
   106|    "Set display.bell_on_complete: true in config.yaml to hear a bell when long tasks finish.",
   107|    "Set display.streaming: true to see tokens appear in real time as the model generates.",
   108|    "Set display.show_reasoning: true to watch the model's chain-of-thought reasoning.",
   109|    "Set display.compact: true to reduce whitespace in output for denser information.",
   110|    "Set display.busy_input_mode: queue to queue messages instead of interrupting the agent.",
   111|    "Set display.resume_display: minimal to skip the full conversation recap on session resume.",
   112|    "Set compression.threshold: 0.50 to control when auto-compression fires (default: 50% of context).",
   113|    "Set agent.max_turns: 200 to let the agent take more tool-calling steps per turn.",
   114|    "Set file_read_max_chars: 200000 to increase the max content per read_file call.",
   115|    "Set approvals.mode: smart to let an LLM auto-approve safe commands and auto-deny dangerous ones.",
   116|    "Set fallback_model in config.yaml to automatically fail over to a backup provider.",
   117|    "Set privacy.redact_pii: true to hash user IDs and phone numbers before sending to the LLM.",
   118|    "Set browser.record_sessions: true to auto-record browser sessions as WebM videos.",
   119|    "Set worktree: true in config.yaml to always create a git worktree (same as hermes -w).",
   120|    "Set security.website_blocklist.enabled: true to block specific domains from web tools.",
   121|    "Set cron.wrap_response: false to deliver raw agent output without the cron header/footer.",
   122|    "HERMES_TIMEZONE overrides the server timezone with any IANA timezone string.",
   123|    "Environment variable substitution works in config.yaml: use ${VAR_NAME} syntax.",
   124|    "Quick commands in config.yaml run shell commands instantly with zero token usage.",
   125|    "Custom personalities can be defined in config.yaml under agent.personalities.",
   126|    "provider_routing controls OpenRouter provider sorting, whitelisting, and blacklisting.",
   127|
   128|    # --- Tools & Capabilities ---
   129|    "execute_code runs Python scripts that call Hermes tools programmatically — results stay out of context.",
   130|    "delegate_task spawns up to 3 concurrent sub-agents with isolated contexts for parallel work.",
   131|    "web_extract works on PDF URLs — pass any PDF link and it converts to markdown.",
   132|    "search_files is ripgrep-backed and faster than grep — use it instead of terminal grep.",
   133|    "patch uses 9 fuzzy matching strategies so minor whitespace differences won't break edits.",
   134|    "patch supports V4A format for bulk multi-file edits in a single call.",
   135|    "read_file suggests similar filenames when a file isn't found.",
   136|    "read_file auto-deduplicates — re-reading an unchanged file returns a lightweight stub.",
   137|    "browser_vision takes a screenshot and analyzes it with AI — works for CAPTCHAs and visual content.",
   138|    "browser_console can evaluate JavaScript expressions in the page context.",
   139|    "image_generate creates images with FLUX 2 Pro and automatic 2x upscaling.",
   140|    "text_to_speech converts text to audio — plays as voice bubbles on Telegram.",
   141|    "send_message can reach any connected messaging platform from within a session.",
   142|    "The todo tool helps the agent track complex multi-step tasks during a session.",
   143|    "session_search performs full-text search across ALL past conversations.",
   144|    "The agent automatically saves preferences, corrections, and environment facts to memory.",
   145|    "mixture_of_agents routes hard problems through 4 frontier LLMs collaboratively.",
   146|    "Terminal commands support background mode with notify_on_complete for long-running tasks.",
   147|    "Terminal background processes support watch_patterns to alert on specific output lines.",
   148|    "The terminal tool supports 6 backends: local, Docker, SSH, Modal, Daytona, and Singularity.",
   149|
   150|    # --- Profiles ---
   151|    "Each profile gets its own config, API keys, memory, sessions, skills, and cron jobs.",
   152|    "Profile names become shell commands — 'hermes profile create coder' creates the 'coder' command.",
   153|    "hermes profile export coder -o backup.tar.gz creates a portable profile archive.",
   154|    "If two profiles accidentally share a bot token, the second gateway is blocked with a clear error.",
   155|
   156|    # --- Sessions ---
   157|    "Sessions auto-generate descriptive titles after the first exchange — no manual naming needed.",
   158|    "Session titles support lineage: \"my project\" → \"my project #2\" → \"my project #3\".",
   159|    "When exiting, Hermes prints a resume command with session ID and stats.",
   160|    "hermes sessions export backup.jsonl exports all sessions for backup or analysis.",
   161|    "hermes -r SESSION_ID resumes any specific past session by its ID.",
   162|
   163|    # --- Memory ---
   164|    "Memory is a frozen snapshot — changes appear in the system prompt only at next session start.",
   165|    "Memory entries are automatically scanned for prompt injection and exfiltration patterns.",
   166|    "The agent has two memory stores: personal notes (~2200 chars) and user profile (~1375 chars).",
   167|    "Corrections you give the agent (\"no, do it this way\") are often auto-saved to memory.",
   168|
   169|    # --- Skills ---
   170|    "Over 80 bundled skills covering github, creative, mlops, productivity, research, and more.",
   171|    "Every installed skill automatically becomes a slash command — type / to see them all.",
   172|    "hermes skills install official/security/1password installs optional skills from the repo.",
   173|    "Skills can restrict to specific OS platforms — some only load on macOS or Linux.",
   174|    "skills.external_dirs in config.yaml lets you load skills from custom directories.",
   175|    "The agent can create its own skills as procedural memory using skill_manage.",
   176|    "The plan skill saves markdown plans under .hermes/plans/ in the active workspace.",
   177|
   178|    # --- Cron & Scheduling ---
   179|    "Cron jobs can attach skills: hermes cron add --skill blogwatcher \"Check for new posts\".",
   180|    "Cron delivery targets include telegram, discord, slack, email, sms, and 12+ more platforms.",
   181|    "If a cron response starts with [SILENT], delivery is suppressed — useful for monitoring-only jobs.",
   182|    "Cron supports relative delays (30m), intervals (every 2h), cron expressions, and ISO timestamps.",
   183|    "Cron jobs run in completely fresh agent sessions — prompts must be self-contained.",
   184|
   185|    # --- Voice ---
   186|    "Voice mode works with zero API keys if faster-whisper is installed (free local speech-to-text).",
   187|    "Five TTS providers available: Edge TTS (free), ElevenLabs, OpenAI, NeuTTS (free local), MiniMax.",
   188|    "/voice on enables voice mode in the CLI. Ctrl+B toggles push-to-talk recording.",
   189|    "Streaming TTS plays sentences as they generate — you don't wait for the full response.",
   190|    "Voice messages on Telegram, Discord, WhatsApp, and Slack are auto-transcribed.",
   191|
   192|    # --- Gateway & Messaging ---
   193|    "Hermes runs on 18 platforms: Telegram, Discord, Slack, WhatsApp, Signal, Matrix, email, and more.",
   194|    "hermes gateway install sets it up as a system service that starts on boot.",
   195|    "DingTalk uses Stream Mode — no webhooks or public URL needed.",
   196|    "BlueBubbles brings iMessage to Hermes via a local macOS server.",
   197|    "Webhook routes support HMAC validation, rate limiting, and event filtering.",
   198|    "The API server exposes an OpenAI-compatible endpoint compatible with Open WebUI and LibreChat.",
   199|    "Discord voice channel mode: the bot joins VC, transcribes speech, and talks back.",
   200|    "group_sessions_per_user: true gives each person their own session in group chats.",
   201|    "/sethome marks a chat as the home channel for cron job deliveries.",
   202|    "The gateway supports inactivity-based timeouts — active agents can run indefinitely.",
   203|
   204|    # --- Security ---
   205|    "Dangerous command approval has 4 tiers: once, session, always (permanent allowlist), deny.",
   206|    "Smart approval mode uses an LLM to auto-approve safe commands and flag dangerous ones.",
   207|    "SSRF protection blocks private networks, loopback, link-local, and cloud metadata addresses.",
   208|    "Tirith pre-exec scanning detects homograph URL spoofing and pipe-to-interpreter patterns.",
   209|    "MCP subprocesses receive a filtered environment — only safe system vars pass through.",
   210|    "Context files (.hermes.md, AGENTS.md) are security-scanned for prompt injection before loading.",
   211|    "command_allowlist in config.yaml permanently approves specific shell command patterns.",
   212|
   213|    # --- Context & Compression ---
   214|    "Context auto-compresses when it reaches the threshold — memories are flushed and history summarized.",
   215|    "The status bar turns yellow, then orange, then red as context fills up.",
   216|    "SOUL.md at ~/.hermes/SOUL.md is the agent's primary identity — customize it to shape behavior.",
   217|    "Hermes loads project context from .hermes.md, AGENTS.md, CLAUDE.md, or .cursorrules (first match).",
   218|    "Subdirectory AGENTS.md files are discovered progressively as the agent navigates into folders.",
   219|    "Context files are capped at 20,000 characters with smart head/tail truncation.",
   220|
   221|    # --- Browser ---
   222|    "Five browser providers: local Chromium, Browserbase, Browser Use, Camofox, and Firecrawl.",
   223|    "Camofox is an anti-detection browser — Firefox fork with C++ fingerprint spoofing.",
   224|    "browser_navigate returns a page snapshot automatically — no need to call browser_snapshot after.",
   225|    "browser_vision with annotate=true overlays numbered labels on interactive elements.",
   226|
   227|    # --- MCP ---
   228|    "MCP servers are configured in config.yaml — both stdio and HTTP transports supported.",
   229|    "Per-server tool filtering: tools.include whitelists and tools.exclude blacklists specific tools.",
   230|    "MCP servers auto-generate toolsets at runtime — hermes tools can toggle them per platform.",
   231|    "MCP OAuth support: auth: oauth enables browser-based authorization with PKCE.",
   232|
   233|    # --- Checkpoints & Rollback ---
   234|    "Checkpoints have zero overhead when no files are modified — enabled by default.",
   235|    "A pre-rollback snapshot is saved automatically so you can undo the undo.",
   236|    "/rollback also undoes the conversation turn, so the agent doesn't remember rolled-back changes.",
   237|    "Checkpoints use shadow repos in ~/.hermes/checkpoints/ — your project's .git is never touched.",
   238|
   239|    # --- Batch & Data ---
   240|    "batch_runner.py processes hundreds of prompts in parallel for training data generation.",
   241|    "hermes chat -Q enables quiet mode for programmatic use — suppresses banner and spinner.",
   242|    "Trajectory saving (--save-trajectories) captures full tool-use traces for model training.",
   243|
   244|    # --- Plugins ---
   245|    "Three plugin types: general (tools/hooks), memory providers, and context engines.",
   246|    "hermes plugins install owner/repo installs plugins directly from GitHub.",
   247|    "8 external memory providers available: Honcho, OpenViking, Mem0, Hindsight, and more.",
   248|    "Plugin hooks include pre_tool_call, post_tool_call, pre_llm_call, and post_llm_call.",
   249|
   250|    # --- Miscellaneous ---
   251|    "Prompt caching (Anthropic) reduces costs by reusing cached system prompt prefixes.",
   252|    "The agent auto-generates session titles in a background thread — zero latency impact.",
   253|    "Smart model routing can auto-route simple queries to a cheaper model.",
   254|    "Slash commands support prefix matching: /h resolves to /help, /mod to /model.",
   255|    "Dragging a file path into the terminal auto-attaches images or sends as context.",
   256|    ".worktreeinclude in your repo root lists gitignored files to copy into worktrees.",
   257|    "hermes acp runs Hermes as an ACP server for VS Code, Zed, and JetBrains integration.",
   258|    "Custom providers: save named endpoints in config.yaml under custom_providers.",
   259|    "HERMES_EPHEMERAL_SYSTEM_PROMPT injects a system prompt that's never persisted to history.",
   260|    "credential_pool_strategies supports fill_first, round_robin, least_used, and random rotation.",
   261|    "hermes login supports OAuth-based auth for Nous and OpenAI Codex providers.",
   262|    "The API server supports both Chat Completions and Responses API with server-side state.",
   263|    "tool_preview_length: 0 in config shows full file paths in the spinner's activity feed.",
   264|    "hermes status --deep runs deeper diagnostic checks across all components.",
   265|
   266|    # --- Hidden Gems & Power-User Tricks ---
   267|    "BOOT.md at ~/.hermes/BOOT.md runs automatically on every gateway start — use it for startup checks.",
   268|    "Cron jobs can attach a Python script (--script) whose stdout is injected into the prompt as context.",
   269|    "Cron scripts live in ~/.hermes/scripts/ and run before the agent — perfect for data collection pipelines.",
   270|    "prefill_messages_file in config.yaml injects few-shot examples into every API call, never saved to history.",
   271|    "SOUL.md completely replaces the agent's default identity — rewrite it to make Hermes your own.",
   272|    "SOUL.md is auto-seeded with a default personality on first run. Edit ~/.hermes/SOUL.md to customize.",
   273|    "/compress <focus topic> allocates 60-70% of the summary budget to your topic and aggressively trims the rest.",
   274|    "On second+ compression, the compressor updates the previous summary instead of starting from scratch.",
   275|    "Before a gateway session reset, Hermes auto-flushes important facts to memory in the background.",
   276|    "network.force_ipv4: true in config.yaml fixes hangs on servers with broken IPv6 — monkey-patches socket.",
   277|    "The terminal tool annotates common exit codes: grep returning 1 = 'No matches found (not an error)'.",
   278|    "Failed foreground terminal commands auto-retry up to 3 times with exponential backoff (2s, 4s, 8s).",
   279|    "Bare sudo commands are auto-rewritten to pipe SUDO_PASSWORD from .env — no interactive prompt needed.",
   280|    "execute_code has built-in helpers: json_parse() for tolerant parsing, shell_quote(), and retry() with backoff.",
   281|    "execute_code's 7 sandbox tools (web_search, terminal, read/write/search/patch) use RPC — never enter context.",
   282|    "Reading the same file region 3+ times triggers a warning. At 4+, it's hard-blocked to prevent loops.",
   283|    "write_file and patch detect if a file was externally modified since the last read and warn about staleness.",
   284|    "V4A patch format supports Add File, Delete File, and Move File directives — not just Update.",
   285|    "MCP servers can request LLM completions back via sampling — the agent becomes a tool for the server.",
   286|    "MCP servers send notifications/tools/list_changed to trigger automatic tool re-registration without restart.",
   287|    "delegate_task with acp_command: 'claude' spawns Claude Code as a child agent from any platform.",
   288|    "Delegation has a heartbeat thread — child activity propagates to the parent, preventing gateway timeouts.",
   289|    "When a provider returns HTTP 402 (payment required), the auxiliary client auto-falls back to the next one.",
   290|    "agent.tool_use_enforcement steers models that describe actions instead of calling tools — auto for GPT/Codex.",
   291|    "agent.restart_drain_timeout (default 60s) lets running agents finish before a gateway restart takes effect.",
   292|    "The gateway caches AIAgent instances per session — destroying this cache breaks Anthropic prompt caching.",
   293|    "Any website can expose skills via /.well-known/skills/index.json — the skills hub discovers them automatically.",
   294|    "The skills audit log at ~/.hermes/skills/.hub/audit.log tracks every install and removal operation.",
   295|    "Stale git worktrees are auto-cleaned: 24-72h old with no unpushed commits get pruned on startup.",
   296|    "Each profile gets its own subprocess HOME at HERMES_HOME/home/ — isolated git, ssh, npm, gh configs.",
   297|    "HERMES_HOME_MODE env var (octal, e.g. 0701) sets custom directory permissions for web server traversal.",
   298|    "Container mode: place .container-mode in HERMES_HOME and the host CLI auto-execs into the container.",
   299|    "Ctrl+C has 5 priority tiers: cancel recording → cancel prompts → cancel picker → interrupt agent → exit.",
   300|    "Every interrupt during an agent run is logged to ~/.hermes/interrupt_debug.log with timestamps.",
   301|    "BROWSER_CDP_URL connects browser tools to any running Chrome — accepts WebSocket, HTTP, or host:port.",
   302|    "BROWSERBASE_ADVANCED_STEALTH=true enables advanced anti-detection with custom Chromium (Scale Plan).",
   303|    "The CLI auto-switches to compact mode in terminals narrower than 80 columns.",
   304|    "Quick commands support two types: exec (run shell command directly) and alias (redirect to another command).",
   305|    "Per-task delegation model: delegation.model and delegation.provider in config route subagents to cheaper models.",
   306|    "delegation.reasoning_effort independently controls thinking depth for subagents.",
   307|    "display.platforms in config.yaml allows per-platform display overrides: {telegram: {tool_progress: all}}.",
   308|    "human_delay.mode in config simulates human typing speed — configurable min_ms/max_ms range.",
   309|    "Config version migrations run automatically on load — new config keys appear without manual intervention.",
   310|    "GPT and Codex models get special system prompt guidance for tool discipline and mandatory tool use.",
   311|    "Gemini models get tailored directives for absolute paths, parallel tool calls, and non-interactive commands.",
   312|    "context.engine in config.yaml can be set to a plugin name for alternative context management strategies.",
   313|    "Browser pages over 8000 tokens are auto-summarized by the auxiliary LLM before returning to the agent.",
   314|    "The compressor does a cheap pre-pass: tool outputs over 200 chars are replaced with placeholders before the LLM runs.",
   315|    "When compression fails, further attempts are paused for 10 minutes to avoid API hammering.",
   316|    "Long dangerous commands (>70 chars) get a 'view' option in the approval prompt to see the full text first.",
   317|    "Audio level visualization shows ▁▂▃▄▅▆▇ bars during voice recording based on microphone RMS levels.",
   318|    "Profile names cannot collide with existing PATH binaries — 'hermes profile create ls' would be rejected.",
   319|    "hermes profile create backup --clone-all copies everything (config, keys, SOUL.md, memories, skills, sessions).",
   320|    "The voice record key is configurable via voice.record_key in config.yaml — not just Ctrl+B.",
   321|    ".cursorrules and .cursor/rules/*.mdc files are auto-detected and loaded as project context.",
   322|    "Context files support 10+ prompt injection patterns — invisible Unicode, 'ignore instructions', exfil attempts.",
   323|    "GPT-5 and Codex use 'developer' role instead of 'system' in the message format.",
   324|    "Per-task auxiliary overrides: auxiliary.vision.provider, auxiliary.compression.model, etc. in config.yaml.",
   325|    "The auxiliary client treats 'main' as a provider alias — resolves to your actual primary provider + model.",
   326|    "Smart routing can auto-route simple queries to a cheaper model — set smart_model_routing.enabled: true.",
   327|    "hermes claw migrate --dry-run previews OpenClaw migration without writing anything.",
   328|    "File paths pasted with quotes or escaped spaces are handled automatically — no manual cleanup needed.",
   329|    "Slash commands never trigger the large-paste collapse — /command with big arguments works correctly.",
   330|    "In interrupt mode, slash commands typed during agent execution bypass interrupt logic and run immediately.",
   331|    "HERMES_DEV=1 bypasses container mode detection for local development.",
   332|    "Each MCP server gets its own toolset (mcp-servername) that can be toggled independently via hermes tools.",
   333|    "MCP ${ENV_VAR} placeholders in config are resolved at server spawn — including vars from ~/.hermes/.env.",
   334|    "Skills from trusted repos (NousResearch) get a 'trusted' security level; community skills get extra scanning.",
   335|    "The skills quarantine at ~/.hermes/skills/.hub/quarantine/ holds skills pending security review.",
   336|]
   337|
   338|
   339|def get_random_tip(exclude_recent: int = 0) -> str:
   340|    """Return a random tip string.
   341|
   342|    Args:
   343|        exclude_recent: not used currently; reserved for future
   344|            deduplication across sessions.
   345|    """
   346|    return random.choice(TIPS)
   347|
   348|
   349|
   350|
