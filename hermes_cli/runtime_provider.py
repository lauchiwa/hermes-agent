     1|"""Shared runtime provider resolution for CLI, gateway, cron, and helpers."""
     2|
     3|from __future__ import annotations
     4|
     5|import logging
     6|import os
     7|import re
     8|from typing import Any, Dict, Optional
     9|
    10|logger = logging.getLogger(__name__)
    11|
    12|from hermes_cli import auth as auth_mod
    13|from agent.credential_pool import CredentialPool, PooledCredential, get_custom_provider_pool_key, load_pool
    14|from hermes_cli.auth import (
    15|    AuthError,
    16|    DEFAULT_CODEX_BASE_URL,
    17|    DEFAULT_QWEN_BASE_URL,
    18|    PROVIDER_REGISTRY,
    19|    _agent_key_is_usable,
    20|    format_auth_error,
    21|    resolve_provider,
    22|    resolve_nous_runtime_credentials,
    23|    resolve_codex_runtime_credentials,
    24|    resolve_qwen_runtime_credentials,
    25|    resolve_api_key_provider_credentials,
    26|    resolve_external_process_provider_credentials,
    27|    has_usable_secret,
    28|)
    29|from hermes_cli.config import get_compatible_custom_providers, load_config
    30|from hermes_constants import OPENROUTER_BASE_URL
    31|
    32|
    33|def _normalize_custom_provider_name(value: str) -> str:
    34|    return value.strip().lower().replace(" ", "-")
    35|
    36|
    37|def _detect_api_mode_for_url(base_url: str) -> Optional[str]:
    38|    """Auto-detect api_mode from the resolved base URL.
    39|
    40|    Direct api.openai.com endpoints need the Responses API for GPT-5.x
    41|    tool calls with reasoning (chat/completions returns 400).
    42|    """
    43|    normalized = (base_url or "").strip().lower().rstrip("/")
    44|    if "api.x.ai" in normalized:
    45|        return "codex_responses"
    46|    if "api.openai.com" in normalized and "openrouter" not in normalized:
    47|        return "codex_responses"
    48|    return None
    49|
    50|
    51|def _auto_detect_local_model(base_url: str) -> str:
    52|    """Query a local server for its model name when only one model is loaded."""
    53|    if not base_url:
    54|        return ""
    55|    try:
    56|        import requests
    57|        url = base_url.rstrip("/")
    58|        if not url.endswith("/v1"):
    59|            url += "/v1"
    60|        resp = requests.get(url + "/models", timeout=5)
    61|        if resp.ok:
    62|            models = resp.json().get("data", [])
    63|            if len(models) == 1:
    64|                model_id = models[0].get("id", "")
    65|                if model_id:
    66|                    return model_id
    67|    except Exception:
    68|        pass
    69|    return ""
    70|
    71|
    72|def _get_model_config() -> Dict[str, Any]:
    73|    config = load_config()
    74|    model_cfg = config.get("model")
    75|    if isinstance(model_cfg, dict):
    76|        cfg = dict(model_cfg)
    77|        # Accept "model" as alias for "default" (users intuitively write model.model)
    78|        if not cfg.get("default") and cfg.get("model"):
    79|            cfg["default"] = cfg["model"]
    80|        default = (cfg.get("default") or "").strip()
    81|        base_url = (cfg.get("base_url") or "").strip()
    82|        is_local = "localhost" in base_url or "127.0.0.1" in base_url
    83|        is_fallback = not default
    84|        if is_local and is_fallback and base_url:
    85|            detected = _auto_detect_local_model(base_url)
    86|            if detected:
    87|                cfg["default"] = detected
    88|        return cfg
    89|    if isinstance(model_cfg, str) and model_cfg.strip():
    90|        return {"default": model_cfg.strip()}
    91|    return {}
    92|
    93|
    94|def _provider_supports_explicit_api_mode(provider: Optional[str], configured_provider: Optional[str] = None) -> bool:
    95|    """Check whether a persisted api_mode should be honored for a given provider.
    96|
    97|    Prevents stale api_mode from a previous provider leaking into a
    98|    different one after a model/provider switch.  Only applies the
    99|    persisted mode when the config's provider matches the runtime
   100|    provider (or when no configured provider is recorded).
   101|    """
   102|    normalized_provider = (provider or "").strip().lower()
   103|    normalized_configured = (configured_provider or "").strip().lower()
   104|    if not normalized_configured:
   105|        return True
   106|    if normalized_provider == "custom":
   107|        return normalized_configured == "custom" or normalized_configured.startswith("custom:")
   108|    return normalized_configured == normalized_provider
   109|
   110|
   111|def _copilot_runtime_api_mode(model_cfg: Dict[str, Any], api_key: str) -> str:
   112|    configured_provider = str(model_cfg.get("provider") or "").strip().lower()
   113|    configured_mode = _parse_api_mode(model_cfg.get("api_mode"))
   114|    if configured_mode and _provider_supports_explicit_api_mode("copilot", configured_provider):
   115|        return configured_mode
   116|
   117|    model_name = str(model_cfg.get("default") or "").strip()
   118|    if not model_name:
   119|        return "chat_completions"
   120|
   121|    try:
   122|        from hermes_cli.models import copilot_model_api_mode
   123|
   124|        return copilot_model_api_mode(model_name, api_key=api_key)
   125|    except Exception:
   126|        return "chat_completions"
   127|
   128|
   129|_VALID_API_MODES = {"chat_completions", "codex_responses", "anthropic_messages", "bedrock_converse"}
   130|
   131|
   132|def _parse_api_mode(raw: Any) -> Optional[str]:
   133|    """Validate an api_mode value from config. Returns None if invalid."""
   134|    if isinstance(raw, str):
   135|        normalized = raw.strip().lower()
   136|        if normalized in _VALID_API_MODES:
   137|            return normalized
   138|    return None
   139|
   140|
   141|def _resolve_runtime_from_pool_entry(
   142|    *,
   143|    provider: str,
   144|    entry: PooledCredential,
   145|    requested_provider: str,
   146|    model_cfg: Optional[Dict[str, Any]] = None,
   147|    pool: Optional[CredentialPool] = None,
   148|) -> Dict[str, Any]:
   149|    model_cfg = model_cfg or _get_model_config()
   150|    base_url = (getattr(entry, "runtime_base_url", None) or getattr(entry, "base_url", None) or "").rstrip("/")
   151|    api_key = getattr(entry, "runtime_api_key", None) or getattr(entry, "access_token", "")
   152|    api_mode = "chat_completions"
   153|    if provider == "openai-codex":
   154|        api_mode = "codex_responses"
   155|        base_url = base_url or DEFAULT_CODEX_BASE_URL
   156|    elif provider == "qwen-oauth":
   157|        api_mode = "chat_completions"
   158|        base_url = base_url or DEFAULT_QWEN_BASE_URL
   159|    elif provider == "anthropic":
   160|        api_mode = "anthropic_messages"
   161|        cfg_provider = str(model_cfg.get("provider") or "").strip().lower()
   162|        cfg_base_url = ""
   163|        if cfg_provider == "anthropic":
   164|            cfg_base_url = str(model_cfg.get("base_url") or "").strip().rstrip("/")
   165|        base_url = cfg_base_url or base_url or "https://api.anthropic.com"
   166|    elif provider == "openrouter":
   167|        base_url = base_url or OPENROUTER_BASE_URL
   168|    elif provider == "xai":
   169|        api_mode = "codex_responses"
   170|    elif provider == "nous":
   171|        api_mode = "chat_completions"
   172|    elif provider == "copilot":
   173|        api_mode = _copilot_runtime_api_mode(model_cfg, getattr(entry, "runtime_api_key", ""))
   174|        base_url = base_url or PROVIDER_REGISTRY["copilot"].inference_base_url
   175|    else:
   176|        configured_provider = str(model_cfg.get("provider") or "").strip().lower()
   177|        # Honour model.base_url from config.yaml when the configured provider
   178|        # matches this provider — same pattern as the Anthropic branch above.
   179|        # Only override when the pool entry has no explicit base_url (i.e. it
   180|        # fell back to the hardcoded default).  Env var overrides win (#6039).
   181|        pconfig = PROVIDER_REGISTRY.get(provider)
   182|        pool_url_is_default = pconfig and base_url.rstrip("/") == pconfig.inference_base_url.rstrip("/")
   183|        if configured_provider == provider and pool_url_is_default:
   184|            cfg_base_url = str(model_cfg.get("base_url") or "").strip().rstrip("/")
   185|            if cfg_base_url:
   186|                base_url = cfg_base_url
   187|        configured_mode = _parse_api_mode(model_cfg.get("api_mode"))
   188|        if configured_mode and _provider_supports_explicit_api_mode(provider, configured_provider):
   189|            api_mode = configured_mode
   190|        elif provider in ("opencode-zen", "opencode-go"):
   191|            from hermes_cli.models import opencode_model_api_mode
   192|            api_mode = opencode_model_api_mode(provider, model_cfg.get("default", ""))
   193|        elif base_url.rstrip("/").endswith("/anthropic"):
   194|            api_mode = "anthropic_messages"
   195|
   196|    # OpenCode base URLs end with /v1 for OpenAI-compatible models, but the
   197|    # Anthropic SDK prepends its own /v1/messages to the base_url.  Strip the
   198|    # trailing /v1 so the SDK constructs the correct path (e.g.
   199|    # https://opencode.ai/zen/go/v1/messages instead of .../v1/v1/messages).
   200|    if api_mode == "anthropic_messages" and provider in ("opencode-zen", "opencode-go"):
   201|        base_url = re.sub(r"/v1/?$", "", base_url)
   202|
   203|    return {
   204|        "provider": provider,
   205|        "api_mode": api_mode,
   206|        "base_url": base_url,
   207|        "api_key": api_key,
   208|        "source": getattr(entry, "source", "pool"),
   209|        "credential_pool": pool,
   210|        "requested_provider": requested_provider,
   211|    }
   212|
   213|
   214|def resolve_requested_provider(requested: Optional[str] = None) -> str:
   215|    """Resolve provider request from explicit arg, config, then env."""
   216|    if requested and requested.strip():
   217|        return requested.strip().lower()
   218|
   219|    model_cfg = _get_model_config()
   220|    cfg_provider = model_cfg.get("provider")
   221|    if isinstance(cfg_provider, str) and cfg_provider.strip():
   222|        return cfg_provider.strip().lower()
   223|
   224|    # Prefer the persisted config selection over any stale shell/.env
   225|    # provider override so chat uses the endpoint the user last saved.
   226|    env_provider = os.getenv("HERMES_INFERENCE_PROVIDER", "").strip().lower()
   227|    if env_provider:
   228|        return env_provider
   229|
   230|    return "auto"
   231|
   232|
   233|def _try_resolve_from_custom_pool(
   234|    base_url: str,
   235|    provider_label: str,
   236|    api_mode_override: Optional[str] = None,
   237|) -> Optional[Dict[str, Any]]:
   238|    """Check if a credential pool exists for a custom endpoint and return a runtime dict if so."""
   239|    pool_key = get_custom_provider_pool_key(base_url)
   240|    if not pool_key:
   241|        return None
   242|    try:
   243|        pool = load_pool(pool_key)
   244|        if not pool.has_credentials():
   245|            return None
   246|        entry = pool.select()
   247|        if entry is None:
   248|            return None
   249|        pool_api_key = getattr(entry, "runtime_api_key", None) or getattr(entry, "access_token", "")
   250|        if not pool_api_key:
   251|            return None
   252|        return {
   253|            "provider": provider_label,
   254|            "api_mode": api_mode_override or _detect_api_mode_for_url(base_url) or "chat_completions",
   255|            "base_url": base_url,
   256|            "api_key": pool_api_key,
   257|            "source": f"pool:{pool_key}",
   258|            "credential_pool": pool,
   259|        }
   260|    except Exception:
   261|        return None
   262|
   263|
   264|def _get_named_custom_provider(requested_provider: str) -> Optional[Dict[str, Any]]:
   265|    requested_norm = _normalize_custom_provider_name(requested_provider or "")
   266|    if not requested_norm or requested_norm == "custom":
   267|        return None
   268|
   269|    # Raw names should only map to custom providers when they are not already
   270|    # valid built-in providers or aliases. Explicit menu keys like
   271|    # ``custom:local`` always target the saved custom provider.
   272|    if requested_norm == "auto":
   273|        return None
   274|    if not requested_norm.startswith("custom:"):
   275|        try:
   276|            auth_mod.resolve_provider(requested_norm)
   277|        except AuthError:
   278|            pass
   279|        else:
   280|            return None
   281|
   282|    config = load_config()
   283|
   284|    # First check providers: dict (new-style user-defined providers)
   285|    providers = config.get("providers")
   286|    if isinstance(providers, dict):
   287|        for ep_name, entry in providers.items():
   288|            if not isinstance(entry, dict):
   289|                continue
   290|            # Match exact name or normalized name
   291|            name_norm = _normalize_custom_provider_name(ep_name)
   292|            # Resolve the API key from the env var name stored in key_env
   293|            key_env = str(entry.get("key_env", "") or "").strip()
   294|            resolved_api_key = os.getenv(key_env, "").strip() if key_env else ""
   295|            # Fall back to inline api_key when key_env is absent or unresolvable
   296|            if not resolved_api_key:
   297|                resolved_api_key = str(entry.get("api_key", "") or "").strip()
   298|
   299|            if requested_norm in {ep_name, name_norm, f"custom:{name_norm}"}:
   300|                # Found match by provider key
   301|                base_url = entry.get("api") or entry.get("url") or entry.get("base_url") or ""
   302|                if base_url:
   303|                    return {
   304|                        "name": entry.get("name", ep_name),
   305|                        "base_url": base_url.strip(),
   306|                        "api_key": resolved_api_key,
   307|                        "model": entry.get("default_model", ""),
   308|                    }
   309|            # Also check the 'name' field if present
   310|            display_name = entry.get("name", "")
   311|            if display_name:
   312|                display_norm = _normalize_custom_provider_name(display_name)
   313|                if requested_norm in {display_name, display_norm, f"custom:{display_norm}"}:
   314|                    # Found match by display name
   315|                    base_url = entry.get("api") or entry.get("url") or entry.get("base_url") or ""
   316|                    if base_url:
   317|                        return {
   318|                            "name": display_name,
   319|                            "base_url": base_url.strip(),
   320|                            "api_key": resolved_api_key,
   321|                            "model": entry.get("default_model", ""),
   322|                        }
   323|
   324|    # Fall back to custom_providers: list (legacy format)
   325|    custom_providers = config.get("custom_providers")
   326|    if isinstance(custom_providers, dict):
   327|        logger.warning(
   328|            "custom_providers in config.yaml is a dict, not a list. "
   329|            "Each entry must be prefixed with '-' in YAML. "
   330|            "Run 'hermes doctor' for details."
   331|        )
   332|        return None
   333|
   334|    custom_providers = get_compatible_custom_providers(config)
   335|    if not custom_providers:
   336|        return None
   337|
   338|    for entry in custom_providers:
   339|        if not isinstance(entry, dict):
   340|            continue
   341|        name = entry.get("name")
   342|        base_url = entry.get("base_url")
   343|        if not isinstance(name, str) or not isinstance(base_url, str):
   344|            continue
   345|        name_norm = _normalize_custom_provider_name(name)
   346|        menu_key = f"custom:{name_norm}"
   347|        provider_key = str(entry.get("provider_key", "") or "").strip()
   348|        provider_key_norm = _normalize_custom_provider_name(provider_key) if provider_key else ""
   349|        provider_menu_key = f"custom:{provider_key_norm}" if provider_key_norm else ""
   350|        if requested_norm not in {name_norm, menu_key, provider_key_norm, provider_menu_key}:
   351|            continue
   352|        result = {
   353|            "name": name.strip(),
   354|            "base_url": base_url.strip(),
   355|            "api_key": str(entry.get("api_key", "") or "").strip(),
   356|        }
   357|        key_env = str(entry.get("key_env", "") or "").strip()
   358|        if key_env:
   359|            result["key_env"] = key_env
   360|        if provider_key:
   361|            result["provider_key"] = provider_key
   362|        api_mode = _parse_api_mode(entry.get("api_mode"))
   363|        if api_mode:
   364|            result["api_mode"] = api_mode
   365|        model_name = str(entry.get("model", "") or "").strip()
   366|        if model_name:
   367|            result["model"] = model_name
   368|        return result
   369|
   370|    return None
   371|
   372|
   373|def _resolve_named_custom_runtime(
   374|    *,
   375|    requested_provider: str,
   376|    explicit_api_key: Optional[str] = None,
   377|    explicit_base_url: Optional[str] = None,
   378|) -> Optional[Dict[str, Any]]:
   379|    custom_provider = _get_named_custom_provider(requested_provider)
   380|    if not custom_provider:
   381|        return None
   382|
   383|    base_url = (
   384|        (explicit_base_url or "").strip()
   385|        or custom_provider.get("base_url", "")
   386|    ).rstrip("/")
   387|    if not base_url:
   388|        return None
   389|
   390|    # Check if a credential pool exists for this custom endpoint
   391|    pool_result = _try_resolve_from_custom_pool(base_url, "custom", custom_provider.get("api_mode"))
   392|    if pool_result:
   393|        # Propagate the model name even when using pooled credentials —
   394|        # the pool doesn't know about the custom_providers model field.
   395|        model_name = custom_provider.get("model")
   396|        if model_name:
   397|            pool_result["model"] = model_name
   398|        return pool_result
   399|
   400|    api_key_candidates = [
   401|        (explicit_api_key or "").strip(),
   402|        str(custom_provider.get("api_key", "") or "").strip(),
   403|        os.getenv(str(custom_provider.get("key_env", "") or "").strip(), "").strip(),
   404|        os.getenv("OPENAI_API_KEY", "").strip(),
   405|        os.getenv("OPENROUTER_API_KEY", "").strip(),
   406|    ]
   407|    api_key = next((candidate for candidate in api_key_candidates if has_usable_secret(candidate)), "")
   408|
   409|    result = {
   410|        "provider": "custom",
   411|        "api_mode": custom_provider.get("api_mode")
   412|        or _detect_api_mode_for_url(base_url)
   413|        or "chat_completions",
   414|        "base_url": base_url,
   415|        "api_key": api_key or "no-key-required",
   416|        "source": f"custom_provider:{custom_provider.get('name', requested_provider)}",
   417|    }
   418|    # Propagate the model name so callers can override self.model when the
   419|    # provider name differs from the actual model string the API expects.
   420|    if custom_provider.get("model"):
   421|        result["model"] = custom_provider["model"]
   422|    return result
   423|
   424|
   425|def _resolve_openrouter_runtime(
   426|    *,
   427|    requested_provider: str,
   428|    explicit_api_key: Optional[str] = None,
   429|    explicit_base_url: Optional[str] = None,
   430|) -> Dict[str, Any]:
   431|    model_cfg = _get_model_config()
   432|    cfg_base_url = model_cfg.get("base_url") if isinstance(model_cfg.get("base_url"), str) else ""
   433|    cfg_provider = model_cfg.get("provider") if isinstance(model_cfg.get("provider"), str) else ""
   434|    cfg_api_key = ""
   435|    for k in ("api_key", "api"):
   436|        v = model_cfg.get(k)
   437|        if isinstance(v, str) and v.strip():
   438|            cfg_api_key = v.strip()
   439|            break
   440|    requested_norm = (requested_provider or "").strip().lower()
   441|    cfg_provider = cfg_provider.strip().lower()
   442|
   443|    env_openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "").strip()
   444|
   445|    # Use config base_url when available and the provider context matches.
   446|    # OPENAI_BASE_URL env var is no longer consulted — config.yaml is
   447|    # the single source of truth for endpoint URLs.
   448|    use_config_base_url = False
   449|    if cfg_base_url.strip() and not explicit_base_url:
   450|        if requested_norm == "auto":
   451|            if not cfg_provider or cfg_provider == "auto":
   452|                use_config_base_url = True
   453|        elif requested_norm == "custom" and cfg_provider == "custom":
   454|            use_config_base_url = True
   455|
   456|    base_url = (
   457|        (explicit_base_url or "").strip()
   458|        or (cfg_base_url.strip() if use_config_base_url else "")
   459|        or env_openrouter_base_url
   460|        or OPENROUTER_BASE_URL
   461|    ).rstrip("/")
   462|
   463|    # Choose API key based on whether the resolved base_url targets OpenRouter.
   464|    # When hitting OpenRouter, prefer OPENROUTER_API_KEY (issue #289).
   465|    # When hitting a custom endpoint (e.g. Z.ai, local LLM), prefer
   466|    # OPENAI_API_KEY so the OpenRouter key doesn't leak to an unrelated
   467|    # provider (issues #420, #560).
   468|    _is_openrouter_url = "openrouter.ai" in base_url
   469|    if _is_openrouter_url:
   470|        api_key_candidates = [
   471|            explicit_api_key,
   472|            os.getenv("OPENROUTER_API_KEY"),
   473|            os.getenv("OPENAI_API_KEY"),
   474|        ]
   475|    else:
   476|        # Custom endpoint: use api_key from config when using config base_url (#1760).
   477|        # When the endpoint is Ollama Cloud, check OLLAMA_API_KEY — it's
   478|        # the canonical env var for ollama.com authentication.
   479|        _is_ollama_url = "ollama.com" in base_url.lower()
   480|        api_key_candidates = [
   481|            explicit_api_key,
   482|            (cfg_api_key if use_config_base_url else ""),
   483|            (os.getenv("OLLAMA_API_KEY") if _is_ollama_url else ""),
   484|            os.getenv("OPENAI_API_KEY"),
   485|            os.getenv("OPENROUTER_API_KEY"),
   486|        ]
   487|    api_key = next(
   488|        (str(candidate or "").strip() for candidate in api_key_candidates if has_usable_secret(candidate)),
   489|        "",
   490|    )
   491|
   492|    source = "explicit" if (explicit_api_key or explicit_base_url) else "env/config"
   493|
   494|    # When "custom" was explicitly requested, preserve that as the provider
   495|    # name instead of silently relabeling to "openrouter" (#2562).
   496|    # Also provide a placeholder API key for local servers that don't require
   497|    # authentication — the OpenAI SDK requires a non-empty api_key string.
   498|    effective_provider = "custom" if requested_norm == "custom" else "openrouter"
   499|
   500|    # For custom endpoints, check if a credential pool exists
   501|    if effective_provider == "custom" and base_url:
   502|        pool_result = _try_resolve_from_custom_pool(
   503|            base_url, effective_provider, _parse_api_mode(model_cfg.get("api_mode")),
   504|        )
   505|        if pool_result:
   506|            return pool_result
   507|
   508|    if effective_provider == "custom" and not api_key and not _is_openrouter_url:
   509|        api_key = "no-key-required"
   510|
   511|    return {
   512|        "provider": effective_provider,
   513|        "api_mode": _parse_api_mode(model_cfg.get("api_mode"))
   514|        or _detect_api_mode_for_url(base_url)
   515|        or "chat_completions",
   516|        "base_url": base_url,
   517|        "api_key": api_key,
   518|        "source": source,
   519|    }
   520|
   521|
   522|def _resolve_explicit_runtime(
   523|    *,
   524|    provider: str,
   525|    requested_provider: str,
   526|    model_cfg: Dict[str, Any],
   527|    explicit_api_key: Optional[str] = None,
   528|    explicit_base_url: Optional[str] = None,
   529|) -> Optional[Dict[str, Any]]:
   530|    explicit_api_key = str(explicit_api_key or "").strip()
   531|    explicit_base_url = str(explicit_base_url or "").strip().rstrip("/")
   532|    if not explicit_api_key and not explicit_base_url:
   533|        return None
   534|
   535|    if provider == "anthropic":
   536|        cfg_provider = str(model_cfg.get("provider") or "").strip().lower()
   537|        cfg_base_url = ""
   538|        if cfg_provider == "anthropic":
   539|            cfg_base_url = str(model_cfg.get("base_url") or "").strip().rstrip("/")
   540|        base_url = explicit_base_url or cfg_base_url or "https://api.anthropic.com"
   541|        api_key = explicit_api_key
   542|        if not api_key:
   543|            from agent.anthropic_adapter import resolve_anthropic_token
   544|
   545|            api_key = resolve_anthropic_token()
   546|            if not api_key:
   547|                raise AuthError(
   548|                    "No Anthropic credentials found. Set ANTHROPIC_TOKEN or ANTHROPIC_API_KEY, "
   549|                    "run 'claude setup-token', or authenticate with 'claude /login'."
   550|                )
   551|        return {
   552|            "provider": "anthropic",
   553|            "api_mode": "anthropic_messages",
   554|            "base_url": base_url,
   555|            "api_key": api_key,
   556|            "source": "explicit",
   557|            "requested_provider": requested_provider,
   558|        }
   559|
   560|    if provider == "openai-codex":
   561|        base_url = explicit_base_url or DEFAULT_CODEX_BASE_URL
   562|        api_key = explicit_api_key
   563|        last_refresh = None
   564|        if not api_key:
   565|            creds = resolve_codex_runtime_credentials()
   566|            api_key = creds.get("api_key", "")
   567|            last_refresh = creds.get("last_refresh")
   568|            if not explicit_base_url:
   569|                base_url = creds.get("base_url", "").rstrip("/") or base_url
   570|        return {
   571|            "provider": "openai-codex",
   572|            "api_mode": "codex_responses",
   573|            "base_url": base_url,
   574|            "api_key": api_key,
   575|            "source": "explicit",
   576|            "last_refresh": last_refresh,
   577|            "requested_provider": requested_provider,
   578|        }
   579|
   580|    if provider == "nous":
   581|        state = auth_mod.get_provider_auth_state("nous") or {}
   582|        base_url = (
   583|            explicit_base_url
   584|            or str(state.get("inference_base_url") or auth_mod.DEFAULT_NOUS_INFERENCE_URL).strip().rstrip("/")
   585|        )
   586|        # Only use agent_key for inference — access_token is an OAuth token for the
   587|        # portal API (minting keys, refreshing tokens), not for the inference API.
   588|        # Falling back to access_token sends an OAuth bearer token to the inference
   589|        # endpoint, which returns 404 because it is not a valid inference credential.
   590|        api_key = explicit_api_key or str(state.get("agent_key") or "").strip()
   591|        expires_at = state.get("agent_key_expires_at") or state.get("expires_at")
   592|        if not api_key:
   593|            creds = resolve_nous_runtime_credentials(
   594|                min_key_ttl_seconds=max(60, int(os.getenv("HERMES_NOUS_MIN_KEY_TTL_SECONDS", "1800"))),
   595|                timeout_seconds=float(os.getenv("HERMES_NOUS_TIMEOUT_SECONDS", "15")),
   596|            )
   597|            api_key = creds.get("api_key", "")
   598|            expires_at = creds.get("expires_at")
   599|            if not explicit_base_url:
   600|                base_url = creds.get("base_url", "").rstrip("/") or base_url
   601|        return {
   602|            "provider": "nous",
   603|            "api_mode": "chat_completions",
   604|            "base_url": base_url,
   605|            "api_key": api_key,
   606|            "source": "explicit",
   607|            "expires_at": expires_at,
   608|            "requested_provider": requested_provider,
   609|        }
   610|
   611|    pconfig = PROVIDER_REGISTRY.get(provider)
   612|    if pconfig and pconfig.auth_type == "api_key":
   613|        env_url = ""
   614|        if pconfig.base_url_env_var:
   615|            env_url = os.getenv(pconfig.base_url_env_var, "").strip().rstrip("/")
   616|
   617|        base_url = explicit_base_url
   618|        if not base_url:
   619|            if provider in ("kimi-coding", "kimi-coding-cn"):
   620|                creds = resolve_api_key_provider_credentials(provider)
   621|                base_url = creds.get("base_url", "").rstrip("/")
   622|            else:
   623|                base_url = env_url or pconfig.inference_base_url
   624|
   625|        api_key = explicit_api_key
   626|        if not api_key:
   627|            creds = resolve_api_key_provider_credentials(provider)
   628|            api_key = creds.get("api_key", "")
   629|            if not base_url:
   630|                base_url = creds.get("base_url", "").rstrip("/")
   631|
   632|        api_mode = "chat_completions"
   633|        if provider == "copilot":
   634|            api_mode = _copilot_runtime_api_mode(model_cfg, api_key)
   635|        elif provider == "xai":
   636|            api_mode = "codex_responses"
   637|        else:
   638|            configured_mode = _parse_api_mode(model_cfg.get("api_mode"))
   639|            if configured_mode:
   640|                api_mode = configured_mode
   641|            elif base_url.rstrip("/").endswith("/anthropic"):
   642|                api_mode = "anthropic_messages"
   643|
   644|        return {
   645|            "provider": provider,
   646|            "api_mode": api_mode,
   647|            "base_url": base_url.rstrip("/"),
   648|            "api_key": api_key,
   649|            "source": "explicit",
   650|            "requested_provider": requested_provider,
   651|        }
   652|
   653|    return None
   654|
   655|
   656|def resolve_runtime_provider(
   657|    *,
   658|    requested: Optional[str] = None,
   659|    explicit_api_key: Optional[str] = None,
   660|    explicit_base_url: Optional[str] = None,
   661|) -> Dict[str, Any]:
   662|    """Resolve runtime provider credentials for agent execution."""
   663|    requested_provider = resolve_requested_provider(requested)
   664|
   665|    custom_runtime = _resolve_named_custom_runtime(
   666|        requested_provider=requested_provider,
   667|        explicit_api_key=explicit_api_key,
   668|        explicit_base_url=explicit_base_url,
   669|    )
   670|    if custom_runtime:
   671|        custom_runtime["requested_provider"] = requested_provider
   672|        return custom_runtime
   673|
   674|    provider = resolve_provider(
   675|        requested_provider,
   676|        explicit_api_key=explicit_api_key,
   677|        explicit_base_url=explicit_base_url,
   678|    )
   679|    model_cfg = _get_model_config()
   680|    explicit_runtime = _resolve_explicit_runtime(
   681|        provider=provider,
   682|        requested_provider=requested_provider,
   683|        model_cfg=model_cfg,
   684|        explicit_api_key=explicit_api_key,
   685|        explicit_base_url=explicit_base_url,
   686|    )
   687|    if explicit_runtime:
   688|        return explicit_runtime
   689|
   690|    should_use_pool = provider != "openrouter"
   691|    if provider == "openrouter":
   692|        cfg_provider = str(model_cfg.get("provider") or "").strip().lower()
   693|        cfg_base_url = str(model_cfg.get("base_url") or "").strip()
   694|        env_openai_base_url = os.getenv("OPENAI_BASE_URL", "").strip()
   695|        env_openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "").strip()
   696|        has_custom_endpoint = bool(
   697|            explicit_base_url
   698|            or env_openai_base_url
   699|            or env_openrouter_base_url
   700|        )
   701|        if cfg_base_url and cfg_provider in {"auto", "custom"}:
   702|            has_custom_endpoint = True
   703|        has_runtime_override = bool(explicit_api_key or explicit_base_url)
   704|        should_use_pool = (
   705|            requested_provider in {"openrouter", "auto"}
   706|            and not has_custom_endpoint
   707|            and not has_runtime_override
   708|        )
   709|
   710|    try:
   711|        pool = load_pool(provider) if should_use_pool else None
   712|    except Exception:
   713|        pool = None
   714|    if pool and pool.has_credentials():
   715|        entry = pool.select()
   716|        pool_api_key = ""
   717|        if entry is not None:
   718|            pool_api_key = (
   719|                getattr(entry, "runtime_api_key", None)
   720|                or getattr(entry, "access_token", "")
   721|            )
   722|        # For Nous, the pool entry's runtime_api_key is the agent_key — a
   723|        # short-lived inference credential (~30 min TTL).  The pool doesn't
   724|        # refresh it during selection (that would trigger network calls in
   725|        # non-runtime contexts like `hermes auth list`).  If the key is
   726|        # expired, clear pool_api_key so we fall through to
   727|        # resolve_nous_runtime_credentials() which handles refresh + mint.
   728|        if provider == "nous" and entry is not None and pool_api_key:
   729|            min_ttl = max(60, int(os.getenv("HERMES_NOUS_MIN_KEY_TTL_SECONDS", "1800")))
   730|            nous_state = {
   731|                "agent_key": getattr(entry, "agent_key", None),
   732|                "agent_key_expires_at": getattr(entry, "agent_key_expires_at", None),
   733|            }
   734|            if not _agent_key_is_usable(nous_state, min_ttl):
   735|                logger.debug("Nous pool entry agent_key expired/missing, falling through to runtime resolution")
   736|                pool_api_key = ""
   737|        if entry is not None and pool_api_key:
   738|            return _resolve_runtime_from_pool_entry(
   739|                provider=provider,
   740|                entry=entry,
   741|                requested_provider=requested_provider,
   742|                model_cfg=model_cfg,
   743|                pool=pool,
   744|            )
   745|
   746|    if provider == "nous":
   747|        try:
   748|            creds = resolve_nous_runtime_credentials(
   749|                min_key_ttl_seconds=max(60, int(os.getenv("HERMES_NOUS_MIN_KEY_TTL_SECONDS", "1800"))),
   750|                timeout_seconds=float(os.getenv("HERMES_NOUS_TIMEOUT_SECONDS", "15")),
   751|            )
   752|            return {
   753|                "provider": "nous",
   754|                "api_mode": "chat_completions",
   755|                "base_url": creds.get("base_url", "").rstrip("/"),
   756|                "api_key": creds.get("api_key", ""),
   757|                "source": creds.get("source", "portal"),
   758|                "expires_at": creds.get("expires_at"),
   759|                "requested_provider": requested_provider,
   760|            }
   761|        except AuthError:
   762|            if requested_provider != "auto":
   763|                raise
   764|            # Auto-detected Nous but credentials are stale/revoked —
   765|            # fall through to env-var providers (e.g. OpenRouter).
   766|            logger.info("Auto-detected Nous provider but credentials failed; "
   767|                        "falling through to next provider.")
   768|
   769|    if provider == "openai-codex":
   770|        try:
   771|            creds = resolve_codex_runtime_credentials()
   772|            return {
   773|                "provider": "openai-codex",
   774|                "api_mode": "codex_responses",
   775|                "base_url": creds.get("base_url", "").rstrip("/"),
   776|                "api_key": creds.get("api_key", ""),
   777|                "source": creds.get("source", "hermes-auth-store"),
   778|                "last_refresh": creds.get("last_refresh"),
   779|                "requested_provider": requested_provider,
   780|            }
   781|        except AuthError:
   782|            if requested_provider != "auto":
   783|                raise
   784|            # Auto-detected Codex but credentials are stale/revoked —
   785|            # fall through to env-var providers (e.g. OpenRouter).
   786|            logger.info("Auto-detected Codex provider but credentials failed; "
   787|                        "falling through to next provider.")
   788|
   789|    if provider == "qwen-oauth":
   790|        try:
   791|            creds = resolve_qwen_runtime_credentials()
   792|            return {
   793|                "provider": "qwen-oauth",
   794|                "api_mode": "chat_completions",
   795|                "base_url": creds.get("base_url", "").rstrip("/"),
   796|                "api_key": creds.get("api_key", ""),
   797|                "source": creds.get("source", "qwen-cli"),
   798|                "expires_at_ms": creds.get("expires_at_ms"),
   799|                "requested_provider": requested_provider,
   800|            }
   801|        except AuthError:
   802|            if requested_provider != "auto":
   803|                raise
   804|            logger.info("Qwen OAuth credentials failed; "
   805|                        "falling through to next provider.")
   806|
   807|    if provider == "copilot-acp":
   808|        creds = resolve_external_process_provider_credentials(provider)
   809|        return {
   810|            "provider": "copilot-acp",
   811|            "api_mode": "chat_completions",
   812|            "base_url": creds.get("base_url", "").rstrip("/"),
   813|            "api_key": creds.get("api_key", ""),
   814|            "command": creds.get("command", ""),
   815|            "args": list(creds.get("args") or []),
   816|            "source": creds.get("source", "process"),
   817|            "requested_provider": requested_provider,
   818|        }
   819|
   820|    # Anthropic (native Messages API)
   821|    if provider == "anthropic":
   822|        from agent.anthropic_adapter import resolve_anthropic_token
   823|        token = resolve_anthropic_token()
   824|        if not token:
   825|            raise AuthError(
   826|                "No Anthropic credentials found. Set ANTHROPIC_TOKEN or ANTHROPIC_API_KEY, "
   827|                "run 'claude setup-token', or authenticate with 'claude /login'."
   828|            )
   829|        # Allow base URL override from config.yaml model.base_url, but only
   830|        # when the configured provider is anthropic — otherwise a non-Anthropic
   831|        # base_url (e.g. Codex endpoint) would leak into Anthropic requests.
   832|        cfg_provider = str(model_cfg.get("provider") or "").strip().lower()
   833|        cfg_base_url = ""
   834|        if cfg_provider == "anthropic":
   835|            cfg_base_url = (model_cfg.get("base_url") or "").strip().rstrip("/")
   836|        base_url = cfg_base_url or "https://api.anthropic.com"
   837|        return {
   838|            "provider": "anthropic",
   839|            "api_mode": "anthropic_messages",
   840|            "base_url": base_url,
   841|            "api_key": token,
   842|            "source": "env",
   843|            "requested_provider": requested_provider,
   844|        }
   845|
   846|    # AWS Bedrock (native Converse API via boto3)
   847|    if provider == "bedrock":
   848|        from agent.bedrock_adapter import (
   849|            has_aws_credentials,
   850|            resolve_aws_auth_env_var,
   851|            resolve_bedrock_region,
   852|            is_anthropic_bedrock_model,
   853|        )
   854|        # When the user explicitly selected bedrock (not auto-detected),
   855|        # trust boto3's credential chain — it handles IMDS, ECS task roles,
   856|        # Lambda execution roles, SSO, and other implicit sources that our
   857|        # env-var check can't detect.
   858|        is_explicit = requested_provider in ("bedrock", "aws", "aws-bedrock", "amazon-bedrock", "amazon")
   859|        if not is_explicit and not has_aws_credentials():
   860|            raise AuthError(
   861|                "No AWS credentials found for Bedrock. Configure one of:\n"
   862|                "  - AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY\n"
   863|                "  - AWS_PROFILE (for SSO / named profiles)\n"
   864|                "  - IAM instance role (EC2, ECS, Lambda)\n"
   865|                "Or run 'aws configure' to set up credentials.",
   866|                code="no_aws_credentials",
   867|            )
   868|        # Read bedrock-specific config from config.yaml
   869|        from hermes_cli.config import load_config as _load_bedrock_config
   870|        _bedrock_cfg = _load_bedrock_config().get("bedrock", {})
   871|        # Region priority: config.yaml bedrock.region → env var → us-east-1
   872|        region = (_bedrock_cfg.get("region") or "").strip() or resolve_bedrock_region()
   873|        auth_source = resolve_aws_auth_env_var() or "aws-sdk-default-chain"
   874|        # Build guardrail config if configured
   875|        _gr = _bedrock_cfg.get("guardrail", {})
   876|        guardrail_config = None
   877|        if _gr.get("guardrail_identifier") and _gr.get("guardrail_version"):
   878|            guardrail_config = {
   879|                "guardrailIdentifier": _gr["guardrail_identifier"],
   880|                "guardrailVersion": _gr["guardrail_version"],
   881|            }
   882|            if _gr.get("stream_processing_mode"):
   883|                guardrail_config["streamProcessingMode"] = _gr["stream_processing_mode"]
   884|            if _gr.get("trace"):
   885|                guardrail_config["trace"] = _gr["trace"]
   886|        # Dual-path routing: Claude models use AnthropicBedrock SDK for full
   887|        # feature parity (prompt caching, thinking budgets, adaptive thinking).
   888|        # Non-Claude models use the Converse API for multi-model support.
   889|        _current_model = str(model_cfg.get("default") or "").strip()
   890|        if is_anthropic_bedrock_model(_current_model):
   891|            # Claude on Bedrock → AnthropicBedrock SDK → anthropic_messages path
   892|            runtime = {
   893|                "provider": "bedrock",
   894|                "api_mode": "anthropic_messages",
   895|                "base_url": f"https://bedrock-runtime.{region}.amazonaws.com",
   896|                "api_key": "***",
   897|                "source": auth_source,
   898|                "region": region,
   899|                "bedrock_anthropic": True,  # Signal to use AnthropicBedrock client
   900|                "requested_provider": requested_provider,
   901|            }
   902|        else:
   903|            # Non-Claude (Nova, DeepSeek, Llama, etc.) → Converse API
   904|            runtime = {
   905|                "provider": "bedrock",
   906|                "api_mode": "bedrock_converse",
   907|                "base_url": f"https://bedrock-runtime.{region}.amazonaws.com",
   908|                "api_key": "***",
   909|                "source": auth_source,
   910|                "region": region,
   911|                "requested_provider": requested_provider,
   912|            }
   913|        if guardrail_config:
   914|            runtime["guardrail_config"] = guardrail_config
   915|        return runtime
   916|
   917|    # API-key providers (z.ai/GLM, Kimi, MiniMax, MiniMax-CN)
   918|    pconfig = PROVIDER_REGISTRY.get(provider)
   919|    if pconfig and pconfig.auth_type == "api_key":
   920|        creds = resolve_api_key_provider_credentials(provider)
   921|        # Honour model.base_url from config.yaml when the configured provider
   922|        # matches this provider — mirrors the Anthropic path above.  Without
   923|        # this, users who set model.base_url to e.g. api.minimaxi.com/anthropic
   924|        # (China endpoint) still get the hardcoded api.minimax.io default (#6039).
   925|        cfg_provider = str(model_cfg.get("provider") or "").strip().lower()
   926|        cfg_base_url = ""
   927|        if cfg_provider == provider:
   928|            cfg_base_url = (model_cfg.get("base_url") or "").strip().rstrip("/")
   929|        base_url = cfg_base_url or creds.get("base_url", "").rstrip("/")
   930|        api_mode = "chat_completions"
   931|        if provider == "copilot":
   932|            api_mode = _copilot_runtime_api_mode(model_cfg, creds.get("api_key", ""))
   933|        elif provider == "xai":
   934|            api_mode = "codex_responses"
   935|        else:
   936|            configured_provider = str(model_cfg.get("provider") or "").strip().lower()
   937|            # Only honor persisted api_mode when it belongs to the same provider family.
   938|            configured_mode = _parse_api_mode(model_cfg.get("api_mode"))
   939|            if configured_mode and _provider_supports_explicit_api_mode(provider, configured_provider):
   940|                api_mode = configured_mode
   941|            elif provider in ("opencode-zen", "opencode-go"):
   942|                from hermes_cli.models import opencode_model_api_mode
   943|                api_mode = opencode_model_api_mode(provider, model_cfg.get("default", ""))
   944|            # Auto-detect Anthropic-compatible endpoints by URL convention
   945|            # (e.g. https://api.minimax.io/anthropic, https://dashscope.../anthropic)
   946|            elif base_url.rstrip("/").endswith("/anthropic"):
   947|                api_mode = "anthropic_messages"
   948|        # Strip trailing /v1 for OpenCode Anthropic models (see comment above).
   949|        if api_mode == "anthropic_messages" and provider in ("opencode-zen", "opencode-go"):
   950|            base_url = re.sub(r"/v1/?$", "", base_url)
   951|        return {
   952|            "provider": provider,
   953|            "api_mode": api_mode,
   954|            "base_url": base_url,
   955|            "api_key": creds.get("api_key", ""),
   956|            "source": creds.get("source", "env"),
   957|            "requested_provider": requested_provider,
   958|        }
   959|
   960|    runtime = _resolve_openrouter_runtime(
   961|        requested_provider=requested_provider,
   962|        explicit_api_key=explicit_api_key,
   963|        explicit_base_url=explicit_base_url,
   964|    )
   965|    runtime["requested_provider"] = requested_provider
   966|    return runtime
   967|
   968|
   969|def format_runtime_provider_error(error: Exception) -> str:
   970|    if isinstance(error, AuthError):
   971|        return format_auth_error(error)
   972|    return str(error)
   973|
