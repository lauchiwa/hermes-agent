     1|"""Mattermost gateway adapter.
     2|
     3|Connects to a self-hosted (or cloud) Mattermost instance via its REST API
     4|(v4) and WebSocket for real-time events.  No external Mattermost library
     5|required — uses aiohttp which is already a Hermes dependency.
     6|
     7|Environment variables:
     8|    MATTERMOST_URL              Server URL (e.g. https://mm.example.com)
     9|    MATTERMOST_TOKEN            Bot token or personal-access token
    10|    MATTERMOST_ALLOWED_USERS    Comma-separated user IDs
    11|    MATTERMOST_HOME_CHANNEL     Channel ID for cron/notification delivery
    12|"""
    13|
    14|from __future__ import annotations
    15|
    16|import asyncio
    17|import json
    18|import logging
    19|import os
    20|import re
    21|from pathlib import Path
    22|from typing import Any, Dict, List, Optional
    23|
    24|from gateway.config import Platform, PlatformConfig
    25|from gateway.platforms.helpers import MessageDeduplicator
    26|from gateway.platforms.base import (
    27|    BasePlatformAdapter,
    28|    MessageEvent,
    29|    MessageType,
    30|    SendResult,
    31|)
    32|
    33|logger = logging.getLogger(__name__)
    34|
    35|# Mattermost post size limit (server default is 16383, but 4000 is the
    36|# practical limit for readable messages — matching OpenClaw's choice).
    37|MAX_POST_LENGTH = 4000
    38|
    39|# Channel type codes returned by the Mattermost API.
    40|_CHANNEL_TYPE_MAP = {
    41|    "D": "dm",
    42|    "G": "group",
    43|    "P": "group",   # private channel → treat as group
    44|    "O": "channel",
    45|}
    46|
    47|# Reconnect parameters (exponential backoff).
    48|_RECONNECT_BASE_DELAY = 2.0
    49|_RECONNECT_MAX_DELAY = 60.0
    50|_RECONNECT_JITTER = 0.2
    51|
    52|
    53|def check_mattermost_requirements() -> bool:
    54|    """Return True if the Mattermost adapter can be used."""
    55|    token = os.getenv("MATTERMOST_TOKEN", "")
    56|    url = os.getenv("MATTERMOST_URL", "")
    57|    if not token:
    58|        logger.debug("Mattermost: MATTERMOST_TOKEN not set")
    59|        return False
    60|    if not url:
    61|        logger.warning("Mattermost: MATTERMOST_URL not set")
    62|        return False
    63|    try:
    64|        import aiohttp  # noqa: F401
    65|        return True
    66|    except ImportError:
    67|        logger.warning("Mattermost: aiohttp not installed")
    68|        return False
    69|
    70|
    71|class MattermostAdapter(BasePlatformAdapter):
    72|    """Gateway adapter for Mattermost (self-hosted or cloud)."""
    73|
    74|    def __init__(self, config: PlatformConfig):
    75|        super().__init__(config, Platform.MATTERMOST)
    76|
    77|        self._base_url: str = (
    78|            config.extra.get("url", "")
    79|            or os.getenv("MATTERMOST_URL", "")
    80|        ).rstrip("/")
    81|        self._token: str = config.token or os.getenv("MATTERMOST_TOKEN", "")
    82|
    83|        self._bot_user_id: str = ""
    84|        self._bot_username: str = ""
    85|
    86|        # aiohttp session + websocket handle
    87|        self._session: Any = None  # aiohttp.ClientSession
    88|        self._ws: Any = None       # aiohttp.ClientWebSocketResponse
    89|        self._ws_task: Optional[asyncio.Task] = None
    90|        self._reconnect_task: Optional[asyncio.Task] = None
    91|        self._closing = False
    92|
    93|        # Reply mode: "thread" to nest replies, "off" for flat messages.
    94|        self._reply_mode: str = (
    95|            config.extra.get("reply_mode", "")
    96|            or os.getenv("MATTERMOST_REPLY_MODE", "off")
    97|        ).lower()
    98|
    99|        # Dedup cache (prevent reprocessing)
   100|        self._dedup = MessageDeduplicator()
   101|
   102|    # ------------------------------------------------------------------
   103|    # HTTP helpers
   104|    # ------------------------------------------------------------------
   105|
   106|    def _headers(self) -> Dict[str, str]:
   107|        return {
   108|            "Authorization": f"Bearer {self._token}",
   109|            "Content-Type": "application/json",
   110|        }
   111|
   112|    async def _api_get(self, path: str) -> Dict[str, Any]:
   113|        """GET /api/v4/{path}."""
   114|        import aiohttp
   115|        url = f"{self._base_url}/api/v4/{path.lstrip('/')}"
   116|        try:
   117|            async with self._session.get(url, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=30)) as resp:
   118|                if resp.status >= 400:
   119|                    body = await resp.text()
   120|                    logger.error("MM API GET %s → %s: %s", path, resp.status, body[:200])
   121|                    return {}
   122|                return await resp.json()
   123|        except aiohttp.ClientError as exc:
   124|            logger.error("MM API GET %s network error: %s", path, exc)
   125|            return {}
   126|
   127|    async def _api_post(
   128|        self, path: str, payload: Dict[str, Any]
   129|    ) -> Dict[str, Any]:
   130|        """POST /api/v4/{path} with JSON body."""
   131|        import aiohttp
   132|        url = f"{self._base_url}/api/v4/{path.lstrip('/')}"
   133|        try:
   134|            async with self._session.post(
   135|                url, headers=self._headers(), json=payload,
   136|                timeout=aiohttp.ClientTimeout(total=30)
   137|            ) as resp:
   138|                if resp.status >= 400:
   139|                    body = await resp.text()
   140|                    logger.error("MM API POST %s → %s: %s", path, resp.status, body[:200])
   141|                    return {}
   142|                return await resp.json()
   143|        except aiohttp.ClientError as exc:
   144|            logger.error("MM API POST %s network error: %s", path, exc)
   145|            return {}
   146|
   147|    async def _api_put(
   148|        self, path: str, payload: Dict[str, Any]
   149|    ) -> Dict[str, Any]:
   150|        """PUT /api/v4/{path} with JSON body."""
   151|        import aiohttp
   152|        url = f"{self._base_url}/api/v4/{path.lstrip('/')}"
   153|        try:
   154|            async with self._session.put(
   155|                url, headers=self._headers(), json=payload
   156|            ) as resp:
   157|                if resp.status >= 400:
   158|                    body = await resp.text()
   159|                    logger.error("MM API PUT %s → %s: %s", path, resp.status, body[:200])
   160|                    return {}
   161|                return await resp.json()
   162|        except aiohttp.ClientError as exc:
   163|            logger.error("MM API PUT %s network error: %s", path, exc)
   164|            return {}
   165|
   166|    async def _upload_file(
   167|        self, channel_id: str, file_data: bytes, filename: str, content_type: str = "application/octet-stream"
   168|    ) -> Optional[str]:
   169|        """Upload a file and return its file ID, or None on failure."""
   170|        import aiohttp
   171|
   172|        url = f"{self._base_url}/api/v4/files"
   173|        form = aiohttp.FormData()
   174|        form.add_field("channel_id", channel_id)
   175|        form.add_field(
   176|            "files",
   177|            file_data,
   178|            filename=filename,
   179|            content_type=content_type,
   180|        )
   181|        headers = {"Authorization": f"Bearer {self._token}"}
   182|        async with self._session.post(url, headers=headers, data=form, timeout=aiohttp.ClientTimeout(total=60)) as resp:
   183|            if resp.status >= 400:
   184|                body = await resp.text()
   185|                logger.error("MM file upload → %s: %s", resp.status, body[:200])
   186|                return None
   187|            data = await resp.json()
   188|            infos = data.get("file_infos", [])
   189|            return infos[0]["id"] if infos else None
   190|
   191|    # ------------------------------------------------------------------
   192|    # Required overrides
   193|    # ------------------------------------------------------------------
   194|
   195|    async def connect(self) -> bool:
   196|        """Connect to Mattermost and start the WebSocket listener."""
   197|        import aiohttp
   198|
   199|        if not self._base_url or not self._token:
   200|            logger.error("Mattermost: URL or token not configured")
   201|            return False
   202|
   203|        self._session = aiohttp.ClientSession(
   204|            timeout=aiohttp.ClientTimeout(total=30)
   205|        )
   206|        self._closing = False
   207|
   208|        # Verify credentials and fetch bot identity.
   209|        me = await self._api_get("users/me")
   210|        if not me or "id" not in me:
   211|            logger.error("Mattermost: failed to authenticate — check MATTERMOST_TOKEN and MATTERMOST_URL")
   212|            await self._session.close()
   213|            return False
   214|
   215|        self._bot_user_id = me["id"]
   216|        self._bot_username = me.get("username", "")
   217|        logger.info(
   218|            "Mattermost: authenticated as @%s (%s) on %s",
   219|            self._bot_username,
   220|            self._bot_user_id,
   221|            self._base_url,
   222|        )
   223|
   224|        # Start WebSocket in background.
   225|        self._ws_task = asyncio.create_task(self._ws_loop())
   226|        self._mark_connected()
   227|        return True
   228|
   229|    async def disconnect(self) -> None:
   230|        """Disconnect from Mattermost."""
   231|        self._closing = True
   232|
   233|        if self._ws_task and not self._ws_task.done():
   234|            self._ws_task.cancel()
   235|            try:
   236|                await self._ws_task
   237|            except (asyncio.CancelledError, Exception):
   238|                pass
   239|
   240|        if self._reconnect_task and not self._reconnect_task.done():
   241|            self._reconnect_task.cancel()
   242|
   243|        if self._ws:
   244|            await self._ws.close()
   245|            self._ws = None
   246|
   247|        if self._session and not self._session.closed:
   248|            await self._session.close()
   249|
   250|        logger.info("Mattermost: disconnected")
   251|
   252|    async def send(
   253|        self,
   254|        chat_id: str,
   255|        content: str,
   256|        reply_to: Optional[str] = None,
   257|        metadata: Optional[Dict[str, Any]] = None,
   258|    ) -> SendResult:
   259|        """Send a message (or multiple chunks) to a channel."""
   260|        if not content:
   261|            return SendResult(success=True)
   262|
   263|        formatted = self.format_message(content)
   264|        chunks = self.truncate_message(formatted, MAX_POST_LENGTH)
   265|
   266|        last_id = None
   267|        for chunk in chunks:
   268|            payload: Dict[str, Any] = {
   269|                "channel_id": chat_id,
   270|                "message": chunk,
   271|            }
   272|            # Thread support: reply_to is the root post ID.
   273|            if reply_to and self._reply_mode == "thread":
   274|                payload["root_id"] = reply_to
   275|
   276|            data = await self._api_post("posts", payload)
   277|            if not data or "id" not in data:
   278|                return SendResult(success=False, error="Failed to create post")
   279|            last_id = data["id"]
   280|
   281|        return SendResult(success=True, message_id=last_id)
   282|
   283|    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
   284|        """Return channel name and type."""
   285|        data = await self._api_get(f"channels/{chat_id}")
   286|        if not data:
   287|            return {"name": chat_id, "type": "channel"}
   288|
   289|        ch_type = _CHANNEL_TYPE_MAP.get(data.get("type", "O"), "channel")
   290|        display_name = data.get("display_name") or data.get("name") or chat_id
   291|        return {"name": display_name, "type": ch_type}
   292|
   293|    # ------------------------------------------------------------------
   294|    # Optional overrides
   295|    # ------------------------------------------------------------------
   296|
   297|    async def send_typing(
   298|        self, chat_id: str, metadata: Optional[Dict[str, Any]] = None
   299|    ) -> None:
   300|        """Send a typing indicator."""
   301|        await self._api_post(
   302|            f"users/{self._bot_user_id}/typing",
   303|            {"channel_id": chat_id},
   304|        )
   305|
   306|    async def edit_message(
   307|        self, chat_id: str, message_id: str, content: str
   308|    ) -> SendResult:
   309|        """Edit an existing post."""
   310|        formatted = self.format_message(content)
   311|        data = await self._api_put(
   312|            f"posts/{message_id}/patch",
   313|            {"message": formatted},
   314|        )
   315|        if not data or "id" not in data:
   316|            return SendResult(success=False, error="Failed to edit post")
   317|        return SendResult(success=True, message_id=data["id"])
   318|
   319|    async def send_image(
   320|        self,
   321|        chat_id: str,
   322|        image_url: str,
   323|        caption: Optional[str] = None,
   324|        reply_to: Optional[str] = None,
   325|        metadata: Optional[Dict[str, Any]] = None,
   326|    ) -> SendResult:
   327|        """Download an image and upload it as a file attachment."""
   328|        return await self._send_url_as_file(
   329|            chat_id, image_url, caption, reply_to, "image"
   330|        )
   331|
   332|    async def send_image_file(
   333|        self,
   334|        chat_id: str,
   335|        image_path: str,
   336|        caption: Optional[str] = None,
   337|        reply_to: Optional[str] = None,
   338|        metadata: Optional[Dict[str, Any]] = None,
   339|    ) -> SendResult:
   340|        """Upload a local image file."""
   341|        return await self._send_local_file(
   342|            chat_id, image_path, caption, reply_to
   343|        )
   344|
   345|    async def send_document(
   346|        self,
   347|        chat_id: str,
   348|        file_path: str,
   349|        caption: Optional[str] = None,
   350|        file_name: Optional[str] = None,
   351|        reply_to: Optional[str] = None,
   352|        metadata: Optional[Dict[str, Any]] = None,
   353|    ) -> SendResult:
   354|        """Upload a local file as a document."""
   355|        return await self._send_local_file(
   356|            chat_id, file_path, caption, reply_to, file_name
   357|        )
   358|
   359|    async def send_voice(
   360|        self,
   361|        chat_id: str,
   362|        audio_path: str,
   363|        caption: Optional[str] = None,
   364|        reply_to: Optional[str] = None,
   365|        metadata: Optional[Dict[str, Any]] = None,
   366|    ) -> SendResult:
   367|        """Upload an audio file."""
   368|        return await self._send_local_file(
   369|            chat_id, audio_path, caption, reply_to
   370|        )
   371|
   372|    async def send_video(
   373|        self,
   374|        chat_id: str,
   375|        video_path: str,
   376|        caption: Optional[str] = None,
   377|        reply_to: Optional[str] = None,
   378|        metadata: Optional[Dict[str, Any]] = None,
   379|    ) -> SendResult:
   380|        """Upload a video file."""
   381|        return await self._send_local_file(
   382|            chat_id, video_path, caption, reply_to
   383|        )
   384|
   385|    def format_message(self, content: str) -> str:
   386|        """Mattermost uses standard Markdown — mostly pass through.
   387|
   388|        Strip image markdown into plain links (files are uploaded separately).
   389|        """
   390|        # Convert ![alt](url) to just the URL — Mattermost renders
   391|        # image URLs as inline previews automatically.
   392|        content = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"\2", content)
   393|        return content
   394|
   395|    # ------------------------------------------------------------------
   396|    # File helpers
   397|    # ------------------------------------------------------------------
   398|
   399|    async def _send_url_as_file(
   400|        self,
   401|        chat_id: str,
   402|        url: str,
   403|        caption: Optional[str],
   404|        reply_to: Optional[str],
   405|        kind: str = "file",
   406|    ) -> SendResult:
   407|        """Download a URL and upload it as a file attachment."""
   408|        from tools.url_safety import is_safe_url
   409|        if not is_safe_url(url):
   410|            logger.warning("Mattermost: blocked unsafe URL (SSRF protection)")
   411|            return await self.send(chat_id, f"{caption or ''}\n{url}".strip(), reply_to)
   412|
   413|        import asyncio
   414|        import aiohttp
   415|
   416|        last_exc = None
   417|        file_data = None
   418|        ct = "application/octet-stream"
   419|        fname = url.rsplit("/", 1)[-1].split("?")[0] or f"{kind}.png"
   420|
   421|        for attempt in range(3):
   422|            try:
   423|                async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
   424|                    if resp.status >= 500 or resp.status == 429:
   425|                        if attempt < 2:
   426|                            logger.debug("Mattermost download retry %d/2 for %s (status %d)",
   427|                                         attempt + 1, url[:80], resp.status)
   428|                            await asyncio.sleep(1.5 * (attempt + 1))
   429|                            continue
   430|                    if resp.status >= 400:
   431|                        return await self.send(chat_id, f"{caption or ''}\n{url}".strip(), reply_to)
   432|                    file_data = await resp.read()
   433|                    ct = resp.content_type or "application/octet-stream"
   434|                    break
   435|            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
   436|                if attempt < 2:
   437|                    await asyncio.sleep(1.5 * (attempt + 1))
   438|                    continue
   439|                logger.warning("Mattermost: failed to download %s after %d attempts: %s", url, attempt + 1, exc)
   440|                return await self.send(chat_id, f"{caption or ''}\n{url}".strip(), reply_to)
   441|
   442|        if file_data is None:
   443|            logger.warning("Mattermost: download returned no data for %s", url)
   444|            return await self.send(chat_id, f"{caption or ''}\n{url}".strip(), reply_to)
   445|
   446|        file_id = await self._upload_file(chat_id, file_data, fname, ct)
   447|        if not file_id:
   448|            return await self.send(chat_id, f"{caption or ''}\n{url}".strip(), reply_to)
   449|
   450|        payload: Dict[str, Any] = {
   451|            "channel_id": chat_id,
   452|            "message": caption or "",
   453|            "file_ids": [file_id],
   454|        }
   455|        if reply_to and self._reply_mode == "thread":
   456|            payload["root_id"] = reply_to
   457|
   458|        data = await self._api_post("posts", payload)
   459|        if not data or "id" not in data:
   460|            return SendResult(success=False, error="Failed to post with file")
   461|        return SendResult(success=True, message_id=data["id"])
   462|
   463|    async def _send_local_file(
   464|        self,
   465|        chat_id: str,
   466|        file_path: str,
   467|        caption: Optional[str],
   468|        reply_to: Optional[str],
   469|        file_name: Optional[str] = None,
   470|    ) -> SendResult:
   471|        """Upload a local file and attach it to a post."""
   472|        import mimetypes
   473|
   474|        p = Path(file_path)
   475|        if not p.exists():
   476|            return await self.send(
   477|                chat_id, f"{caption or ''}\n(file not found: {file_path})", reply_to
   478|            )
   479|
   480|        fname = file_name or p.name
   481|        ct = mimetypes.guess_type(fname)[0] or "application/octet-stream"
   482|        file_data = p.read_bytes()
   483|
   484|        file_id = await self._upload_file(chat_id, file_data, fname, ct)
   485|        if not file_id:
   486|            return SendResult(success=False, error="File upload failed")
   487|
   488|        payload: Dict[str, Any] = {
   489|            "channel_id": chat_id,
   490|            "message": caption or "",
   491|            "file_ids": [file_id],
   492|        }
   493|        if reply_to and self._reply_mode == "thread":
   494|            payload["root_id"] = reply_to
   495|
   496|        data = await self._api_post("posts", payload)
   497|        if not data or "id" not in data:
   498|            return SendResult(success=False, error="Failed to post with file")
   499|        return SendResult(success=True, message_id=data["id"])
   500|
   501|    # ------------------------------------------------------------------
   502|    # WebSocket
   503|    # ------------------------------------------------------------------
   504|
   505|    async def _ws_loop(self) -> None:
   506|        """Connect to the WebSocket and listen for events, reconnecting on failure."""
   507|        delay = _RECONNECT_BASE_DELAY
   508|        while not self._closing:
   509|            try:
   510|                await self._ws_connect_and_listen()
   511|                # Clean disconnect — reset delay.
   512|                delay = _RECONNECT_BASE_DELAY
   513|            except asyncio.CancelledError:
   514|                return
   515|            except Exception as exc:
   516|                if self._closing:
   517|                    return
   518|                # Detect permanent auth/permission failures that will never
   519|                # succeed on retry — stop reconnecting instead of looping forever.
   520|                import aiohttp
   521|                err_str = str(exc).lower()
   522|                if isinstance(exc, aiohttp.WSServerHandshakeError) and exc.status in (401, 403):
   523|                    logger.error("Mattermost WS auth failed (HTTP %d) — stopping reconnect", exc.status)
   524|                    return
   525|                if "401" in err_str or "403" in err_str or "unauthorized" in err_str:
   526|                    logger.error("Mattermost WS permanent error: %s — stopping reconnect", exc)
   527|                    return
   528|                logger.warning("Mattermost WS error: %s — reconnecting in %.0fs", exc, delay)
   529|
   530|            if self._closing:
   531|                return
   532|
   533|            # Exponential backoff with jitter.
   534|            import random
   535|            jitter = delay * _RECONNECT_JITTER * random.random()
   536|            await asyncio.sleep(delay + jitter)
   537|            delay = min(delay * 2, _RECONNECT_MAX_DELAY)
   538|
   539|    async def _ws_connect_and_listen(self) -> None:
   540|        """Single WebSocket session: connect, authenticate, process events."""
   541|        # Build WS URL: https:// → wss://, http:// → ws://
   542|        ws_url = re.sub(r"^http", "ws", self._base_url) + "/api/v4/websocket"
   543|        logger.info("Mattermost: connecting to %s", ws_url)
   544|
   545|        self._ws = await self._session.ws_connect(ws_url, heartbeat=30.0)
   546|
   547|        # Authenticate via the WebSocket.
   548|        auth_msg = {
   549|            "seq": 1,
   550|            "action": "authentication_challenge",
   551|            "data": {"token": self._token},
   552|        }
   553|        await self._ws.send_json(auth_msg)
   554|        logger.info("Mattermost: WebSocket connected and authenticated")
   555|
   556|        async for raw_msg in self._ws:
   557|            if self._closing:
   558|                return
   559|
   560|            if raw_msg.type in (
   561|                raw_msg.type.TEXT,
   562|                raw_msg.type.BINARY,
   563|            ):
   564|                try:
   565|                    event = json.loads(raw_msg.data)
   566|                except (json.JSONDecodeError, TypeError):
   567|                    continue
   568|                await self._handle_ws_event(event)
   569|            elif raw_msg.type in (
   570|                raw_msg.type.ERROR,
   571|                raw_msg.type.CLOSE,
   572|                raw_msg.type.CLOSING,
   573|                raw_msg.type.CLOSED,
   574|            ):
   575|                logger.info("Mattermost: WebSocket closed (%s)", raw_msg.type)
   576|                break
   577|
   578|    async def _handle_ws_event(self, event: Dict[str, Any]) -> None:
   579|        """Process a single WebSocket event."""
   580|        event_type = event.get("event")
   581|        if event_type != "posted":
   582|            return
   583|
   584|        data = event.get("data", {})
   585|        raw_post_str = data.get("post")
   586|        if not raw_post_str:
   587|            return
   588|
   589|        try:
   590|            post = json.loads(raw_post_str)
   591|        except (json.JSONDecodeError, TypeError):
   592|            return
   593|
   594|        # Ignore own messages.
   595|        if post.get("user_id") == self._bot_user_id:
   596|            return
   597|
   598|        # Ignore system posts.
   599|        if post.get("type"):
   600|            return
   601|
   602|        post_id = post.get("id", "")
   603|
   604|        # Dedup.
   605|        if self._dedup.is_duplicate(post_id):
   606|            return
   607|
   608|        # Build message event.
   609|        channel_id = post.get("channel_id", "")
   610|        channel_type_raw = data.get("channel_type", "O")
   611|        chat_type = _CHANNEL_TYPE_MAP.get(channel_type_raw, "channel")
   612|
   613|        # For DMs, user_id is sufficient.  For channels, check for @mention.
   614|        message_text = post.get("message", "")
   615|
   616|        # Mention-gating for non-DM channels.
   617|        # Config (env vars):
   618|        #   MATTERMOST_REQUIRE_MENTION: Require @mention in channels (default: true)
   619|        #   MATTERMOST_FREE_RESPONSE_CHANNELS: Channel IDs where bot responds without mention
   620|        if channel_type_raw != "D":
   621|            require_mention = os.getenv(
   622|                "MATTERMOST_REQUIRE_MENTION", "true"
   623|            ).lower() not in ("false", "0", "no")
   624|
   625|            free_channels_raw = os.getenv("MATTERMOST_FREE_RESPONSE_CHANNELS", "")
   626|            free_channels = {ch.strip() for ch in free_channels_raw.split(",") if ch.strip()}
   627|            is_free_channel = channel_id in free_channels
   628|
   629|            mention_patterns = [
   630|                f"@{self._bot_username}",
   631|                f"@{self._bot_user_id}",
   632|            ]
   633|            has_mention = any(
   634|                pattern.lower() in message_text.lower()
   635|                for pattern in mention_patterns
   636|            )
   637|
   638|            if require_mention and not is_free_channel and not has_mention:
   639|                logger.debug(
   640|                    "Mattermost: skipping non-DM message without @mention (channel=%s)",
   641|                    channel_id,
   642|                )
   643|                return
   644|
   645|            # Strip @mention from the message text so the agent sees clean input.
   646|            if has_mention:
   647|                for pattern in mention_patterns:
   648|                    message_text = re.sub(
   649|                        re.escape(pattern), "", message_text, flags=re.IGNORECASE
   650|                    ).strip()
   651|
   652|        # Resolve sender info.
   653|        sender_id = post.get("user_id", "")
   654|        sender_name = data.get("sender_name", "").lstrip("@") or sender_id
   655|
   656|        # Thread support: if the post is in a thread, use root_id.
   657|        thread_id = post.get("root_id") or None
   658|
   659|        # Determine message type.
   660|        file_ids = post.get("file_ids") or []
   661|        msg_type = MessageType.TEXT
   662|        if message_text.startswith("/"):
   663|            msg_type = MessageType.COMMAND
   664|
   665|        # Download file attachments immediately (URLs require auth headers
   666|        # that downstream tools won't have).
   667|        media_urls: List[str] = []
   668|        media_types: List[str] = []
   669|        for fid in file_ids:
   670|            try:
   671|                file_info = await self._api_get(f"files/{fid}/info")
   672|                fname = file_info.get("name", f"file_{fid}")
   673|                ext = Path(fname).suffix or ""
   674|                mime = file_info.get("mime_type", "application/octet-stream")
   675|
   676|                import aiohttp
   677|                dl_url = f"{self._base_url}/api/v4/files/{fid}"
   678|                async with self._session.get(
   679|                    dl_url,
   680|                    headers={"Authorization": f"Bearer {self._token}"},
   681|                    timeout=aiohttp.ClientTimeout(total=30),
   682|                ) as resp:
   683|                    if resp.status < 400:
   684|                        file_data = await resp.read()
   685|                        from gateway.platforms.base import cache_image_from_bytes, cache_document_from_bytes
   686|                        if mime.startswith("image/"):
   687|                            local_path = cache_image_from_bytes(file_data, ext or ".png")
   688|                            media_urls.append(local_path)
   689|                            media_types.append(mime)
   690|                        elif mime.startswith("audio/"):
   691|                            from gateway.platforms.base import cache_audio_from_bytes
   692|                            local_path = cache_audio_from_bytes(file_data, ext or ".ogg")
   693|                            media_urls.append(local_path)
   694|                            media_types.append(mime)
   695|                        else:
   696|                            local_path = cache_document_from_bytes(file_data, fname)
   697|                            media_urls.append(local_path)
   698|                            media_types.append(mime)
   699|                    else:
   700|                        logger.warning("Mattermost: failed to download file %s: HTTP %s", fid, resp.status)
   701|            except Exception as exc:
   702|                logger.warning("Mattermost: error downloading file %s: %s", fid, exc)
   703|
   704|        # Set message type based on downloaded media types.
   705|        if media_types and msg_type == MessageType.TEXT:
   706|            if any(m.startswith("image/") for m in media_types):
   707|                msg_type = MessageType.PHOTO
   708|            elif any(m.startswith("audio/") for m in media_types):
   709|                msg_type = MessageType.VOICE
   710|            elif media_types:
   711|                msg_type = MessageType.DOCUMENT
   712|
   713|        source = self.build_source(
   714|            chat_id=channel_id,
   715|            chat_type=chat_type,
   716|            user_id=sender_id,
   717|            user_name=sender_name,
   718|            thread_id=thread_id,
   719|        )
   720|
   721|        # Per-channel ephemeral prompt
   722|        from gateway.platforms.base import resolve_channel_prompt
   723|        _channel_prompt = resolve_channel_prompt(
   724|            self.config.extra, channel_id, None,
   725|        )
   726|
   727|        msg_event = MessageEvent(
   728|            text=message_text,
   729|            message_type=msg_type,
   730|            source=source,
   731|            raw_message=post,
   732|            message_id=post_id,
   733|            media_urls=media_urls if media_urls else None,
   734|            media_types=media_types if media_types else None,
   735|            channel_prompt=_channel_prompt,
   736|        )
   737|
   738|        await self.handle_message(msg_event)
   739|
   740|
   741|
