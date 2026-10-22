# Survey: LiteLLM Router (litellm/router.py + litellm/router_utils/**)

Commit `93b79d2587d186fb7266556a34a22d03f187a3da`. Scope: 34 source files and 22,984 non-blank LOC, made up of `litellm/router.py` (16,278 lines, 14,635 LOC) and `litellm/router_utils/**` (33 files, 8,349 LOC). The rest of the repository is context only. That covers the proxy server, the provider SDK layer, `router_strategy/`, caching, the Rust gateway and the UI.

## What the system is

LiteLLM is an OpenAI-format gateway and SDK for more than 100 LLM providers. The **Router** is the load-balancing and reliability layer inside the SDK. A caller asks for a *model group* (a public `model_name`). The Router does five things:

1. It picks one concrete *deployment* (a `litellm_params` block holding the provider model, credentials, `api_base` and limits) from the healthy, eligible members of that group.
2. It calls the SDK function (`litellm.acompletion`, `aembedding`, `aresponses`, `anthropic_messages`, files, batches, vector stores, realtime, OCR, search and so on) with that deployment's parameters.
3. It retries within the group.
4. It falls back to other groups on failure.
5. It cools down failing deployments.

The proxy (`litellm/proxy/proxy_server.py`) builds one `litellm.Router(model_list=..., **router_settings)` from its YAML or DB config. All proxy LLM traffic goes through it. SDK users can also construct `Router` directly.

## How it is invoked

- **Construction:** `Router.__init__` (lines 1124-1601, 478 lines) takes about 60 keyword settings (see Configuration). It then calls `set_model_list`, which builds every deployment and its indexes. It also sets up the strategy selectors (`routing_strategy_init`, `routing_groups`) and attaches the endpoint attributes built by `factory_function` (119 `self.factory_function(` call sites). Finally, it registers four router callbacks on the **process-global** `litellm.success_callback` and `failure_callback` lists, plus their async variants.
- **Request entry points:** `acompletion` and `completion`, `aembedding`, `aimage_generation`, `atranscription`, `aspeech`, `arerank`, `atext_completion`, `abatch_completion*`, `schedule_acompletion` (priority queue), `acreate_file`, `acreate_batch` and `aretrieve_batch`. The factory-built attributes add `aresponses`, `aanthropic_messages`, `agenerate_content`, vector-store calls, fine-tuning, realtime, `allm_passthrough_route` and others. The proxy reaches these through `proxy/route_llm_request.py::route_request`.
- **Management calls:** `add_deployment`, `upsert_deployment`, `delete_deployment` and `update_settings`. The proxy calls these when models change in the DB (a background `add_deployment` job runs every 10 seconds) and from management endpoints. `SearchAPIRouter.update_router_search_tools` is driven by a proxy cron that syncs search tools from the DB. That cron is the "scheduled/background job" entry hint.
- **Read-only queries** used by the proxy: `get_model_list`, `get_model_group_info`, `get_model_names`, `get_deployment*`, `map_team_model`, `is_deployment_blocked` and `get_settings`.

## Main paths

1. **Async chat call:**
   1. `acompletion` sets `original_function=_acompletion`. A prompt-management model or a priority request branches off to `schedule_acompletion` (scheduler in `litellm/scheduler.py`).
   2. `async_function_with_fallbacks` calls `async_function_with_retries`, which calls `make_call`, which calls `_acompletion`.
   3. `_acompletion` calls `async_get_available_deployment`. That is `_async_get_available_deployment_unresolved` wrapped by `kubernetes_pod_discovery.async_resolve_pods_after`, which can rewrite `api_base` to a pod IP.
   4. Selection runs these steps in order:
      - `async_pre_routing_hook`: strategy-router (auto, complexity, adaptive or quality) pseudo-deployments and the Claude-Code session router.
      - `async_get_healthy_deployments`: aliases, wildcard patterns, team and access-group filters, then the cooldown, blocked, health-check, reserved-window and PTU-share filters, with batched Redis reads in `RoutingReadBatch`.
      - `_pre_call_checks` and the optional `CustomLogger.async_filter_deployments` checks (rate limits, affinity, prompt cache, continuation).
      - The strategy selector (`router_strategy/*`, out of scope).
      - `_record_routing_decision`.
   5. `_update_kwargs_with_deployment` binds credentials, client, timeouts and metadata. Then `litellm.acompletion` runs (in `main.py`, out of scope). A streaming result is wrapped by `_acompletion_streaming_iterator`, which can retry, fall back or continue (prefill) when the stream fails after it started.
2. **Failure:** the litellm failure callback calls `deployment_callback_on_failure`. That calls `cooldown_handlers.set_cooldown_deployments`, which follows the allowed-fails policy and per-minute failure counters and writes `deployment:<id>:cooldown` to the `CooldownCache` (`DualCache`). `async_function_with_retries` consults the retry policy (`get_retry_from_policy`) and the remaining healthy deployments, and sleeps per `_time_to_sleep_before_retry`. Once retries are exhausted, `async_function_with_fallbacks_common_utils` picks the context-window, content-policy or generic fallback group (`fallback_event_handlers.get_fallback_model_group`). `run_async_fallback` then tries each target after the optional access and budget checks. Headers such as `x-litellm-attempted-retries` and `-fallbacks` are added by `add_retry_fallback_headers`.
3. **Success:** `deployment_callback_on_success` and `_increment_deployment_usage` update TPM/RPM usage counters in `Router.cache`. The I/O-token and model rate-limit checks reconcile their reservations.
4. **Generic endpoints:** `factory_function(litellm.X, call_type=...)` builds a sync or async wrapper (`async_wrapper` is 175 lines). It resolves the deployment, or the model-less file, batch or vector-store variant, then sends the call through `_ageneric_api_call_with_fallbacks`. That path goes through the same retry and fallback loop.

## External systems and data stores

- **LLM providers** through the SDK (`litellm.main`). The router builds and caches OpenAI and Azure clients (`_get_client`, `InitalizeCachedClient`) with a TTL of `client_ttl`.
- **Redis** (single node or cluster, chosen through `REDIS_CLUSTER_NODES`) behind `DualCache` (in-memory plus Redis). It holds usage and TPM/RPM counters, cooldowns (a separate `CooldownCache` store with its own Redis read interval so that other replicas see a cooldown), health-check state, deployment-affinity and prompt-cache pins, Claude-Code session bindings, I/O-token reservations and the scheduler queue.
- **Kubernetes DNS:** pod discovery resolves headless service hosts with `getaddrinfo`. The sync path uses a `ThreadPoolExecutor` and the async path uses `loop.getaddrinfo`.
- **Process-global state:** `litellm.model_cost` (per-deployment prices are written in and replayed through the `_live_routers` WeakSet after a price-map refresh), the `litellm.*_callback` lists, `litellm.cache` and `litellm.model_alias_map`.
- **No database access:** the router never touches PostgreSQL. The proxy owns persistence and pushes changes in.

## Configuration surface

- Constructor keywords: `routing_strategy` (simple-shuffle, least-busy, usage-based-routing and v2, latency-based-routing, cost-based-routing), `routing_strategy_args` and `routing_groups`.
- Reliability: `num_retries`, `retry_policy`, `model_group_retry_policy`, `allowed_fails`, `allowed_fails_policy`, `cooldown_time`, `disable_cooldowns`, `retry_after`, `timeout`, `stream_timeout`, `max_fallbacks`, `fallbacks`, `context_window_fallbacks`, `content_policy_fallbacks` and `default_fallbacks`.
- Routing behavior: `enable_pre_call_checks`, `optional_pre_call_checks`, tag filtering, `model_group_alias`, `enable_weighted_failover`, `enable_mid_stream_fallback_continuation`, health-check routing options, `provider_budget_config`, `alerting_config`, `router_general_settings`, the affinity TTL and config, the fallback access and budget check callables, and `auto_router_capability_limit`.
- Per-deployment settings: `model_info` and `litellm_params` keys such as `rpm`, `tpm`, the I/O-token limits, `access_windows`, `ptu_shares`, `order`, `weight`, `silent_model`, `team_id`, `access_groups`, tags and pricing fields.
- Per-request kwargs: `fallbacks`, `num_retries`, `disable_fallbacks`, `specific_deployment`, `priority`, `metadata` and `litellm_metadata`, plus the `mock_*` test hooks.
- Tunables in `litellm/constants.py` (out of scope).
- Runtime changes: `update_settings` and `set_custom_routing_strategy` change behavior while the router runs, through `setattr` on the router.

## Cross-cutting concerns

- **Retries and fallbacks** are spread across three in-scope places: `router-dispatch`, `router-calls` (stream recovery) and `failure-handling`.
- **Metadata buckets:** the Router writes bookkeeping into whichever request bucket the call surface uses, `metadata` or `litellm_metadata` (`get_router_metadata_variable_name`). It does this **in place**, because the proxy reads those dicts back. That behavior is subtle.
- **Observability:** logging uses `verbose_router_logger` (162 sites). Tracing uses OTel and Datadog spans (`phase_span`, `tracer`). Service hooks run through fire-and-forget `asyncio.create_task`, and Slack alerts go through `handle_error.send_llm_exception_alert`.
- **Secret handling:** API keys are masked in errors and logs (`SensitiveDataMasker` and `redact_string`). Client-side credentials (`clientside_credential_handler`) create ad-hoc deployments.
- **Team and auth scoping:** team-owned deployments, team pattern routers, access groups and the proxy-admin checks in `common_utils`.

## Risks for specification

1. **The `Router` class is one 15,172-line class with 407 methods.** The five range modules cut it at method boundaries, so each extractor sees state (`self.*` attributes) that is assigned in `router-setup` (`__init__`) and read everywhere. Extractors of ranges 2-5 should read `__init__` (lines 1124-1601) as context. Cross-range calls are dense: `_acompletion` in range 2 calls selection in range 5, and both are driven by the loop in range 3.
2. **Dynamic dispatch and metaprogramming:**
   - Many public endpoint methods do not exist as `def`s. There are 119 `self.factory_function(` call sites. `_initialize_*_endpoints` assigns them as `self.X = self.factory_function(litellm.X, call_type=...)`, and the container-file endpoints are assigned in a `setattr` loop over `litellm.containers.endpoint_factory._generated_endpoints`, which is generated from JSON. Their names are not visible in router.py at all.
   - `async_get_available_deployment` and `get_available_deployment` are class attributes wrapped by the pod-discovery decorators.
   - Strategy selectors are looked up by attribute name (`_DEFAULT_SELECTOR_ATTR_BY_STRATEGY`).
   - `update_settings` uses `setattr`.
   - Optional checks are `CustomLogger` objects found through the global callback list.
   - Behavior also depends on `litellm.*` globals that other code mutates.
   The spec must state these name-to-behavior mappings explicitly.
3. **Long functions with many branches on hidden state:**
   - `factory_function` (420 lines) and `async_function_with_fallbacks_common_utils` (281)
   - `_set_model_group_info` (265) and `async_pre_routing_hook` (206)
   - `async_function_with_retries` (205)
   - the three stream iterators (177-214 each), `_pre_call_checks` (181) and `async_get_healthy_deployments` (178)

   Their behavior turns on exception types, metadata flags and the sync/async split. The sync paths (`completion`, `function_with_fallbacks`, `get_available_deployment`) deliberately do less, so weighted failover and mid-stream continuation are async-only.

Other risks:
- Mid-stream semantics (what was already sent to the client before a fallback) are timing-dependent.
- `response_headers.py` is an empty file (0 lines), assigned to `failure-handling`.
- `client_initalization_utils.py` keeps its misspelled name.
- `tests/unit/test_router/test_router.py` is 28,777 lines and spans every range, so it appears in each router-* module's `test_globs`.
- Meta-tests in `tests/code_coverage_tests/router_*` enforce that every router function is tested and stays under 100 lines. Both checks have ignore lists.

## Module map

| id | LOC | content |
|---|---|---|
| router-setup | 2949 | router.py:1-3315. Module helpers, `__init__`, strategy and routing groups, endpoint wiring, completion entry |
| router-calls | 2994 | router.py:3316-6605. `_acompletion`, stream recovery, kwargs binding, per-endpoint wrappers |
| router-dispatch | 2967 | router.py:6606-9865. `factory_function`, embedding, files and batches, retry and fallback loop, deployment callbacks |
| router-deployments | 2969 | router.py:9866-13216. Deployment registry, strategy-router deployments, pricing, model and group info |
| router-selection | 2756 | router.py:13217-16278. Selection pipeline, filters, pre-routing, settings |
| failure-handling | 2629 | Cooldowns, health state, metrics, batched reads, fallback and retry helpers, headers, alerts |
| deployment-limits | 1330 | RPM/TPM and I/O-token checks, PTU shares, access windows |
| affinity-checks | 1658 | Session, user, encrypted-content and prompt-cache affinity, Responses API, continuation checks |
| routing-contracts | 922 | Routing groups, auto-router naming and tuning gate, baseline request, reasoning-effort capability |
| request-targets | 1810 | Wildcard patterns, Kubernetes pods, client-side credentials, semaphores, common utils, batch JSONL, search router |

`depends_on` names in-scope modules only. Out-of-scope dependencies:
- `litellm/router_strategy/**` (selectors, budget limiter, auto, complexity, adaptive and quality routers)
- `litellm/caching/**` (`DualCache`, `RedisCache`, `redis_batch`)
- `litellm/main.py` and `litellm/utils.py`
- `litellm/scheduler.py`
- `litellm/types/router.py` (all router TypedDicts and pydantic types)
- `litellm/integrations/**` (`CustomLogger`, OTel, Prometheus)
- `litellm/constants.py`

The in-scope modules are also used from outside the scope by `litellm/proxy/**`: `proxy_server`, `route_llm_request`, management endpoints, and `parallel_request_limiter_v3`, which imports `ptu_shares` and the deployment metrics. No files were excluded, because nothing in scope is vendored, generated, a fixture or an example.

## Suggested reading order

1. `litellm/types/router.py` (context) and `router-setup`, especially `__init__`, `routing_strategy_init` and `_initialize_*_endpoints`.
2. `router-selection` (`_async_get_available_deployment`, `async_get_healthy_deployments`, `_common_checks_available_deployment`).
3. `router-calls` (`_acompletion`, `_update_kwargs_with_deployment`).
4. `router-dispatch` (`async_function_with_fallbacks`, `async_function_with_retries`, `factory_function`).
5. `failure-handling`.
6. `router-deployments`.
7. `deployment-limits`, then `affinity-checks`.
8. `request-targets`, then `routing-contracts`.
