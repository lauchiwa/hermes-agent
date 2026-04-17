     1|---
     2|sidebar_position: 7
     3|title: "Docker"
     4|description: "Running Hermes Agent in Docker and using Docker as a terminal backend"
     5|---
     6|
     7|# Hermes Agent — Docker
     8|
     9|There are two distinct ways Docker intersects with Hermes Agent:
    10|
    11|1. **Running Hermes IN Docker** — the agent itself runs inside a container (this page's primary focus)
    12|2. **Docker as a terminal backend** — the agent runs on your host but executes commands inside a Docker sandbox (see [Configuration → terminal.backend](./configuration.md))
    13|
    14|This page covers option 1. The container stores all user data (config, API keys, sessions, skills, memories) in a single directory mounted from the host at `/opt/data`. The image itself is stateless and can be upgraded by pulling a new version without losing any configuration.
    15|
    16|## Quick start
    17|
    18|If this is your first time running Hermes Agent, create a data directory on the host and start the container interactively to run the setup wizard:
    19|
    20|```sh
    21|mkdir -p ~/.hermes
    22|docker run -it --rm \
    23|  -v ~/.hermes:/opt/data \
    24|  nousresearch/hermes-agent setup
    25|```
    26|
    27|This drops you into the setup wizard, which will prompt you for your API keys and write them to `~/.hermes/.env`. You only need to do this once. It is highly recommended to set up a chat system for the gateway to work with at this point.
    28|
    29|## Running in gateway mode
    30|
    31|Once configured, run the container in the background as a persistent gateway (Telegram, Discord, Slack, WhatsApp, etc.):
    32|
    33|```sh
    34|docker run -d \
    35|  --name hermes \
    36|  --restart unless-stopped \
    37|  -v ~/.hermes:/opt/data \
    38|  -p 8642:8642 \
    39|  nousresearch/hermes-agent gateway run
    40|```
    41|
    42|Port 8642 exposes the gateway's [OpenAI-compatible API server](./api-server.md) and health endpoint. It's optional if you only use chat platforms (Telegram, Discord, etc.), but required if you want the dashboard or external tools to reach the gateway.
    43|
    44|Opening any port on an internet facing machine is a security risk. You should not do it unless you understand the risks.
    45|
    46|## Running the dashboard
    47|
    48|The built-in web dashboard can run alongside the gateway as a separate container.
    49|
    50|To run the dashboard as its own container, point it at the gateway's health endpoint so it can detect gateway status across containers:
    51|
    52|```sh
    53|docker run -d \
    54|  --name hermes-dashboard \
    55|  --restart unless-stopped \
    56|  -v ~/.hermes:/opt/data \
    57|  -p 9119:9119 \
    58|  -e GATEWAY_HEALTH_URL=http://$HOST_IP:8642 \
    59|  nousresearch/hermes-agent dashboard
    60|```
    61|
    62|Replace `$HOST_IP` with the IP address of the machine running the gateway container (e.g. `192.168.1.100`), or use a Docker network hostname if both containers share a network (see the [Compose example](#docker-compose-example) below).
    63|
    64|| Environment variable | Description | Default |
    65||---------------------|-------------|---------|
    66|| `GATEWAY_HEALTH_URL` | Base URL of the gateway's API server, e.g. `http://gateway:8642` | *(unset — local PID check only)* |
    67|| `GATEWAY_HEALTH_TIMEOUT` | Health probe timeout in seconds | `3` |
    68|
    69|Without `GATEWAY_HEALTH_URL`, the dashboard falls back to local process detection — which only works when the gateway runs in the same container or on the same host.
    70|
    71|## Running interactively (CLI chat)
    72|
    73|To open an interactive chat session against a running data directory:
    74|
    75|```sh
    76|docker run -it --rm \
    77|  -v ~/.hermes:/opt/data \
    78|  nousresearch/hermes-agent
    79|```
    80|
    81|## Persistent volumes
    82|
    83|The `/opt/data` volume is the single source of truth for all Hermes state. It maps to your host's `~/.hermes/` directory and contains:
    84|
    85|| Path | Contents |
    86||------|----------|
    87|| `.env` | API keys and secrets |
    88|| `config.yaml` | All Hermes configuration |
    89|| `SOUL.md` | Agent personality/identity |
    90|| `sessions/` | Conversation history |
    91|| `memories/` | Persistent memory store |
    92|| `skills/` | Installed skills |
    93|| `cron/` | Scheduled job definitions |
    94|| `hooks/` | Event hooks |
    95|| `logs/` | Runtime logs |
    96|| `skins/` | Custom CLI skins |
    97|
    98|:::warning
    99|Never run two Hermes **gateway** containers against the same data directory simultaneously — session files and memory stores are not designed for concurrent write access. Running a dashboard container alongside the gateway is safe since the dashboard only reads data.
   100|:::
   101|
   102|## Environment variable forwarding
   103|
   104|API keys are read from `/opt/data/.env` inside the container. You can also pass environment variables directly:
   105|
   106|```sh
   107|docker run -it --rm \
   108|  -v ~/.hermes:/opt/data \
   109|  -e ANTHROPIC_API_KEY="***" \
   110|  -e OPENAI_API_KEY="***" \
   111|  nousresearch/hermes-agent
   112|```
   113|
   114|Direct `-e` flags override values from `.env`. This is useful for CI/CD or secrets-manager integrations where you don't want keys on disk.
   115|
   116|## Docker Compose example
   117|
   118|For persistent deployment with both the gateway and dashboard, a `docker-compose.yaml` is convenient:
   119|
   120|```yaml
   121|services:
   122|  hermes:
   123|    image: nousresearch/hermes-agent:latest
   124|    container_name: hermes
   125|    restart: unless-stopped
   126|    command: gateway run
   127|    ports:
   128|      - "8642:8642"
   129|    volumes:
   130|      - ~/.hermes:/opt/data
   131|    networks:
   132|      - hermes-net
   133|    # Uncomment to forward specific env vars instead of using .env file:
   134|    # environment:
   135|    #   - ANTHROPIC_API_KEY=${ANTH...KEY}
   136|    #   - OPENAI_API_KEY=***
   137|    #   - TELEGRAM_BOT_TOKEN=${TELE...KEN}
   138|    deploy:
   139|      resources:
   140|        limits:
   141|          memory: 4G
   142|          cpus: "2.0"
   143|
   144|  dashboard:
   145|    image: nousresearch/hermes-agent:latest
   146|    container_name: hermes-dashboard
   147|    restart: unless-stopped
   148|    command: dashboard --host 0.0.0.0
   149|    ports:
   150|      - "9119:9119"
   151|    volumes:
   152|      - ~/.hermes:/opt/data
   153|    environment:
   154|      - GATEWAY_HEALTH_URL=http://hermes:8642
   155|    networks:
   156|      - hermes-net
   157|    depends_on:
   158|      - hermes
   159|    deploy:
   160|      resources:
   161|        limits:
   162|          memory: 512M
   163|          cpus: "0.5"
   164|
   165|networks:
   166|  hermes-net:
   167|    driver: bridge
   168|```
   169|
   170|Start with `docker compose up -d` and view logs with `docker compose logs -f`.
   171|
   172|## Resource limits
   173|
   174|The Hermes container needs moderate resources. Recommended minimums:
   175|
   176|| Resource | Minimum | Recommended |
   177||----------|---------|-------------|
   178|| Memory | 1 GB | 2–4 GB |
   179|| CPU | 1 core | 2 cores |
   180|| Disk (data volume) | 500 MB | 2+ GB (grows with sessions/skills) |
   181|
   182|Browser automation (Playwright/Chromium) is the most memory-hungry feature. If you don't need browser tools, 1 GB is sufficient. With browser tools active, allocate at least 2 GB.
   183|
   184|Set limits in Docker:
   185|
   186|```sh
   187|docker run -d \
   188|  --name hermes \
   189|  --restart unless-stopped \
   190|  --memory=4g --cpus=2 \
   191|  -v ~/.hermes:/opt/data \
   192|  nousresearch/hermes-agent gateway run
   193|```
   194|
   195|## What the Dockerfile does
   196|
   197|The official image is based on `debian:13.4` and includes:
   198|
   199|- Python 3 with all Hermes dependencies (`pip install -e ".[all]"`)
   200|- Node.js + npm (for browser automation and WhatsApp bridge)
   201|- Playwright with Chromium (`npx playwright install --with-deps chromium`)
   202|- ripgrep and ffmpeg as system utilities
   203|- The WhatsApp bridge (`scripts/whatsapp-bridge/`)
   204|
   205|The entrypoint script (`docker/entrypoint.sh`) bootstraps the data volume on first run:
   206|- Creates the directory structure (`sessions/`, `memories/`, `skills/`, etc.)
   207|- Copies `.env.example` → `.env` if no `.env` exists
   208|- Copies default `config.yaml` if missing
   209|- Copies default `SOUL.md` if missing
   210|- Syncs bundled skills using a manifest-based approach (preserves user edits)
   211|- Then runs `hermes` with whatever arguments you pass
   212|
   213|## Upgrading
   214|
   215|Pull the latest image and recreate the container. Your data directory is untouched.
   216|
   217|```sh
   218|docker pull nousresearch/hermes-agent:latest
   219|docker rm -f hermes
   220|docker run -d \
   221|  --name hermes \
   222|  --restart unless-stopped \
   223|  -v ~/.hermes:/opt/data \
   224|  nousresearch/hermes-agent gateway run
   225|```
   226|
   227|Or with Docker Compose:
   228|
   229|```sh
   230|docker compose pull
   231|docker compose up -d
   232|```
   233|
   234|## Skills and credential files
   235|
   236|When using Docker as the execution environment (not the methods above, but when the agent runs commands inside a Docker sandbox), Hermes automatically bind-mounts the skills directory (`~/.hermes/skills/`) and any credential files declared by skills into the container as read-only volumes. This means skill scripts, templates, and references are available inside the sandbox without manual configuration.
   237|
   238|The same syncing happens for SSH and Modal backends — skills and credential files are uploaded via rsync or the Modal mount API before each command.
   239|
   240|## Troubleshooting
   241|
   242|### Container exits immediately
   243|
   244|Check logs: `docker logs hermes`. Common causes:
   245|- Missing or invalid `.env` file — run interactively first to complete setup
   246|- Port conflicts if running with exposed ports
   247|
   248|### "Permission denied" errors
   249|
   250|The container runs as root by default. If your host `~/.hermes/` was created by a non-root user, permissions should work. If you get errors, ensure the data directory is writable:
   251|
   252|```sh
   253|chmod -R 755 ~/.hermes
   254|```
   255|
   256|### Browser tools not working
   257|
   258|Playwright needs shared memory. Add `--shm-size=1g` to your Docker run command:
   259|
   260|```sh
   261|docker run -d \
   262|  --name hermes \
   263|  --shm-size=1g \
   264|  -v ~/.hermes:/opt/data \
   265|  nousresearch/hermes-agent gateway run
   266|```
   267|
   268|### Gateway not reconnecting after network issues
   269|
   270|The `--restart unless-stopped` flag handles most transient failures. If the gateway is stuck, restart the container:
   271|
   272|```sh
   273|docker restart hermes
   274|```
   275|
   276|### Checking container health
   277|
   278|```sh
   279|docker logs --tail 50 hermes          # Recent logs
   280|docker run -it --rm nousresearch/hermes-agent:latest version     # Verify version
   281|docker stats hermes                    # Resource usage
   282|```
   283|
