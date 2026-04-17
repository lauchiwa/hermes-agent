     1|# Hermes Agent Has Had "Routines" Since March
     2|
     3|Anthropic just announced [Claude Code Routines](https://claude.com/blog/introducing-routines-in-claude-code) — scheduled tasks, GitHub event triggers, and API-triggered agent runs. Bundled prompt + repo + connectors, running on their infrastructure.
     4|
     5|It's a good feature. We shipped it two months ago.
     6|
     7|---
     8|
     9|## The Three Trigger Types — Side by Side
    10|
    11|Claude Code Routines offers three ways to trigger an automation:
    12|
    13|**1. Scheduled (cron)**
    14|> "Every night at 2am: pull the top bug from Linear, attempt a fix, and open a draft PR."
    15|
    16|Hermes equivalent — works today:
    17|```bash
    18|hermes cron create "0 2 * * *" \
    19|  "Pull the top bug from the issue tracker, attempt a fix, and open a draft PR." \
    20|  --name "Nightly bug fix" \
    21|  --deliver telegram
    22|```
    23|
    24|**2. GitHub Events (webhook)**
    25|> "Flag PRs that touch the /auth-provider module and post to #auth-changes."
    26|
    27|Hermes equivalent — works today:
    28|```bash
    29|hermes webhook subscribe auth-watch \
    30|  --events "pull_request" \
    31|  --prompt "PR #{pull_request.number}: {pull_request.title} by {pull_request.user.login}. Check if it touches the auth-provider module. If yes, summarize the changes." \
    32|  --deliver slack
    33|```
    34|
    35|**3. API Triggers**
    36|> "Read the alert payload, find the owning service, post a triage summary to #oncall."
    37|
    38|Hermes equivalent — works today:
    39|```bash
    40|hermes webhook subscribe alert-triage \
    41|  --prompt "Alert: {alert.name} — Severity: {alert.severity}. Find the owning service, investigate, and post a triage summary with proposed first steps." \
    42|  --deliver slack
    43|```
    44|
    45|Every use case in their blog post — backlog triage, docs drift, deploy verification, alert correlation, library porting, bespoke PR review — has a working Hermes implementation. No new features needed. It's been shipping since March 2026.
    46|
    47|---
    48|
    49|## What's Different
    50|
    51|| | Claude Code Routines | Hermes Agent |
    52||---|---|---|
    53|| **Scheduled tasks** | ✅ Schedule-based | ✅ Any cron expression + human-readable intervals |
    54|| **GitHub triggers** | ✅ PR, issue, push events | ✅ Any GitHub event via webhook subscriptions |
    55|| **API triggers** | ✅ POST to unique endpoint | ✅ POST to webhook routes with HMAC auth |
    56|| **MCP connectors** | ✅ Native connectors | ✅ Full MCP client support |
    57|| **Script pre-processing** | ❌ | ✅ Python scripts run before agent, inject context |
    58|| **Skill chaining** | ❌ | ✅ Load multiple skills per automation |
    59|| **Daily limit** | 5-25 runs/day | **Unlimited** |
    60|| **Model choice** | Claude only | **Any model** — Claude, GPT, Gemini, DeepSeek, Qwen, local |
    61|| **Delivery targets** | GitHub comments | Telegram, Discord, Slack, SMS, email, GitHub comments, webhooks, local files |
    62|| **Infrastructure** | Anthropic's servers | **Your infrastructure** — VPS, home server, laptop |
    63|| **Data residency** | Anthropic's cloud | **Your machines** |
    64|| **Cost** | Pro/Max/Team/Enterprise subscription | Your API key, your rates |
    65|| **Open source** | No | **Yes** — MIT license |
    66|
    67|---
    68|
    69|## Things Hermes Does That Routines Can't
    70|
    71|### Script Injection
    72|
    73|Run a Python script *before* the agent. The script's stdout becomes context. The script handles mechanical work (fetching, diffing, computing); the agent handles reasoning.
    74|
    75|```bash
    76|hermes cron create "every 1h" \
    77|  "If CHANGE DETECTED, summarize what changed. If NO_CHANGE, respond with [SILENT]." \
    78|  --script ~/.hermes/scripts/watch-site.py \
    79|  --name "Pricing monitor" \
    80|  --deliver telegram
    81|```
    82|
    83|The `[SILENT]` pattern means you only get notified when something actually happens. No spam.
    84|
    85|### Multi-Skill Workflows
    86|
    87|Chain specialized skills together. Each skill teaches the agent a specific capability, and the prompt ties them together.
    88|
    89|```bash
    90|hermes cron create "0 8 * * *" \
    91|  "Search arXiv for papers on language model reasoning. Save the top 3 as Obsidian notes." \
    92|  --skills "arxiv,obsidian" \
    93|  --name "Paper digest"
    94|```
    95|
    96|### Deliver Anywhere
    97|
    98|One automation, any destination:
    99|
   100|```bash
   101|--deliver telegram                      # Telegram home channel
   102|--deliver discord                       # Discord home channel
   103|--deliver slack                         # Slack channel
   104|--deliver sms:+155****4567              # Text message
   105|--deliver telegram:-1001234567890:42    # Specific Telegram forum topic
   106|--deliver local                         # Save to file, no notification
   107|```
   108|
   109|### Model-Agnostic
   110|
   111|Your nightly triage can run on Claude. Your deploy verification can run on GPT. Your cost-sensitive monitors can run on DeepSeek or a local model. Same automation system, any backend.
   112|
   113|---
   114|
   115|## The Limits Tell the Story
   116|
   117|Claude Code Routines: **5 routines per day** on Pro. **25 on Enterprise.** That's their ceiling.
   118|
   119|Hermes has no daily limit. Run 500 automations a day if you want. The only constraint is your API budget, and you choose which models to use for which tasks.
   120|
   121|A nightly backlog triage on Sonnet costs roughly $0.02-0.05. A monitoring check on DeepSeek costs fractions of a cent. You control the economics.
   122|
   123|---
   124|
   125|## Get Started
   126|
   127|Hermes Agent is open source and free. The automation infrastructure — cron scheduler, webhook platform, skill system, multi-platform delivery — is built in.
   128|
   129|```bash
   130|pip install hermes-agent
   131|hermes setup
   132|```
   133|
   134|Set up a scheduled task in 30 seconds:
   135|```bash
   136|hermes cron create "0 9 * * 1" \
   137|  "Generate a weekly AI news digest. Search the web for major announcements, trending repos, and notable papers. Keep it under 500 words with links." \
   138|  --name "Weekly digest" \
   139|  --deliver telegram
   140|```
   141|
   142|Set up a GitHub webhook in 60 seconds:
   143|```bash
   144|hermes gateway setup    # enable webhooks
   145|hermes webhook subscribe pr-review \
   146|  --events "pull_request" \
   147|  --prompt "Review PR #{pull_request.number}: {pull_request.title}" \
   148|  --skills "github-code-review" \
   149|  --deliver github_comment
   150|```
   151|
   152|Full automation templates gallery: [hermes-agent.nousresearch.com/docs/guides/automation-templates](https://hermes-agent.nousresearch.com/docs/guides/automation-templates)
   153|
   154|Documentation: [hermes-agent.nousresearch.com](https://hermes-agent.nousresearch.com)
   155|
   156|GitHub: [github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
   157|
   158|---
   159|
   160|*Hermes Agent is built by [Nous Research](https://nousresearch.com). Open source, model-agnostic, runs on your infrastructure.*
   161|
