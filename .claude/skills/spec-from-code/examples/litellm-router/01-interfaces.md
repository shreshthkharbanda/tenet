---
kind: interfaces
prefix: IF
commit: 93b79d2587d186fb7266556a34a22d03f187a3da
status: draft
---
# External interfaces

Scope: the LiteLLM Router (`litellm/router.py`) and its helper package (`litellm/router_utils/**`).
The Router is an in-process library: callers are SDK users and the proxy server, which build one
`Router` and call its methods. Everything outside these two paths is context only.

This file is the index of the external contract. Each entry names the interface and points to the
module claim that specifies its behavior; a fact is stated here only when no module claim states it
(constructor signature defaults, facts that span modules, and gaps between modules).

Terms used below:
- **Model group**: the public `model_name` a caller asks for. Several deployments can share one.
- **Deployment**: one `model_list` entry, made of `model_name`, `litellm_params` (provider model,
  credentials, limits) and `model_info` (always has an `id`).
- **Request kwargs**: the keyword arguments a caller passes to a Router call method. The Router
  reads its own control keys from them and forwards the rest to the provider SDK call.
- **Metadata bucket**: the request kwarg `metadata` or `litellm_metadata`. The Router writes its
  bookkeeping into this dict, changing the caller's dict in place.

## Entry points

### Surfaces that do not exist

- [IF-001] {confirmed} `litellm/router.py:1-460`, `litellm/router_utils/search_api_router.py:1-30` The in-scope code defines no CLI command, no argument parser, no HTTP route, no signal handler and no process exit code; every entry point is a Python callable.
- [IF-002] {confirmed} `litellm/router.py:1630-1652` The Router has no async close or context-manager protocol; its teardown entry points are `discard()` ([RSETUP-062], [RSETUP-291]) and `reset()` ([RSELECT-184]).

### Library API: module-level exports of `litellm.router`

- [IF-003] {confirmed} `litellm/__init__.py:1448`, `litellm/router.py:1107` `Router` is importable both as `litellm.router.Router` and as `litellm.Router`.
- [IF-004] {confirmed} `litellm/router.py:478-512` `model_info_is_active_for_environment(model_info)` returns `True` when `model_info` is `None` or has no `supported_environments` ([RSETUP-202]), and otherwise, once the checks of [RSETUP-203]-[RSETUP-206] pass, whether `LITELLM_ENVIRONMENT` is in that list ([RSETUP-207]).
- [IF-005] {confirmed} `litellm/router.py:487-505` `model_info_is_active_for_environment` raises `ValueError` for an invalid `supported_environments` value or an unset or invalid `LITELLM_ENVIRONMENT`; the four checks, their order and their exact messages are specified by [RSETUP-203], [RSETUP-204], [RSETUP-205] and [RSETUP-206].
- [IF-006] {confirmed} `litellm/router.py:524` `CLAUDE_CODE_SESSION_ROUTER_BINDING_TARGET` is a module constant whose value is in [RSETUP-252].
- [IF-007] {confirmed} `litellm/router.py:680`, `litellm/router.py:890` `MAX_BUFFERED_PRE_CONTENT_ANTHROPIC_CHUNKS` and `MAX_HELD_PRE_OUTPUT_RESPONSES_EVENTS` are module constants; their values and the stream rules that use them are in [RSETUP-233] and [RSETUP-235].
- [IF-008] {confirmed} `litellm/router.py:997-998` `RoutingArgs` is an enum with the single member `ttl`, whose value and use are stated in [RSETUP-250].
- [IF-009] {confirmed} `litellm/router.py:1017` `RETRY_BREADCRUMB_LIMIT` caps the retry/fallback attempt records kept in a request's `previous_models` metadata ([RDISP-202]); its value is in [RSETUP-251].
- [IF-010] {confirmed} `litellm/router.py:1052-1061` `as_output_cap(value)` coerces a client-sent output cap to a non-negative int or `None`; the exact rules are in [RSETUP-225].
- [IF-011] {confirmed} `litellm/router.py:907-994` `FallbackAwareAnthropicMessagesStream(async_generator, source_iterator)` is the async byte iterator returned for routed Anthropic Messages streams ([RCALL-128]); its `_hidden_params`, read-only `has_buffered_provider_output` / `chunks` / `messages` / `model`, `fallback_headers_adopted` flag and `aclose()` are defined in [RSETUP-238]-[RSETUP-243].
- [IF-012] {confirmed} `litellm/router.py:1020-1049` `FallbackAwareStreamWrapper` subclasses `CustomStreamWrapper`; `adopt_fallback_response_headers(...)` repoints the wrapper's response headers and hidden params at the fallback deployment and sets `fallback_headers_adopted = True`, as stated in [RSETUP-245].
- [IF-013] {confirmed} `litellm/router.py:1005-1014` A Router built with a non-`None` `model_list` joins the module-level live-router set ([RSETUP-023]), and a global price-map refresh replays every live router's deployment prices ([RSETUP-255], [RDEPLOY-085]).

### Library API: `Router` constructor

`Router(**kwargs)` takes keyword arguments only in practice (all have defaults; an unknown keyword
raises `TypeError`, [RSETUP-292]). The table lists every parameter with its declared type and
default; the last column names the module claims that specify what the constructor and later calls
do with it.

| Claim | Parameter | Type | Default | Behavior specified in |
|---|---|---|---|---|
| [IF-020] | `model_list` | list of deployment dicts | `None` | [RSETUP-022], [RSETUP-025], [RDEPLOY-001] |
| [IF-021] | `assistants_config` | `{custom_llm_provider, litellm_params}` | `None` | [RSETUP-005], [RDISP-041] |
| [IF-022] | `search_tools` | list | `None` | [RSETUP-005], [TARGETS-141] |
| [IF-023] | `guardrail_list` | list | `None` | [RSETUP-005], [RCALL-115] |
| [IF-024] | `redis_url`, `redis_host`, `redis_port`, `redis_password`, `redis_db` | str / int | `None` | [RSETUP-006]-[RSETUP-009] |
| [IF-025] | `cache_responses` | bool | `False` | [RSETUP-012], [RSETUP-013], [RCALL-171] |
| [IF-026] | `cache_kwargs` | dict | `{}` | [RSETUP-007] |
| [IF-027] | `caching_groups` | list of tuples | `None` | [RSETUP-043] |
| [IF-028] | `client_ttl` | int seconds | `3600` | [RSETUP-276] |
| [IF-029] | `polling_interval`, `default_priority` | float / int | `None` | [RSETUP-015], [RSETUP-191], [RSETUP-284] |
| [IF-034] | `num_retries` | int | `None` | [RSETUP-031] |
| [IF-036] | `max_fallbacks` | int | `None` | [RSETUP-032] |
| [IF-038] | `timeout`, `stream_timeout` | float seconds | `None` | [RSETUP-033]-[RSETUP-035], [RCALL-082], [RCALL-083] |
| [IF-040] | `default_litellm_params` | dict | `None` | [RSETUP-042], [RSETUP-043], [RCALL-064] |
| [IF-042] | `default_max_parallel_requests` | int | `None` | [RSETUP-016], [TARGETS-077] |
| [IF-043] | `set_verbose`, `debug_level` | bool / `"DEBUG"`\|`"INFO"` | `False` / `"INFO"` | [RSETUP-003] |
| [IF-045] | `default_fallbacks` | list of str | `None` | [RSETUP-038], [RSETUP-039] |
| [IF-047] | `fallbacks`, `context_window_fallbacks`, `content_policy_fallbacks` | list | `[]` | [RSETUP-037], [RSETUP-040], [RSETUP-131] |
| [IF-049] | `model_group_alias` | dict str → str or `{"model", "hidden"}` | `{}` | [RSETUP-017], [RSELECT-011] |
| [IF-050] | `enable_pre_call_checks` | bool | `False` | [RSETUP-001], [RSELECT-048] |
| [IF-051] | `enable_tag_filtering`, `tag_filtering_match_any`, `tag_routing_prefix` | bool, bool, str | `False`, `True`, `""` | [RSETUP-001], [RSELECT-106]-[RSELECT-108] |
| [IF-052] | `plugins` | list of routing plugins | `None` | [RSETUP-016], [RSELECT-085], [RSELECT-120] |
| [IF-053] | `retry_after` | int seconds | `0` | [RSETUP-035], [RDISP-161] |
| [IF-054] | `retry_policy` | `RetryPolicy` or dict | `None` | [RSETUP-053] |
| [IF-056] | `model_group_retry_policy` | dict str → `RetryPolicy` | `{}` | [RSETUP-054], [FAILURE-099] |
| [IF-057] | `allowed_fails` | int | `None` | [RSETUP-026], [FAILURE-042], [FAILURE-047] |
| [IF-058] | `allowed_fails_policy` | `AllowedFailsPolicy` (a dict is converted) | `None` | [RSETUP-055], [RSELECT-171] |
| [IF-059] | `cooldown_time` | float seconds | `None` | [RSETUP-027] |
| [IF-060] | `disable_cooldowns`, `fallback_on_unsupported_params` | bool | `None`, `True` | [RSETUP-028], [FAILURE-028], [RDISP-101] |
| [IF-061] | `routing_strategy`, `routing_strategy_args` | str or `RoutingStrategy`, dict | `"simple-shuffle"`, `{}` | [RSETUP-036], [RSETUP-045], [RSETUP-050], [CONTRACTS-117] |
| [IF-063] | `optional_pre_call_checks` | list of check names | `None` | [RSETUP-136]-[RSETUP-145] |
| [IF-065] | `routing_groups` | list of `RoutingGroup` or dict | `None` | [RSETUP-085]-[RSETUP-091], [CONTRACTS-120] |
| [IF-067] | `provider_budget_config`, `alerting_config` | dict, `AlertingConfig` | `None` | [RSETUP-051], [RSETUP-052], [RSETUP-057] |
| [IF-070] | `router_general_settings` | `RouterGeneralSettings` | `RouterGeneralSettings()` | [RSETUP-004] |
| [IF-071] | `deployment_affinity_ttl_seconds`, `model_group_affinity_config` | int, dict | `3600`, `None` | [RSETUP-020], [RSETUP-137], [RSETUP-146] |
| [IF-073] | `ignore_invalid_deployments` | bool | `False` | [RSETUP-001], [RDEPLOY-033], [RDEPLOY-049] |
| [IF-074] | `enable_health_check_routing`, `health_check_staleness_threshold`, `health_check_ignore_transient_errors`, `background_health_check_model_groups` | bool, int, bool, list | `False`, `None`, `False`, `None` | [RSETUP-028]-[RSETUP-030], [RSELECT-142]-[RSELECT-146] |
| [IF-076] | `enable_weighted_failover`, `enable_mid_stream_fallback_continuation` | bool | `False`, `False` | [RSETUP-028], [RDISP-106], [RCALL-019] (sync behavior in [IF-077]) |
| [IF-078] | `fallback_access_check`, `fallback_budget_check` | async callables | `None` | [RSETUP-001], [FAILURE-143], [FAILURE-144] |
| [IF-079] | `auto_router_capability_limit` | callable returning int or `None` | `None` | [RSETUP-001], [RDEPLOY-076] |

- [IF-020] {confirmed} `litellm/router.py:1126`, `litellm/router.py:1404-1415` `model_list` defaults to `None`; how a given list is loaded and what `None` leaves is in [RSETUP-022] and [RSETUP-025].
- [IF-021] {confirmed} `litellm/router.py:1128` `assistants_config` defaults to `None`; it is stored as given ([RSETUP-005]) and read by assistants calls as in [RDISP-041].
- [IF-022] {confirmed} `litellm/router.py:1130` `search_tools` defaults to `None`; how it is stored is in [RSETUP-005], and how search calls pick from it in [TARGETS-141] and [TARGETS-146].
- [IF-023] {confirmed} `litellm/router.py:1132` `guardrail_list` defaults to `None`; how it is stored is in [RSETUP-005], and how `aguardrail` picks from it in [RCALL-115].
- [IF-024] {confirmed} `litellm/router.py:1134-1138` The Redis parameters `redis_url`, `redis_host`, `redis_port`, `redis_password` and `redis_db` all default to `None`; what each does is in [RSETUP-006]-[RSETUP-009].
- [IF-025] {confirmed} `litellm/router.py:1139` `cache_responses` defaults to `False`; its instance storage is in [RSETUP-013] and its use as the `caching` argument of provider calls in [RCALL-171].
- [IF-026] {confirmed} `litellm/router.py:1140`, `litellm/router.py:1303-1326` `cache_kwargs` defaults to `{}`; how it is merged into the Redis config is in [RSETUP-007].
- [IF-027] {confirmed} `litellm/router.py:1141`, `litellm/router.py:1497` `caching_groups` defaults to `None`; where the constructor writes it is in [RSETUP-043].
- [IF-028] {confirmed} `litellm/router.py:1142` `client_ttl` and its default are specified in [RSETUP-276]; [RSELECT-280] records that nothing reads it.
- [IF-029] {confirmed} `litellm/router.py:1144-1145`, `litellm/router.py:1346-1347` `polling_interval` and `default_priority` (both default `None`) go to the scheduler and the router as stated in [RSETUP-015].
- [IF-030] {confirmed} `litellm/router.py:1303-1326` Redis is enabled by `redis_url`, or by `redis_host` together with `redis_port`; the exact condition is in [RSETUP-006] and how the arguments are passed in [RSETUP-007].
- [IF-031] {confirmed} `litellm/router.py:1318-1322` Passing `redis_db` logs a deprecation warning and still applies the database index, as stated in [RSETUP-008] (it is ignored entirely when no Redis backend is configured, [RSETUP-009]).
- [IF-032] {confirmed} `litellm/router.py:1328-1332` When `cache_responses` is truthy and `litellm.cache` is `None`, the constructor creates the process-global `litellm.cache`; the cache type rule is in [RSETUP-012].
- [IF-033] {confirmed} `litellm/router.py:1654-1669` When the Redis config has no truthy `startup_nodes`, a `REDIS_CLUSTER_NODES` secret or env value can supply them and switch construction to a Redis cluster client; the exact rule is in [RSETUP-010].
- [IF-034] {confirmed} `litellm/router.py:1147` `num_retries` defaults to `None`, which leaves the count to the global and library fallbacks of [RSETUP-031].
- [IF-035] {confirmed} `litellm/router.py:1439-1444` The effective `num_retries` follows the precedence stated in [RSETUP-031] (argument, then `litellm.num_retries`, then `openai.DEFAULT_MAX_RETRIES`).
- [IF-036] {confirmed} `litellm/router.py:1148` `max_fallbacks` defaults to `None`, which leaves the bound to the global and env fallbacks of [RSETUP-032].
- [IF-037] {confirmed} `litellm/router.py:1446-1451`, `litellm/constants.py:53` The effective `max_fallbacks` follows the precedence stated in [RSETUP-032] (argument, then `litellm.max_fallbacks`, then `ROUTER_MAX_FALLBACKS`).
- [IF-038] {confirmed} `litellm/router.py:1149-1150` `timeout` and `stream_timeout` default to `None`; what the constructor stores for each is in [RSETUP-033] and [RSETUP-035], and how a call's timeouts are chosen from them and other sources in [RCALL-082] and [RCALL-083].
- [IF-039] {confirmed} `litellm/router.py:1453-1459` The stored `timeout`, the captured per-attempt `request_timeout` and the stored `stream_timeout` are specified in [RSETUP-033], [RSETUP-034] and [RSETUP-035].
- [IF-040] {confirmed} `litellm/router.py:1151`, `litellm/router.py:1490-1494` `default_litellm_params` defaults to `None` (stored as `{}`); a caller's dict is kept and changed in place as described in [RSETUP-043].
- [IF-041] {confirmed} `litellm/router.py:1495-1497` The constructor fills defaults into `default_litellm_params` (`timeout`, `max_retries` `0`, and `metadata.caching_groups`); the exact rules are in [RSETUP-043].
- [IF-042] {confirmed} `litellm/router.py:1152` `default_max_parallel_requests` defaults to `None` and is stored as in [RSETUP-016]; where it enters a deployment's concurrency cap is in [TARGETS-077].
- [IF-043] {confirmed} `litellm/router.py:1153-1154` `set_verbose` defaults to `False` and `debug_level` to `"INFO"`; their effect on the router logger is in [RSETUP-003].
- [IF-044] {confirmed} `litellm/router.py:1283-1288` `set_verbose=True` with `debug_level` sets the router logger level ([RSETUP-003]); every construction also sets the process-global `litellm.suppress_debug_info = True` ([RSETUP-002]).
- [IF-045] {confirmed} `litellm/router.py:1155` `default_fallbacks` defaults to `None`, so no wildcard entry is added unless `litellm.default_fallbacks` is set ([RSETUP-038]).
- [IF-046] {confirmed} `litellm/router.py:1473-1478` `default_fallbacks` (or `litellm.default_fallbacks`) appends a `{"*": ...}` entry to the fallbacks list in place; the exact rule is in [RSETUP-038], the `default_fallbacks=[]` case in [RSETUP-039], and that entry's use as the unknown-model substitute in [RSELECT-028].
- [IF-047] {confirmed} `litellm/router.py:1156-1158`, `litellm/router.py:1467-1484` `fallbacks`, `context_window_fallbacks` and `content_policy_fallbacks` default to `[]`, and an empty value falls back to the matching `litellm.*` global; the per-setting rules are in [RSETUP-037], [RSETUP-038] and [RSETUP-040].
- [IF-048] {confirmed} `litellm/router.py:2616-2628`, `litellm/router.py:1469`, `litellm/router.py:1483` `fallbacks` and `content_policy_fallbacks` are validated at construction and `context_window_fallbacks` is not; the selection and validation rules are in [RSETUP-037], [RSETUP-040] and [RSETUP-131] (messages in [IF-201]).
- [IF-049] {confirmed} `litellm/router.py:1159` `model_group_alias` defaults to `{}`; how a falsy value is replaced is in [RSETUP-017], and alias resolution in [RSELECT-011].
- [IF-050] {confirmed} `litellm/router.py:1160` `enable_pre_call_checks` defaults to `False`; it is stored as in [RSETUP-001], and the context-window, RPM, region and parameter checks it enables are in [RSELECT-048] and [RSELECT-200]-[RSELECT-211].
- [IF-051] {confirmed} `litellm/router.py:1161-1163` `enable_tag_filtering` defaults to `False`; the `tag_filtering_match_any` and `tag_routing_prefix` defaults and their storage are in [RSETUP-001], and their effect on strategy choice in [RSELECT-106]-[RSELECT-108].
- [IF-052] {confirmed} `litellm/router.py:1164` `plugins` defaults to `None`; it is copied into the routing-plugin list as in [RSETUP-016], runs on the async path as in [RSELECT-085]-[RSELECT-089], and makes sync selection raise as in [RSELECT-120].
- [IF-053] {confirmed} `litellm/router.py:1165` `retry_after` and its default are stored as in [RSETUP-035]; it is the minimum retry back-off of [RDISP-161].
- [IF-054] {confirmed} `litellm/router.py:1166` `retry_policy` defaults to `None`; how a given value is converted or ignored is in [RSETUP-053].
- [IF-055] {confirmed} `litellm/router.py:1558-1570` A dict `retry_policy` becomes a `RetryPolicy` and a value of any other non-`RetryPolicy` type is ignored, as in [RSETUP-053]; the policy fields and how one is chosen for an exception are in [FAILURE-102] and [FAILURE-103].
- [IF-056] {confirmed} `litellm/router.py:1167` `model_group_retry_policy` and its shared `{}` default are stored as in [RSETUP-054]; how a group's entry replaces `retry_policy` is in [FAILURE-099] and [FAILURE-100].
- [IF-057] {confirmed} `litellm/router.py:1417-1420`, `litellm/__init__.py:533` `allowed_fails` defaults to `None`; its resolution is in [RSETUP-026], and how it decides cooldowns in [FAILURE-042] and [FAILURE-047].
- [IF-058] {confirmed} `litellm/router.py:1572-1585` `allowed_fails_policy` defaults to `None`; dict conversion is in [RSETUP-055] and the per-exception lookup in [RSELECT-171].
- [IF-059] {confirmed} `litellm/router.py:1421`, `litellm/constants.py:151` `cooldown_time` falls back to its default when falsy, so `0` also means the default; the default and its env var are in [RSETUP-027].
- [IF-060] {confirmed} `litellm/router.py:1171-1172` `disable_cooldowns` defaults to `None`; it and `fallback_on_unsupported_params` are stored as in [RSETUP-028], and their effects are in [FAILURE-028] and [RDISP-101].
- [IF-061] {confirmed} `litellm/router.py:1173`, `litellm/router.py:1175` `routing_strategy` defaults to `"simple-shuffle"`; how it is stored is in [RSETUP-036], and the shared `routing_strategy_args` default in [RSETUP-050].
- [IF-062] {confirmed} `litellm/router_utils/routing_groups.py:20-35`, `litellm/router.py:1515-1523` `routing_strategy` must be an accepted strategy name, a `RoutingStrategy` member or `None`, otherwise the constructor raises `ValueError` ([IF-202]); the accepted names are in [CONTRACTS-116] and the accept/raise rule in [CONTRACTS-117].
- [IF-063] {confirmed} `litellm/router.py:1174` `optional_pre_call_checks` defaults to `None`; the constructor registers a given list as in [RSETUP-056], and what each name registers is in [RSETUP-136]-[RSETUP-145].
- [IF-064] {confirmed} `litellm/router.py:3173-3188`, `litellm/router.py:5044-5059` Whether `acompletion` goes through the priority scheduler is decided as in [RSETUP-190] and [RSETUP-191]; with an int `default_priority` every `acompletion` raises `TypeError` instead ([RSETUP-284]; suspected defect [RSETUP-297]).
- [IF-065] {confirmed} `litellm/router.py:1176` `routing_groups` defaults to `None`; building and replacing groups is in [RSETUP-085]-[RSETUP-091].
- [IF-066] {confirmed} `litellm/router_utils/routing_groups.py:38-100`, `litellm/types/router.py:87-115` `routing_groups` entries are validated at construction ([RSETUP-086], [RSETUP-087]) and on `update_settings(routing_groups=...)` ([RSELECT-162]); the parsing rules and failure messages are in [CONTRACTS-122] and [CONTRACTS-124]-[CONTRACTS-128].
- [IF-067] {confirmed} `litellm/router.py:1177-1178` `provider_budget_config` and `alerting_config` default to `None`; their effects are in [RSETUP-051], [RSETUP-052] and [RSETUP-057].
- [IF-068] {confirmed} `litellm/router.py:1551-1557` When the budget limiter should start ([RSETUP-052]), `"router_budget_limiting"` is added to the optional pre-call checks as in [RSETUP-051].
- [IF-069] {confirmed} `litellm/router.py:1596-1597`, `litellm/router.py:16208-16228` When `alerting_config` is set, the constructor starts Slack alerting and registers it on the process-global callback lists ([RSETUP-057], [RSELECT-177]; the `AlertingConfig` type: [CFG-078]).
- [IF-070] {confirmed} `litellm/router.py:1179`, `litellm/router.py:1289` `router_general_settings` defaults to `RouterGeneralSettings()` (`async_only_mode=False`, `pass_through_all_models=False`); the shared default and the replacement of a falsy value are in [RSETUP-004].
- [IF-071] {confirmed} `litellm/router.py:1180-1181` `deployment_affinity_ttl_seconds` and `model_group_affinity_config` and their defaults are stored as in [RSETUP-020]; they configure the affinity check of [RSETUP-137].
- [IF-072] {confirmed} `litellm/router.py:1400-1402`, `litellm/router.py:1593-1594` A non-empty `model_group_affinity_config` registers the deployment-affinity check even when no global affinity check is enabled ([RSETUP-056], [RSETUP-146]), and unknown affinity flags in it only produce a warning ([RSETUP-021]).
- [IF-073] {confirmed} `litellm/router.py:1182` `ignore_invalid_deployments` defaults to `False`; it is stored as in [RSETUP-001] and decides skip-or-raise as in [RDEPLOY-033] and [RDEPLOY-049].
- [IF-074] {confirmed} `litellm/router.py:1183-1186` `enable_health_check_routing` defaults to `False`, `health_check_staleness_threshold` to `None`, `health_check_ignore_transient_errors` to `False` and `background_health_check_model_groups` to `None`; how they are stored is in [RSETUP-028]-[RSETUP-030].
- [IF-075] {confirmed} `litellm/router.py:1429-1437`, `litellm/constants.py:1945-1952` The health-state staleness threshold is resolved as in [RSETUP-030] and applied to health marks as in [FAILURE-083] and [FAILURE-086].
- [IF-076] {confirmed} `litellm/router.py:1187-1188`, `litellm/router.py:1427` `enable_weighted_failover` and `enable_mid_stream_fallback_continuation` default to `False`; how they are stored is in [RSETUP-028], and their effects in [RDISP-106] and [RCALL-019].
- [IF-077] {confirmed} `litellm/router.py:1229-1230`, `litellm/router.py:8879-8885`, `litellm/router.py:3028-3035`, `litellm/router.py:8258-8273` The constructor docstring calls weighted failover async-only and says sync `completion()` uses the regular fallback flow, but sync calls run the same async fallback dispatcher ([RDISP-165]) and their attempts stamp `failed_deployment_id` ([RSETUP-176]), so with `enable_weighted_failover` the sync path also re-picks within the group as in [RDISP-106] and [RDISP-120]; mid-stream continuation is never applied to sync streams ([RCALL-038], [RCALL-169]).
- [IF-078] {confirmed} `litellm/router.py:1189-1190`, `litellm/types/router.py:1192-1213` `fallback_access_check` and `fallback_budget_check` default to `None`; they are stored as in [RSETUP-001] and awaited per fallback target as in [FAILURE-143] and [FAILURE-144].
- [IF-079] {confirmed} `litellm/router.py:1191`, `litellm/types/router.py:1216-1225` `auto_router_capability_limit` defaults to `None`; it is stored as in [RSETUP-001] and called on every capability check as in [RDEPLOY-076].
- [IF-080] {confirmed} `litellm/router.py:1529-1548` The constructor registers the router's usage and cooldown callbacks on the process-global callback lists as in [RSETUP-049], so they fire for every litellm call in the process, routed or not ([RDISP-196]).
- [IF-081] {confirmed} `litellm/router.py:1599-1601`, `litellm/router.py:1614-1623` After setup, the constructor binds the factory-built endpoint attributes ([RSETUP-058], [RSETUP-111]) and applies default settings, which register the continuation-prefill check when `enable_mid_stream_fallback_continuation` is on ([RSETUP-060], [RSETUP-061]).
- [IF-082] {confirmed} `litellm/router.py:1604-1612` `Router.get_valid_args()` (static) is specified in [RSETUP-059].

### Library API: request call methods

Every call method takes `model` (a model group name, a deployment id, an alias, a routing-group name or
a wildcard-matched name, resolved as in [RSELECT-020]) plus request kwargs. Unless a claim says
otherwise, the call runs inside the retry and fallback loop ([IF-140] to [IF-149]), and the provider
SDK function receives the chosen deployment's `litellm_params` merged under the request kwargs, as in
[RCALL-049] and [RCALL-196].

- [IF-300] {confirmed} `litellm/router.py:2908-2925` `completion(model, messages, **kwargs)` is the synchronous chat entry point specified in [RSETUP-157] and [RSETUP-160]; it runs the retry/fallback loop to completion as in [RDISP-165].
- [IF-301] {confirmed} `litellm/router.py:3159-3210` `async acompletion(model, messages, stream=False, **kwargs)` is specified in [RSETUP-186]-[RSETUP-194].
- [IF-302] {confirmed} `litellm/router.py:3176-3182`, `litellm/router.py:5115-5125` When the requested group is prompt-managed (exactly one deployment whose `litellm_params.model` contains `/` and whose text before the first `/` is one of `litellm._known_custom_logger_compatible_callbacks`, for example `langfuse/gpt-4o`; `openai/gpt-4o` does not qualify, [RCALL-093]), `acompletion` skips the scheduler and resolves the prompt ([RCALL-094]-[RCALL-097]); the resolved target model is then called directly through `litellm.acompletion` without retries or fallbacks when it is not a router model group ([RCALL-098]), and otherwise through the router's retry/fallback loop for that target group ([RCALL-099]).
- [IF-303] {confirmed} `litellm/router.py:5159-5178` On that prompt-management path an invalid `prompt_id` or `prompt_variables` raises `ValueError` ([IF-204]); the exact conditions, the `litellm_agent/` exemption and the messages are in [RCALL-095].
- [IF-304] {confirmed} `litellm/router.py:4416-4438` Before routing, the router entry points stamp a `litellm_trace_id` and the metadata bucket's `model_group` / `model_group_alias` as stated in [RCALL-058] and [RCALL-059].
- [IF-305] {confirmed} `litellm/router.py:4610-4625`, `litellm/router.py:4685` After a deployment is chosen, the metadata bucket receives the deployment fields listed in [RCALL-068] (`deployment`, `model_info`, `api_base`, `deployment_model_name` and the pod-routing key), and the request kwarg `model_info` is set to the deployment's `model_info` ([RCALL-076]).
- [IF-306] {confirmed} `litellm/router.py:4643-4660` Deployment `tags` and the credential-name tag are added to the request's metadata `tags` as in [RCALL-073] and [RCALL-074].
- [IF-307] {confirmed} `litellm/router.py:4495-4514` Router-level `default_litellm_params` are merged into each call as in [RCALL-064]: absent non-`None` keys are filled, and default `metadata` entries overwrite same-named request metadata keys.
- [IF-308] {confirmed} `litellm/router.py:3000-3009`, `litellm/router.py:4350-4360` When a completion attempt returns a `ModelResponse` that the content-policy rule flags ([RSETUP-172]), the attempt raises `litellm.ContentPolicyViolationError` with message `Response output was blocked.` and `llm_provider=""` ([IF-205]) inside the router, and the retry/fallback loop answers the call from the fallback the rule found; the caller sees the error only when no fallback serves it ([RSETUP-171], [RSETUP-303]). A filtered response the rule does not flag is returned to the caller unchanged.
- [IF-309] {confirmed} `litellm/router.py:4365-4390`, `litellm/router.py:797-815` Streaming `acompletion` reads the first chunk inside the attempt ([RCALL-052], [RCALL-053]), so a stream that fails before its first chunk is retried and falls back like a non-streaming failure.
- [IF-310] {confirmed} `litellm/router.py:2955-2965`, `litellm/router.py:4299-4309`, `litellm/router.py:638-650` Shadow traffic for a deployment's `litellm_params.silent_model` is specified in [RSETUP-177]-[RSETUP-185] (sync path) and in [RCALL-043] and [RCALL-047] (async path).
- [IF-311] {confirmed} `litellm/router.py:4804-4895` `async abatch_completion(models, messages, **kwargs)` is specified in [RCALL-085], [RCALL-086] and [RCALL-087].
- [IF-312] {confirmed} `litellm/router.py:4897-4935` `async abatch_completion_one_model_multiple_requests(model, messages, **kwargs)` is specified in [RCALL-088].
- [IF-313] {confirmed} `litellm/router.py:4954-5024` `async abatch_completion_fastest_response(model, messages, stream=False, **kwargs)` is specified in [RCALL-089] and [RCALL-155].
- [IF-314] {confirmed} `litellm/router.py:5044-5069` `async schedule_acompletion(model, messages, priority, stream=False, **kwargs)` and the `x-litellm-request-prioritization-used` header it sets are specified in [RCALL-091].
- [IF-315] {confirmed} `litellm/router.py:5234-5244` `image_generation(prompt, model, **kwargs)` (sync) and `async aimage_generation(prompt, model, **kwargs)` are specified in [RCALL-106] and in [RCALL-100] and [RCALL-101], including the fixed placeholder message used for deployment selection.
- [IF-316] {confirmed} `litellm/router.py:5351-5391`, `litellm/router.py:5434-5515` `async atranscription(file, model, **kwargs)` and `async aspeech(model, input, voice=None, **kwargs)` are specified in [RCALL-100], [RCALL-102] and [RCALL-103].
- [IF-317] {confirmed} `litellm/router.py:5527-5534` `async arerank(model, **kwargs)` is specified in [RCALL-104] and [RCALL-105]; it forwards the language's built-in `input` function to the provider call (suspected defect [RCALL-190]).
- [IF-318] {gap} `litellm/router.py:5530`, `litellm/router.py:5567-5574` Does the provider rerank call ignore, reject or serialize the stray built-in `input` argument that `arerank` forwards? This is the open question [RCALL-182].
- [IF-319] {confirmed} `litellm/router.py:5586-5620` `text_completion(model, prompt, ...)` (sync) makes a single SDK call with no router retries or fallbacks, and ignores its `is_retry`, `is_fallback` and `is_async` parameters; the full behavior is in [RCALL-107].
- [IF-320] {confirmed} `litellm/router.py:5622-5655` `async atext_completion(model, prompt, ...)` is specified in [RCALL-100] and [RCALL-108] (priority scheduling) and [RCALL-109] (attempts).
- [IF-321] {confirmed} `litellm/router.py:5701-5725` `async aadapter_completion(adapter_id, model, ...)` is specified in [RCALL-110] and [RCALL-111].
- [IF-322] {confirmed} `litellm/router.py:6739-6754`, `litellm/router.py:6806-6828` `embedding(model, input, ...)` (sync) and `async aembedding(model, input, ...)` are specified in [RDISP-052]-[RDISP-056].
- [IF-323] {confirmed} `litellm/router.py:6873-7016` `async acreate_file(model, **kwargs)`, its upload to every healthy deployment and its `model_file_id_mapping` hidden param are specified in [RDISP-057]-[RDISP-068].
- [IF-324] {confirmed} `litellm/router.py:6948-6973` The batch-file JSONL rewrite and the `litellm_proxy` `target_model_names` field of `acreate_file` are specified in [RDISP-063] and [RDISP-064].
- [IF-325] {confirmed} `litellm/router.py:7019-7046` `async avector_store_create(model, **kwargs)` is specified in [RDISP-070]-[RDISP-072].
- [IF-326] {confirmed} `litellm/router.py:7108-7130` `async acreate_batch(model, **kwargs)` and `async acancel_batch(model, **kwargs)` are specified in [RDISP-074]-[RDISP-078].
- [IF-327] {confirmed} `litellm/router.py:7193-7300` `async aretrieve_batch(model=None, **kwargs)` probes the healthy deployments of `model` (every deployment when `model` is `None`) in parallel; which deployments are probed is in [RDISP-079]-[RDISP-082] and the result and error rule in [RDISP-083].
- [IF-328] {confirmed} `litellm/router.py:7398-7444` `async alist_batches(model, **kwargs)` and the merged list dict it returns are specified in [RDISP-085]-[RDISP-087].
- [IF-083] {confirmed} `litellm/router.py:5800-5887` `async aguardrail(guardrail_name, original_function, **kwargs)` and `get_available_guardrail(guardrail_name)` are specified in [RCALL-113], [RCALL-114] and [RCALL-115].
- [IF-329] {confirmed} `litellm/router.py:3200-3211`, `litellm/router_utils/handle_error.py:25-70` When an async call method fails, the router schedules the exception alert of [RSETUP-194] and [RCALL-157] and re-raises the original exception; when the alert is sent and what it says are in [FAILURE-175] and [FAILURE-176].

### Library API: endpoint attributes bound at construction

These public methods are not declared in the class body. The constructor binds each one as an
instance attribute, built from an SDK function and a `call_type` string ([RSETUP-110]-[RSETUP-126]).
The `call_type` decides whether the attribute is sync or async and how it is routed.

| Claim | Attributes (call type in parentheses when it differs from the name) | Sync/async | Routing | Specified in |
|---|---|---|---|---|
| [IF-091] | `acreate_assistants`, `adelete_assistant`, `aget_assistants`, `acreate_thread`, `aget_thread`, `a_add_message`, `aget_messages`, `arun_thread` (`assistants`) | async | SDK called directly | [RDISP-008], [RDISP-041] |
| [IF-092] | `amoderation` (`moderation`) | async | one deployment pick, no retries | [RDISP-009], [RDISP-042], [RDISP-043] |
| [IF-093] | `aanthropic_messages`, `anthropic_messages` (`anthropic_messages`), `_arealtime`, `_aresponses_websocket`, `acreate_fine_tuning_job`, `acancel_fine_tuning_job`, `alist_fine_tuning_jobs`, `aretrieve_fine_tuning_job`, `afile_list` (`alist_files`), `aimage_edit`, `agenerate_content`, `agenerate_content_stream`, `aocr`, `adecisions`, `asystemone`, `avideo_generation`, `avideo_list`, `avideo_status`, `avideo_content`, `avideo_remix`, `avideo_create_character`, `avideo_get_character`, `avideo_edit`, `avideo_extension`, `acreate_skill`, `alist_skills`, `aget_skill`, `adelete_skill`, `acreate_realtime_client_secret`, `arealtime_calls`, `acreate_realtime_transcription_session`, `afile_delete`, `afile_content` | async | retry/fallback loop | [RDISP-013], [RDISP-014], [RDISP-019], [RDISP-044]-[RDISP-046] |
| [IF-094] | `aresponses` | async | retry/fallback loop with mid-stream recovery | [RDISP-012], [RCALL-125]-[RCALL-127] |
| [IF-350] | `aget_responses`, `acancel_responses`, `acompact_responses`, `adelete_responses`, `alist_input_items` | async | model taken from `response_id` | [RDISP-017], [RDISP-036] |
| [IF-351] | `responses`, `generate_content`, `generate_content_stream`, `ocr`, `search`, `decisions`, `systemone`, `video_generation`, `video_list`, `video_status`, `video_content`, `video_remix`, `create_container`, `list_containers`, `retrieve_container`, `delete_container` | sync | one pick, no retries or fallbacks | [RDISP-002], [RDISP-022], [RDISP-047]-[RDISP-051] |
| [IF-352] | `asearch` | async | search tools, retry/fallback loop | [RDISP-010], [TARGETS-142], [TARGETS-143] |
| [IF-353] | `avector_store_search`, `avector_store_retrieve`, `avector_store_list`, `avector_store_update`, `avector_store_delete` | async | routed only when `model` is given | [RDISP-018], [RDISP-030], [RDISP-031] |
| [IF-354] | `vector_store_search`, `vector_store_create`, `vector_store_retrieve`, `vector_store_list`, `vector_store_update`, `vector_store_delete` | sync | routed only when `model` is given | [RDISP-003], [RDISP-004] |
| [IF-355] | `avector_store_file_create`, `avector_store_file_list`, `avector_store_file_retrieve`, `avector_store_file_content`, `avector_store_file_update`, `avector_store_file_delete` | async | routed only when `model` is given | [RDISP-011], [RDISP-030], [RDISP-031] |
| [IF-356] | `vector_store_file_create`, `vector_store_file_list`, `vector_store_file_retrieve`, `vector_store_file_content`, `vector_store_file_update`, `vector_store_file_delete` | sync | SDK called directly | [RDISP-005] |
| [IF-357] | `acreate_container`, `alist_containers`, `aretrieve_container`, `adelete_container`, `aupload_container_file`, `alist_container_files`, `aretrieve_container_file`, `adelete_container_file`, `aretrieve_container_file_content` | async | routed by container id or `model` | [RDISP-015], [RDISP-032]-[RDISP-035] |
| [IF-358] | `acreate_interaction`, `create_interaction`, `aget_interaction`, `adelete_interaction`, `acancel_interaction` | async | routed only when `model` is given | [RDISP-020], [RDISP-037]-[RDISP-039], [RDISP-027] |
| [IF-359] | `acreate_agent`, `alist_agents`, `aget_agent`, `adelete_agent`, `alist_agent_versions` (async); `create_agent`, `list_agents`, `get_agent`, `delete_agent`, `list_agent_versions` (sync) | both | SDK called directly | [RDISP-006], [RDISP-021], [RDISP-040] |
| [IF-360] | `allm_passthrough_route` | async | retry/fallback loop, direct call when no deployment | [RDISP-016], [RCALL-117], [RCALL-119] |
| [IF-361] | `aadapter_generate_content`, `video_create_character`, `video_get_character`, `video_edit`, `video_extension`, `get_interaction`, `delete_interaction`, `cancel_interaction`, `upload_container_file`, `list_container_files`, `retrieve_container_file`, `delete_container_file`, `retrieve_container_file_content` | async | none: always returns `None` | [RDISP-023]-[RDISP-026], [RDISP-296] |

- [IF-090] {confirmed} `litellm/router.py:2274-2614`, `litellm/router.py:7471-7890` The constructor binds the attributes in the table above by calling `factory_function(sdk_function, call_type)`; how the call type decides between a plain function and a coroutine function is in [RDISP-001], [RDISP-007] and [RSETUP-127].
- [IF-091] {confirmed} `litellm/router.py:2274-2283`, `litellm/router.py:8054-8070` The assistants attributes are bound as in [RSETUP-110] and call the SDK directly as in [RDISP-008] and [RDISP-041], which also gives the error raised without a provider ([IF-206]).
- [IF-092] {confirmed} `litellm/router.py:7445-7468` `amoderation` is specified in [RDISP-042] and [RDISP-043]; it has no retry or fallback loop.
- [IF-093] {confirmed} `litellm/router.py:7763-7797`, `litellm/router.py:5889-5920`, `litellm/router.py:5951-6044` The generic routed attributes are dispatched as in [RDISP-014] and [RDISP-044]-[RDISP-046], and each attempt selects, binds and calls the SDK as in [RCALL-116]-[RCALL-124].
- [IF-362] {confirmed} `litellm/router.py:7714-7797` Which factory-built attributes forward or drop the wrapper's `custom_llm_provider` and `client` arguments is stated per call type in [RDISP-002]-[RDISP-021]; on most routed attributes both are dropped, so a caller cannot pass them through ([RDISP-014]).
- [IF-363] {confirmed} `litellm/router.py:7753-7762`, `litellm/router.py:7858-7864` `acreate_realtime_client_secret`, `arealtime_calls` and `acreate_realtime_transcription_session` forward `client` ([RDISP-013]); what `afile_delete` and `afile_content` forward is in [RDISP-019].
- [IF-364] {confirmed} `litellm/router.py:2287-2289`, `litellm/router.py:2434-2450` The double binding of `aanthropic_messages` / `anthropic_messages` to one SDK function and the rebinding of `agenerate_content` are specified in [RSETUP-114] and [RSETUP-113].
- [IF-094] {confirmed} `litellm/router.py:7748-7752`, `litellm/router.py:6046-6058` `aresponses` is dispatched as in [RDISP-012], and its attempts and per-attempt stream wrapping are in [RCALL-125]-[RCALL-127].
- [IF-350] {confirmed} `litellm/router.py:7987-8005` The Responses-by-id attributes derive `model` from `response_id` as in [RDISP-036].
- [IF-351] {confirmed} `litellm/router.py:7601-7631`, `litellm/router.py:6670-6737` The sync generic attributes are specified in [RDISP-002] and [RDISP-047]-[RDISP-051]: one deployment through the sync selector, one SDK call, no retry and no fallback.
- [IF-352] {confirmed} `litellm/router.py:7730-7734`, `litellm/router_utils/search_api_router.py:116-179` `asearch` resolves its search tool inside the retry/fallback loop as in [RDISP-010], [TARGETS-142] and [TARGETS-143]; the sync `search` attribute instead uses deployment selection over `model_list` ([RDISP-022], [IF-351]).
- [IF-353] {confirmed} `litellm/router.py:7833-7857`, `litellm/router.py:7896-7927` The async vector-store attributes use the retry/fallback loop only when the call has a truthy `model` ([RDISP-030]); otherwise they call the SDK directly, and only `avector_store_search` gets the keyword `router` set to this Router, overriding any caller value ([RDISP-031]).
- [IF-354] {confirmed} `litellm/router.py:7633-7676` The sync vector-store attributes are specified in [RDISP-003] and [RDISP-004].
- [IF-355] {confirmed} `litellm/router.py:7735-7747`, `litellm/router.py:7896-7927` The async vector-store-file attributes are specified in [RDISP-011], [RDISP-030] and [RDISP-031].
- [IF-356] {confirmed} `litellm/router.py:7678-7697` The sync vector-store-file attributes are specified in [RDISP-005].
- [IF-357] {confirmed} `litellm/router.py:7929-7985` The container attributes and how they route by a LiteLLM-managed `container_id`, a `model` or neither are specified in [RDISP-032]-[RDISP-035].
- [IF-358] {confirmed} `litellm/router.py:8007-8034` The interaction attributes are specified in [RDISP-037]-[RDISP-039].
- [IF-359] {confirmed} `litellm/router.py:7699-7712`, `litellm/router.py:8036-8052` The managed-agent attributes are specified in [RDISP-006] and [RDISP-040].
- [IF-360] {confirmed} `litellm/router.py:7814-7821`, `litellm/router.py:5956-5972`, `litellm/router.py:5922-5949` `allm_passthrough_route` is specified in [RDISP-016], [RCALL-117] and [RCALL-119], including the direct SDK call when no deployment can be selected.
- [IF-361] {confirmed} `litellm/router.py:7714-7890` The attributes listed for [IF-361] have a call type that matches no branch of the async wrapper, so calling them does nothing and resolves to `None` ([RDISP-023]-[RDISP-026]); the sync-named ones in that row are coroutine functions too (suspected defect [RDISP-296]).
- [IF-365] {confirmed} `litellm/router.py:2518-2545`, `litellm/containers/endpoints.json` The container-file attributes are bound at runtime from a JSON-generated endpoint table, as specified in [RSETUP-122] and [RSETUP-123].
- [IF-366] {confirmed} `litellm/router.py:7097-7106` The vector-store override step called during endpoint setup is a no-op ([RDISP-073]); `avector_store_create` is the class method of [RDISP-070], not a factory attribute.

### Library API: lifecycle and settings

- [IF-095] {confirmed} `litellm/router.py:1630-1652` `discard()` is specified in [RSETUP-062], [RSETUP-063] and [RSETUP-064]; it does not close clients or clear caches ([RSETUP-291]).
- [IF-096] {confirmed} `litellm/router.py:16271-16278` `reset()` empties the four process-global success/failure callback lists (removing other routers' and integrations' callbacks too), sets `retry_policy` to `None` and flushes the caches; the exact lists are in [RSELECT-184].
- [IF-097] {confirmed} `litellm/router.py:16263-16269` `flush_cache()` sets the process-global `litellm.cache` to `None` and flushes the router's caches; exactly what is flushed (including a Redis `FLUSHALL`) is in [RSELECT-183].
- [IF-098] {confirmed} `litellm/router.py:1671-1686` `update_redis_cache(cache)` (alias `_update_redis_cache`) attaches `cache` as the Redis tier of the router's caches listed in [RSETUP-065].
- [IF-099] {confirmed} `litellm/router.py:16230-16261`, `litellm/router.py:1821-1824` `set_custom_routing_strategy(CustomRoutingStrategy)` and the removal of that override are specified in [RSELECT-180] and [RSELECT-181].
- [IF-100] {confirmed} `litellm/router.py:2698-2789`, `litellm/types/router.py:165-176` `add_optional_pre_call_checks(names)` registers a check per recognized name as in [RSETUP-136]-[RSETUP-145]; every other name, including `forward_client_headers_by_model_group`, is ignored ([RSETUP-144]).
- [IF-101] {confirmed} `litellm/router.py:2704-2742` The names `deployment_affinity`, `responses_api_deployment_check` and `session_affinity` share one deployment-affinity check whose flags a later call can only turn on; creation is in [RSETUP-137] and the merge into an existing instance in [RSETUP-138].
- [IF-102] {confirmed} `litellm/router.py:2791-2813`, `litellm/router.py:528-534` `set_optional_pre_call_checks(names)` first removes the runtime-toggleable checks not in `names`, then adds `names`; `None` is a no-op. Which checks are toggleable and when removal also touches the global callback list are in [RSETUP-147] and [RSETUP-148].
- [IF-103] {confirmed} `litellm/router.py:13520-13574`, `litellm/constants.py:55-78` `update_settings(**kwargs)` applies only the keys in `RUNTIME_UPDATABLE_ROUTER_SETTINGS` and skips any other key with a debug log, not an error; the exact key list and log text are in [RSELECT-152].
- [IF-104] {confirmed} `litellm/router.py:13523-13541` `update_settings` converts `timeout`, `num_retries`, `retry_after`, `allowed_fails` and `cooldown_time` with `int()`; the truncation and error behavior is in [RSELECT-153].
- [IF-105] {confirmed} `litellm/router.py:13536-13587` In `update_settings`, a changed `routing_strategy` re-initializes the strategy and rebuilds routing groups, and a changed `routing_strategy_args` rebuilds the default selector (keeping the old one and logging an exception if the new args are invalid). `routing_groups` rebuilds the routing groups from the new input, `optional_pre_call_checks`, `enable_mid_stream_fallback_continuation` and `retry_policy` go through their own handlers ([RSELECT-155] to [RSELECT-157]), and the integer keys are converted ([IF-104]); the other allowed keys are set as attributes without validation, so `fallbacks` is not re-validated ([RSELECT-154]).
- [IF-106] {confirmed} `litellm/router.py:13466-13508` `get_settings()` returns a dict of the router's current routing, retry and fallback settings plus `routing_groups` as a list of dicts; the exact keys are in [RSELECT-150] and the value forms in [RSELECT-151].
- [IF-107] {confirmed} `litellm/router.py:13497-13503` For `latency-based-routing`, `get_settings()["routing_strategy_args"]` reports the latency selector's effective args rather than the dict that was passed in; the reported form is in [RSELECT-151].
- [IF-108] {confirmed} `litellm/router.py:1821-1848` `routing_strategy_init(routing_strategy, routing_strategy_args)` is specified in [RSETUP-073] and [RSETUP-074]; calling it directly with a strategy other than the router's leaves the two out of step ([RSETUP-306]).

### Library API: deployment registry

- [IF-110] {confirmed} `litellm/router.py:10552-10642` `set_model_list(model_list)` is specified in [RDEPLOY-001]-[RDEPLOY-011], including the deep copy of the input ([RDEPLOY-001]) and the `os.environ/` secret expansion ([RDEPLOY-006]).
- [IF-111] {confirmed} `litellm/router.py:9945-10111` The checks a model-list row must pass, in order, are in [RDEPLOY-015]-[RDEPLOY-024]; whether a failure raises or skips the row under `ignore_invalid_deployments` is in [RDEPLOY-033].
- [IF-112] {confirmed} `litellm/router.py:11178-11204` `replay_model_cost_registrations()` is specified in [RDEPLOY-085].
- [IF-113] {confirmed} `litellm/router.py:10594-10622` How a deployment without `model_info.id` gets its id, and how an `organization` list expands into several deployments, are specified in [RDEPLOY-007] and [RDEPLOY-009].
- [IF-114] {confirmed} `litellm/router.py:9771-9800` `Router.generate_model_id(model_group, litellm_params)` (static) is specified in [RDISP-240]-[RDISP-243].
- [IF-115] {confirmed} `litellm/router.py:10820-10851` `add_deployment(deployment)` returns `None` without changes for an already-registered id, otherwise registers the deployment with capability flags stripped and returns the stored deployment; the exact condition and steps are in [RDEPLOY-040] and [RDEPLOY-041].
- [IF-116] {confirmed} `litellm/router.py:10175-10189`, `litellm/router.py:10191-10210` `auto_router_capability_violation(capability)` is specified in [RDEPLOY-076], and the registration error it causes in [RDEPLOY-065].
- [IF-117] {confirmed} `litellm/router.py:10970-11039` `upsert_deployment(deployment)` is specified in [RDEPLOY-046]-[RDEPLOY-052].
- [IF-118] {confirmed} `litellm/router.py:11206-11243` `delete_deployment(id)` is specified in [RDEPLOY-053]-[RDEPLOY-056].
- [IF-119] {confirmed} `litellm/router.py:11377-11389` `async arefresh_model_info(client=None)` is specified in [RDEPLOY-105]-[RDEPLOY-111].

### Library API: read-only queries

- [IF-120] {confirmed} `litellm/router.py:13997-14006`, `litellm/router_utils/common_utils.py:75-93` `get_model_from_alias(model)` returns the target group of `model`'s `model_group_alias` entry, or `None`; the accepted entry shapes and the malformed-entry rule are in [RSELECT-011].
- [IF-121] {confirmed} `litellm/router.py:13274-13298` `get_model_list(model_name=None, team_id=None)` is specified in [RSELECT-001], [RSELECT-002] and [RSELECT-281]; it always returns a list, never `None`.
- [IF-122] {confirmed} `litellm/router.py:7215-7221`, `litellm/router.py:7406-7410` Because `get_model_list` never returns `None` ([RSELECT-001]), the `Router not yet initialized.` errors of [RDISP-079] and [RDISP-085] are unreachable, and `alist_batches` for an unknown model returns the empty merged result of [RDISP-087].
- [IF-123] {confirmed} `litellm/router.py:13083-13090` An alias entry with `hidden: True` is left out of `get_model_list()` with no name but still returned when the alias name is asked for directly ([RDEPLOY-170], [RSELECT-281]).
- [IF-124] {confirmed} `litellm/router.py:12929-12948` `get_model_names(team_id=None)` is specified in [RDEPLOY-165].
- [IF-125] {confirmed} `litellm/router.py:12261-12288` `get_model_group_info(model_group, include_hidden=False)` is specified in [RDEPLOY-131]-[RDEPLOY-142].
- [IF-126] {confirmed} `litellm/router.py:11292-11309`, `litellm/router.py:11888-11914` `get_deployment(model_id)`, `get_model_info(id)` and `get_model_group(id)` are specified in [RDEPLOY-095], [RDEPLOY-126] and [RDEPLOY-127].
- [IF-127] {confirmed} `litellm/router.py:11311-11324` `get_deployment_credentials(model_id)` returns the deployment's credential fields, or `None` for an unknown or admin-paused deployment, as stated in [RDEPLOY-097].
- [IF-128] {confirmed} `litellm/router.py:11632-11654` `get_credential_deployment(model_id, team_id=None)` is specified in [RDEPLOY-099] and [RDEPLOY-100].
- [IF-129] {confirmed} `litellm/router.py:11681-11744` `get_deployment_credentials_with_provider(model_id, team_id=None)` is specified in [RDEPLOY-101]-[RDEPLOY-103].
- [IF-130] {confirmed} `litellm/router.py:11758-11886` `get_router_model_info(deployment, received_model_name, id=None)` is specified in [RDEPLOY-120]-[RDEPLOY-125] (errors in [IF-207]).
- [IF-131] {confirmed} `litellm/router.py:12534-12566` `get_model_ids(model_name=None, exclude_team_models=False)` is specified in [RDEPLOY-059].
- [IF-132] {confirmed} `litellm/router.py:1973-2003` `is_recognized_model(model)` and `routing_group_has_alternatives(model_group)` are specified in [RSETUP-096] and [RSETUP-097].
- [IF-133] {confirmed} `litellm/router.py:12767-12828` `map_team_model(team_model_name, team_id, custom_llm_provider=None)` is specified in [RDEPLOY-160] and [RDEPLOY-161].
- [IF-134] {confirmed} `litellm/router.py:16021-16031` `Router.is_deployment_blocked(deployment)` (static) is specified in [RSELECT-143], and `get_fully_blocked_model_names()` in [RDEPLOY-166].
- [IF-135] {confirmed} `litellm/router.py:12290-12355`, `litellm/types/router.py:1176-1180` `async get_model_group_usage(model_group)` is specified in [RDEPLOY-144].
- [IF-136] {confirmed} `litellm/router.py:12421-12455` `async get_remaining_model_group_usage(model_group)` and the rate-limit headers it returns are specified in [RDEPLOY-146].
- [IF-137] {confirmed} `litellm/router.py:14670-14690`, `litellm/router.py:14846-14850`, `litellm/router.py:15802-15806` `async_get_available_deployment(model, request_kwargs, messages=None, input=None, specific_deployment=False)` and `get_available_deployment(model, messages=None, input=None, specific_deployment=False, request_kwargs=None)` return the selected deployment dict; both results pass through Kubernetes pod discovery ([RSELECT-073], [RSELECT-129]).
- [IF-138] {confirmed} `litellm/router.py:14700-14713` The async selector falls back to the sync selection path whenever the top-level `routing_strategy` has no async-native selector, regardless of routing groups; the exact strategy list and what the fallback skips are in [RSELECT-060].
- [IF-139] {inferred} `litellm/router.py:2229-2272`, `litellm/router.py:15778-15791` With top-level `routing_strategy="provider-budget-routing"` and a model outside any routing group, no selector exists ([RSETUP-084], [RSETUP-108]), so every request that resolves to a deployment list (rather than one specific deployment), including a one-deployment group, raises `RouterRateLimitError` ([RSELECT-127]; suspected defect [RSELECT-279]); inferred by reading, no test exercises a request under that strategy.
- [IF-167] {confirmed} `litellm/router.py:14852-14872`, `litellm/router.py:14918-14949` `async_get_available_deployment_for_pass_through(...)` and its sync twin are specified in [RSELECT-130]-[RSELECT-139] (errors in [IF-208]).
- [IF-168] {confirmed} `litellm/router.py:16146-16152`, `litellm/router_utils/get_retry_from_policy.py:52-66` `get_num_retries_from_retry_policy(exception, model_group=None)` is specified in [RSELECT-170], and the policy resolution it delegates to in [FAILURE-099]-[FAILURE-105].
- [IF-169] {confirmed} `litellm/router.py:16154-16206` `get_allowed_fails_from_policy(exception)` is specified in [RSELECT-171] and [RSELECT-172].

### Library API: per-request control kwargs

These request kwargs change router behavior for one call. All other kwargs pass through to the
provider SDK call unchanged ([IF-440]).

| Claim | Kwarg | Effect | Specified in |
|---|---|---|---|
| [IF-370] | `specific_deployment` | `True`: `model` is matched against deployments' `litellm_params.model` | [RSELECT-021], [RSELECT-022], [RSELECT-042] |
| [IF-371] | `fallbacks`, `context_window_fallbacks`, `content_policy_fallbacks` | replace the router's lists for this call whenever the key is present (even as `None`, and without validation); the `content_filter` raise decision still reads the router's `content_policy_fallbacks` | [RDISP-093], [RDISP-250], [RSETUP-303] |
| [IF-372] | `num_retries`, `model_group_retry_policy` | override retry count and per-group policy | [RDISP-131], [RDISP-136], [RDISP-138], [RDISP-139] |
| [IF-373] | `disable_fallbacks` | `True` skips every fallback | [RDISP-093], [RDISP-101] |
| [IF-374] | `include_fallback_errors` | `True` adds `x-litellm-fallback-errors` to a response served by a fallback, one error list per fallback walk (other truthy values also do, [RDISP-119]) | [FAILURE-153], [FAILURE-158], [FAILURE-214] |
| [IF-375] | `max_fallbacks` | per-call bound on fallback-walk nesting depth, checked only when a walk starts | [RDISP-102], [FAILURE-138], [FAILURE-147] |
| [IF-376] | `routing_strategy` | per-call strategy override | [RSETUP-100], [RSETUP-101] |
| [IF-377] | `mock_testing_fallbacks`, `mock_testing_context_fallbacks`, `mock_testing_content_policy_fallbacks`, `mock_testing_rate_limit_error`, `mock_timeout` | inject test failures | [RDISP-094], [RDISP-151], [RDISP-152] |
| [IF-378] | `metadata.user_api_key_team_id`, `metadata.user_api_key_auth` | team scoping and admin access | [TARGETS-082]-[TARGETS-084], [TARGETS-100], [TARGETS-103] |
| [IF-379] | client-side credential keys such as `api_key`, `api_base`, `base_url` | per-request deployment identity | [RCALL-065], [TARGETS-062]-[TARGETS-067] |
| [IF-380] | `reasoning_effort` | strips the deployment's own effort settings | [RSETUP-153] |
| [IF-381] | `tools`, `tool_choice` | merged with the deployment's | [RCALL-066] |
| [IF-382] | `timeout`, `request_timeout`, `stream_timeout` | per-call timeouts | [RCALL-082], [RCALL-083] |

- [IF-370] {confirmed} `litellm/router.py:14129-14152`, `litellm/router.py:14415-14422` With `specific_deployment=True` the candidates are chosen as in [RSELECT-021]; without it, a `model` that is a deployment id (and not also a group name) selects that one deployment as in [RSELECT-022], which skips the health, cooldown and limit filters apart from the paused check ([RSELECT-042]).
- [IF-371] {confirmed} `litellm/router.py:8465-8467`, `litellm/router.py:8572-8575` Request-level `fallbacks`, `context_window_fallbacks` and `content_policy_fallbacks` replace the router's lists for that call whenever the key is present, even with value `None`; see [RDISP-093], and [RDISP-250] for the lack of validation. One exception: the decision whether a `content_filter` response raises at all always reads the router's `content_policy_fallbacks`, because the retry loop removes the request key before each attempt ([RSETUP-303]).
- [IF-372] {confirmed} `litellm/router.py:8577-8583`, `litellm/router.py:8613-8649` How the request's `num_retries` and `model_group_retry_policy` override the retry count, and how a retry policy overrides that count unless the request passed `num_retries=0`, is specified in [RDISP-131], [RDISP-136], [RDISP-138] and [RDISP-139].
- [IF-373] {confirmed} `litellm/router.py:8463-8464`, `litellm/router.py:8181-8188` `disable_fallbacks=True` makes the error left after retries propagate unchanged ([RDISP-101]); the router records the choice in the metadata bucket as `_disable_fallbacks: True` ([RDISP-093], [FAILURE-132]).
- [IF-374] {confirmed} `litellm/router_utils/fallback_event_handlers.py:860-878`, `litellm/router_utils/add_retry_fallback_headers.py:323-356` With `include_fallback_errors=True`, a successful fallback response carries header `x-litellm-fallback-errors` holding a JSON list of `{message, type, param, code}` objects. Each fallback walk contributes its own original error followed by its own failed attempts, and the walks append their lists as the success returns through them, so the list starts with the original error only when the outermost walk's own hop succeeded; after a nested success the innermost walk's errors come first ([FAILURE-153], [FAILURE-214]).
- [IF-375] {confirmed} `litellm/router.py:8198-8201`, `litellm/router_utils/fallback_event_handlers.py:796-798` A request `max_fallbacks` replaces the router's bound for that call. It is checked only when a fallback walk starts, so a walk entered at depth `>= max_fallbacks` raises the original error, but a running walk still attempts every remaining target of its chain past the bound; the rules are in [FAILURE-138] and [FAILURE-147].
- [IF-376] {confirmed} `litellm/router.py:2019-2043` A request `routing_strategy` overrides the model's strategy only for the per-request-capable strategies listed in [RSETUP-100]; any other value is ignored with a warning, never an error ([RSETUP-101]).
- [IF-377] {confirmed} `litellm/router.py:8504-8549`, `litellm/router.py:8789-8813` `mock_testing_fallbacks`, `mock_testing_context_fallbacks` and `mock_testing_content_policy_fallbacks` (bool or boolean string) raise a fallback-triggering error before any provider call, `mock_testing_rate_limit_error=True` raises `RateLimitError` on the first attempt inside the retry loop, and `mock_timeout` is forwarded to the retry loop when not `None` ([RDISP-094]); the error types and exact messages are in [RDISP-151] and [RDISP-152].
- [IF-378] {confirmed} `litellm/router_utils/common_utils.py:39-72`, `litellm/router_utils/common_utils.py:245-309` How the caller's team id and admin role are read from the metadata buckets is in [TARGETS-082]-[TARGETS-084], and how they filter team-owned deployments in [TARGETS-100] and [TARGETS-103].
- [IF-379] {confirmed} `litellm/router.py:4516-4550`, `litellm/router.py:4598-4602`, `litellm/router.py:4294-4329`, `litellm/router_utils/clientside_credential_handler.py:85-143` A request carrying a client-side credential key runs on a per-request deployment copy as in [RCALL-065] and [RCALL-069]; which configured fields a caller-supplied `api_base` or `base_url` clears from that copy is in [TARGETS-063]-[TARGETS-067]. That copy feeds only the request's deployment id, pricing and metadata: the provider call is still built from the deployment's own params overlaid with the request kwargs, so the cleared fields and the admin `api_key` still reach it and the workload-identity disable flag never does ([TARGETS-211]).
- [IF-380] {confirmed} `litellm/router.py:2837-2868` When a request sets `reasoning_effort`, the deployment's own effort controls are stripped from that call's params without changing the stored deployment; the exact keys are in [RSETUP-153].
- [IF-381] {confirmed} `litellm/router.py:4552-4575` How deployment-configured `tools` and `tool_choice` merge with the request's is specified in [RCALL-066].
- [IF-382] {confirmed} `litellm/router.py:4771-4802` The non-stream and stream timeouts are each the first truthy value of a fixed request, service-tier, deployment, router and default chain; the exact orders are in [RCALL-083] (non-stream) and [RCALL-082] (stream).
- [IF-383] {confirmed} `litellm/router_utils/common_utils.py:30-36` Router-only kwargs are stripped before the provider completion call; the key list is in [TARGETS-081] and the merge order in [RCALL-049].
- [IF-384] {confirmed} `litellm/router.py:4665-4684` A request `litellm_credential_name` that conflicts with a per-user GitHub OAuth deployment raises during deployment binding as in [RCALL-075] ([IF-211]).

### Retry and fallback contract

- [IF-140] {confirmed} `litellm/router_utils/fallback_event_handlers.py:674-721`, `litellm/router_utils/fallback_event_handlers.py:830-841` The per-target `fallback_access_check` and `fallback_budget_check` gates, their skip reasons and the targets they never check are specified in [FAILURE-143] and [FAILURE-144].
- [IF-141] {confirmed} `litellm/router.py:8815-8877` The rules under which the router does not retry after a failure and moves to fallbacks are specified, in order, in [RDISP-155], with the 401/403 case in [RDISP-158].
- [IF-142] {confirmed} `litellm/router.py:8636-8662` When a retry policy yields a count for the error, that count replaces the retry count and the retry-eligibility gate is skipped for the whole request, as in [RDISP-138] and [RDISP-140].
- [IF-143] {confirmed} `litellm/router.py:8910-8954` The wait before a retry is specified in [RDISP-160], [RDISP-161] and [RDISP-162].
- [IF-144] {confirmed} `litellm/router.py:8690-8773` Retries re-run the whole call, including a new deployment pick ([RDISP-143], [RDISP-282]); when all fail, the latest error is raised with the attributes of [RDISP-147].
- [IF-385] {confirmed} `litellm/router.py:8552-8566`, `litellm/router.py:14520-14532` A deployment that failed with a non-retryable status is excluded from later retries of the same request unless that would leave no deployment, as in [RDISP-148] and [RSELECT-053].
- [IF-145] {confirmed} `litellm/router.py:8074-8148`, `litellm/router.py:8262-8273` Weighted intra-group failover (`enable_weighted_failover`) is specified in [RDISP-106] and [RDISP-120]-[RDISP-124].
- [IF-146] {confirmed} `litellm/router.py:8204-8258` Fallback across a group's `order` levels is specified in [RDISP-103]-[RDISP-105].
- [IF-147] {confirmed} `litellm/router.py:8276-8410`, `litellm/router_utils/fallback_event_handlers.py:566-623` How the fallback chain is chosen (non-standard list, context-window and content-policy lists, then generic `fallbacks` by exact, provider-adjusted or `"*"` key) is specified in [RDISP-107]-[RDISP-111] and [FAILURE-114]-[FAILURE-116].
- [IF-148] {confirmed} `litellm/router.py:8181-8188`, `litellm/router_utils/fallback_event_handlers.py:255-262` The cases in which no fallback is attempted at all are specified in [RDISP-101] and [FAILURE-113].
- [IF-149] {confirmed} `litellm/router_utils/fallback_event_handlers.py:800-848` Within one request each fallback target is attempted at most once, the group that just failed is skipped, and a request naming a provider-scoped resource falls back only within its own group, as specified in [FAILURE-141], [FAILURE-142] and [FAILURE-145].
- [IF-386] {confirmed} `litellm/router_utils/fallback_event_handlers.py:812-818`, `litellm/types/router.py:1405-1424` A dict fallback target carrying a server-owned workload-identity or token-exchange parameter makes the whole fallback step raise `ValueError` before any target is tried, as specified in [FAILURE-139].
- [IF-387] {confirmed} `litellm/router.py:8177-8189`, `litellm/router.py:8205-8272`, `litellm/router.py:8380-8431`, `litellm/router_utils/common_utils.py:136-209`, `litellm/__init__.py:208` While `litellm.expose_router_debug_in_errors` is `True` (default), a top-level (not nested) async fallback walk whose original exception has a `message` appends an explanation to it: either that no fallback group was found (with the configured fallback keys) or which fallbacks were attempted, skipped as unauthorized or over budget, or failed. Nothing is appended when the error is re-raised before fallback handling or when an order-based fallback walk ran; the exact cases and message texts are in [TARGETS-174] and [TARGETS-090] to [TARGETS-094].
- [IF-388] {confirmed} `litellm/router_utils/common_utils.py:120-133` The truncation of the nested fallback failure text appended to an error is specified in [TARGETS-089].
- [IF-389] {confirmed} `litellm/router.py:8879-8885` The sync `function_with_fallbacks` runs the async retry/fallback loop to completion ([RDISP-165]), so sync calls go through the same retry and fallback decision code as async calls.

### Outputs produced besides return values

Response headers are not set on any HTTP response by the Router. They are written into the response
object's hidden params under `additional_headers` ([FAILURE-159]), and the proxy turns them into HTTP
headers.

| Claim | Header | When | Specified in |
|---|---|---|---|
| [IF-151] | `x-litellm-attempted-retries`, `x-litellm-max-retries` | every success through the retry loop; the second only after a retry | [RDISP-134], [RDISP-143], [FAILURE-156] |
| [IF-152] | `x-litellm-attempted-fallbacks` | every success through the fallback loop: `0` in the requested group, else the outermost walk's depth for the hop the success came through | [RDISP-095], [FAILURE-150], [FAILURE-213] |
| [IF-374] | `x-litellm-fallback-errors` | with `include_fallback_errors=True`, on a success served by a fallback | [FAILURE-158], [FAILURE-214] |
| [IF-153] | `x-litellm-model-group` | every successful routed attempt | [RDEPLOY-147] |
| [IF-314] | `x-litellm-request-prioritization-used` | scheduler path | [RCALL-091] |
| [IF-136] | `x-ratelimit-remaining-tokens`, `x-ratelimit-limit-tokens`, `x-ratelimit-remaining-requests`, `x-ratelimit-limit-requests` | group with `tpm`/`rpm` | [RDEPLOY-146] |
| [IF-157] | `x-ratelimit-limit-input-tokens`, `x-ratelimit-remaining-input-tokens`, `x-ratelimit-reset-input-tokens` and the `output` equivalents | group with `itpm`/`otpm` | [RDEPLOY-146], [LIMITS-113] |
| [IF-158] | `x-litellm-quality-router-model`, `-tier`, `-via`, `-keyword`, `-complexity` | quality-router decision present | [FAILURE-169] |
| [IF-159] | `x-litellm-complexity-router-tier`, `-cause`, `-score`, `-reasoning-effort` | complexity-router decision present | [FAILURE-172], [FAILURE-173] |

- [IF-151] {confirmed} `litellm/router.py:8603`, `litellm/router.py:8699-8705`, `litellm/router_utils/add_retry_fallback_headers.py:306-320` The retry headers `x-litellm-attempted-retries` and `x-litellm-max-retries` are set as in [RDISP-134] (first-try success) and [RDISP-143] (success on a retry), through the helper of [FAILURE-156].
- [IF-152] {confirmed} `litellm/router.py:8486-8489`, `litellm/router_utils/fallback_event_handlers.py:872-876` `x-litellm-attempted-fallbacks` is `0` for a success in the requested group. For a success reached by fallback it is the depth of the outermost fallback walk's hop through which the success arrived, not the number of hops: each walk overwrites the header with its own depth as the response returns through it, so a success found inside a nested walk reports the outermost walk's value ([FAILURE-150], [FAILURE-213]).
- [IF-153] {confirmed} `litellm/router.py:12457-12481`, `litellm/router.py:8775-8786` Every successful routed attempt passes through `set_response_headers` ([RDISP-150]), which sets `x-litellm-model-group`, the response `model_id` and the remaining-usage headers as in [RDEPLOY-147] and [RDEPLOY-148].
- [IF-154] {confirmed} `litellm/router_utils/add_retry_fallback_headers.py:132-139` How a bare async-iterator stream and a dict response are made to carry these headers is specified in [FAILURE-166] and [FAILURE-160].
- [IF-157] {confirmed} `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:748-767` The input/output token rate-limit headers are built as in [LIMITS-113] and added to group usage headers as in [RDEPLOY-146].
- [IF-158] {confirmed} `litellm/router_utils/add_retry_fallback_headers.py:171-188` When `metadata.quality_router_decision` is a dict, its routing fields are echoed as `x-litellm-quality-router-*` response headers; the field-to-header mapping is in [FAILURE-169].
- [IF-159] {confirmed} `litellm/router_utils/add_retry_fallback_headers.py:55-82` When the request's routing decision has `router_type: "complexity"`, the `x-litellm-complexity-router-tier`, `-cause`, `-score` and `-reasoning-effort` headers are added; which decision is read is in [FAILURE-172], and which values qualify in [FAILURE-173].
- [IF-150] {confirmed} `litellm/router.py:9313-9358` The retry breadcrumbs written to metadata `previous_models` and `request_retry_count` on each retry and fallback hop are specified in [RDISP-200]-[RDISP-204].
- [IF-160] {confirmed} `litellm/router.py:9339-9353` Each retry emits the trace event `litellm.routing.retry` when the request's routing decision carries a string `router_model_name`; its attributes are listed in [RDISP-205].
- [IF-161] {confirmed} `litellm/router.py:571`, `litellm/router.py:614-627`, `litellm/router.py:14760-14828`, `litellm/router.py:15653-15800` Each successful pick on the standard async and sync selection paths emits the trace event `litellm.request.deployment_selected` with `litellm.deployment.attempt`, `litellm.deployment.reason` and `litellm.deployment.model_group` (the async pass-through pick emits none, [RSELECT-133]); the attribute values are defined in [RSETUP-216] and the async emission points in [RSELECT-070].
- [IF-162] {confirmed} `litellm/router.py:8585-8600`, `litellm/router.py:8448-8461`, `litellm/router_utils/fallback_event_handlers.py:857-866` The keys the retry loop and the fallback walk write into the metadata bucket are listed in [RDISP-261], with the per-hop copy in [FAILURE-148].
- [IF-163] {confirmed} `litellm/router.py:3191-3199`, `litellm/router.py:4277-4286`, `litellm/router.py:14817-14826` Service-success events for service `ROUTER` are fired in the background as specified in [RSETUP-193], [RCALL-046] and [RSELECT-069].
- [IF-164] {confirmed} `litellm/router_utils/fallback_event_handlers.py:903-956` After each fallback attempt, every registered `CustomLogger` gets a fallback success or failure event as specified in [FAILURE-154].
- [IF-165] {confirmed} `litellm/router_utils/cooldown_handlers.py:501-567`, `litellm/router_utils/cooldown_callbacks.py:21-78` When a deployment enters cooldown, a background task reports it to a registered Prometheus logger, as specified in [FAILURE-052] and [FAILURE-056].
- [IF-166] {confirmed} `litellm/router.py:14830-14844`, `litellm/router.py:9600-9634` When deployment selection or a routing pre-call check fails and the request has a `litellm_logging_obj`, its failure handlers are started in the background before the error is re-raised, as specified in [RSELECT-071], [RDISP-216] and [RDISP-217].

### Events consumed (callbacks the Router registers)

- [IF-180] {confirmed} `litellm/router.py:8957-9006`, `litellm/router.py:9044-9100` `async deployment_callback_on_success(kwargs, completion_response, start_time, end_time)` is specified in [RDISP-170]-[RDISP-174] and [RDISP-181]-[RDISP-183].
- [IF-181] {confirmed} `litellm/router.py:9104-9139` `sync_deployment_callback_on_success(...)` is specified in [RDISP-187].
- [IF-182] {confirmed} `litellm/router.py:9141-9264` `deployment_callback_on_failure(kwargs, completion_response, start_time, end_time)` returns `True` when it put the deployment into cooldown and `False` otherwise; the cases that never cool down and the rest of its behavior are in [RDISP-190]-[RDISP-195].
- [IF-183] {confirmed} `litellm/router.py:9210-9231` The cooldown length for a failure follows the precedence stated in [RDISP-191] (deployment `cooldown_time`, then the provider retry-after header, then the router `cooldown_time`).
- [IF-184] {confirmed} `litellm/router.py:9266-9297`, `litellm/types/router.py:1176-1180` `async_deployment_callback_on_failure(...)` counts a failed request toward the deployment's per-minute RPM key as specified in [RDISP-197] and [RDISP-182].
- [IF-185] {confirmed} `litellm/router.py:1008-1014` The price-map refresh hook installed at import is specified in [RSETUP-255].

### Scheduled and background jobs

- [IF-190] {confirmed} `litellm/router_utils/search_api_router.py:54-87`, `litellm/proxy/proxy_server.py:9540-9575` `SearchAPIRouter.update_router_search_tools(router_instance, search_tools)` (async, static) is specified in [TARGETS-139] and [TARGETS-140]; the proxy calls it when syncing search tools from its database.
- [IF-191] {confirmed} `litellm/router.py:1001-1014`, `litellm/router.py:11377-11389`, `litellm/router_strategy/base_routing_strategy.py:20-42`, `litellm/router_strategy/lowest_tpm_rpm_v2.py:95-100` The Router itself schedules no recurring job at construction, but the `usage-based-routing-v2` selector it builds ([RSETUP-072]) starts its own periodic Redis sync task (with no running event loop it first creates and installs a new one), which is cancelled when the selector is retired ([RSETUP-080]); `arefresh_model_info` ([RDEPLOY-105]) and the search-tool sync ([TARGETS-139]) run only when an outside caller invokes them.
- [IF-192] {confirmed} `litellm/router.py:5098-5113` How `schedule_acompletion` waits for its turn in the shared priority queue, and its wait limit, are specified in [RCALL-091] and [RCALL-173].

### Concurrency limits visible to callers

- [IF-170] {confirmed} `litellm/router_utils/client_initalization_utils.py:16-78`, `litellm/router.py:9702-9716` A deployment's concurrency cap is chosen and enforced as in [TARGETS-076]-[TARGETS-078] and [RDISP-218]; slots are counted per process, not across replicas.
- [IF-171] {confirmed} `litellm/router.py:4339-4390` How long a streaming call holds its concurrency slot is specified in [RCALL-177] (async chat) and [RCALL-195] (other surfaces).
- [IF-172] {confirmed} `litellm/router.py:4868-4895`, `litellm/router.py:5004-5010` The batch-completion methods start every sub-request at once with no concurrency bound ([RCALL-175]).

### Library API: `litellm.router_utils` helpers used outside the Router

These module-level names are imported by the proxy, provider adapters and integrations, so their
names and contracts are part of the interface.

- [IF-400] {confirmed} `litellm/router_utils/common_utils.py:96-117` `resolve_served_model(model, model_alias_map, key_aliases, model_group_alias)` is specified in [TARGETS-087].
- [IF-401] {confirmed} `litellm/router_utils/common_utils.py:48-72` `is_proxy_admin_request(request_kwargs)` and `get_request_team_id(request_kwargs)` are specified in [TARGETS-082], [TARGETS-083] and [TARGETS-084].
- [IF-402] {confirmed} `litellm/router_utils/common_utils.py:427-430` `is_model_capability_field(name)` is specified in [TARGETS-116] and [TARGETS-119].
- [IF-403] {confirmed} `litellm/router_utils/batch_utils.py:171-193` `get_router_metadata_variable_name(function_name)` (alias `_get_router_metadata_variable_name`) returns `"litellm_metadata"` or `"metadata"` by the substring rule in [TARGETS-136].
- [IF-404] {confirmed} `litellm/router_utils/batch_utils.py:197-212` `is_batch_retrieve_call_type(call_type)` is specified in [TARGETS-138].
- [IF-405] {confirmed} `litellm/router_utils/get_retry_from_policy.py:37-49`, `litellm/router_utils/get_retry_from_policy.py:69-70` `resolve_retry_policy(retry_policy, model_group, model_group_retry_policy)` and `reset_retry_policy()` are specified in [FAILURE-099], [FAILURE-100] and [FAILURE-106].
- [IF-406] {confirmed} `litellm/router_utils/fallback_event_handlers.py:581-623` `get_fallback_model_group(fallbacks, model_group)` is specified in [FAILURE-114]-[FAILURE-118].
- [IF-407] {confirmed} `litellm/router_utils/fallback_event_handlers.py:537-578` `fallback_lookup_groups(kwargs, model_group)` returns the ordered, de-duplicated lookup groups defined in [FAILURE-120]; `get_fallback_model_group_for_lookup_groups` lets the first group with a specific chain win and uses `"*"` only after every group missed ([FAILURE-119]).
- [IF-408] {confirmed} `litellm/router_utils/fallback_event_handlers.py:528-534` `fallbacks_disabled_for_request(kwargs)` is specified in [FAILURE-132].
- [IF-409] {confirmed} `litellm/router_utils/fallback_event_handlers.py:652` `PROVIDER_SCOPED_RESOURCE_KEYS` holds the request keys listed in [FAILURE-137].
- [IF-410] {confirmed} `litellm/router_utils/fallback_event_handlers.py:959-986` `check_non_standard_fallback_format(fallbacks)` (alias `_check_non_standard_fallback_format`) is specified in [FAILURE-135].
- [IF-411] {confirmed} `litellm/router_utils/add_retry_fallback_headers.py:220-233`, `litellm/router_utils/add_retry_fallback_headers.py:267-280` `get_hidden_params_dict(response, create=False)` and `get_fallback_errors_from_headers(additional_headers)` are specified in [FAILURE-160] and [FAILURE-162].
- [IF-412] {confirmed} `litellm/router_utils/add_retry_fallback_headers.py:142-155` `response_has_hidden_params(response)` and `ensure_response_additional_headers(response)` are specified in [FAILURE-165] and [FAILURE-164].
- [IF-413] {confirmed} `litellm/router_utils/cooldown_handlers.py:62-78` `mark_advisor_orchestration_failure(exception)` tags the exception object as in [FAILURE-062], so the router never cools down a deployment for it ([RDISP-190]).
- [IF-414] {confirmed} `litellm/router_utils/cooldown_handlers.py:501-567` `set_cooldown_deployments(litellm_router_instance, original_exception, exception_status, deployment=None, time_to_cooldown=None, requested_model_group=None, request_kwargs=None)` returns whether it wrote a cooldown entry; its gates and decision rules are in [FAILURE-021]-[FAILURE-053].
- [IF-415] {confirmed} `litellm/router_utils/router_callbacks/track_deployment_metrics.py:62-113` Per-deployment per-minute success and failure counters (keys rendered for example `dep-a:successes` and `dep-a:fails`, memory tier only, `60` s TTL) are described in [FAILURE-072]; the getters return `0` when a counter is unset ([FAILURE-074]).
- [IF-416] {confirmed} `litellm/router_utils/routing_groups.py:20`, `litellm/router_utils/routing_groups.py:38-100` `VALID_ROUTING_STRATEGIES` is specified in [CONTRACTS-116], and `parse_routing_groups(groups_input, known_model_names=frozenset())` in [CONTRACTS-120] and [CONTRACTS-124]-[CONTRACTS-130].
- [IF-417] {confirmed} `litellm/router_utils/search_api_router.py:89-114`, `litellm/router_utils/search_api_router.py:181-243` Search calls pick uniformly at random among `search_tools` entries with the requested `search_tool_name` ([TARGETS-146]) and call the search function with that entry's provider and credentials plus the remaining parameters, as in [TARGETS-148].
- [IF-418] {confirmed} `litellm/router_utils/access_windows.py:23-75` `access_windows_config_error(model_info, *, model_name)` is specified in [LIMITS-002], and the access-window filtering it guards (active windows, midnight-crossing windows, the window's time zone) in [LIMITS-004]-[LIMITS-012].
- [IF-419] {confirmed} `litellm/router_utils/auto_router_model_naming.py:26`, `litellm/router_utils/auto_router_model_naming.py:70-86` `AUTO_ROUTER_MODEL_PREFIX` is `"auto_router/"` ([CONTRACTS-013]); `classify_strategy_router_model(model)` returns `None`, `"complexity"`, `"adaptive"`, `"quality"` or `"semantic"` by the prefix rules in [CONTRACTS-014]-[CONTRACTS-016].
- [IF-420] {confirmed} `litellm/router_utils/auto_router_model_naming.py:43-56` `STRATEGY_ROUTER_PARAM_FIELDS` is the set of ten strategy-router `litellm_params` fields listed in [CONTRACTS-018].
- [IF-421] {confirmed} `litellm/router_utils/auto_router_model_naming.py:345-357` `capability_limit_violation(*, capability, held, limit)` is specified in [CONTRACTS-063].
- [IF-422] {confirmed} `litellm/router_utils/auto_router_model_naming.py:360-466` `validate_strategy_router_model_write`, `validate_complexity_router_config_write` and `validate_complexity_router_config_placement` return `None` or a rejection string, as specified in [CONTRACTS-023]-[CONTRACTS-028], [CONTRACTS-029]-[CONTRACTS-033] and [CONTRACTS-035].
- [IF-423] {confirmed} `litellm/router_utils/auto_router_tuning_baseline.py:14`, `litellm/router_utils/auto_router_tuning_baseline.py:146-173` `TUNING_BASELINE_PARAM_NAME` is specified in [CONTRACTS-067], and `tuning_quota_violation(...)` and its message in [CONTRACTS-082] and [CONTRACTS-083].
- [IF-424] {confirmed} `litellm/router_utils/reasoning_effort_capability.py:87-120` `declared_reasoning_efforts_for_model(model, custom_llm_provider)` and `nearest_declared_reasoning_effort(requested, declared)` are specified in [CONTRACTS-105] and [CONTRACTS-106].
- [IF-425] {confirmed} `litellm/router_utils/ptu_shares.py:28-36`, `litellm/router_utils/ptu_shares.py:90-100` `PTUTeamCeiling.raw_output_token_limit()` and `deployments_shared_with(deployments, team_id)` are specified in [LIMITS-042] and [LIMITS-031].
- [IF-426] {confirmed} `litellm/router_utils/ptu_shares.py:184-252` `routed_deployments`, `team_servable_deployments` and `model_group_ptu_capacity` are specified in [LIMITS-034], [LIMITS-035] and [LIMITS-045].
- [IF-427] {confirmed} `litellm/router_utils/baseline_request.py:102-153` `capture_baseline_parameters(kwargs, *, include_extra_body=True)` and `baseline_request(kwargs, caller, deployment, ...)` are specified in [CONTRACTS-090]-[CONTRACTS-093] and [CONTRACTS-094]-[CONTRACTS-099].
- [IF-428] {confirmed} `litellm/router_utils/health_state_cache.py:18`, `litellm/router_utils/routing_read_batch.py:33-34`, `litellm/router_utils/cooldown_cache.py:38` The service-target labels `health_checks`, `router_cooldowns_usage`, `router_usage` and `router_cooldowns` are specified in [FAILURE-085], [FAILURE-091] and [FAILURE-018].

### Library API: other caller-visible contracts

- [IF-440] {confirmed} `litellm/router.py:4322-4330`, `litellm/router.py:5993-6004` Request kwargs the Router does not consume are not validated and are forwarded to the provider SDK call, where request values override the deployment's `litellm_params` for the same key ([RCALL-049], [RCALL-154]).
- [IF-441] {confirmed} `litellm/router_utils/common_utils.py:63-72`, `litellm/router.py:14108-14128` The Router trusts the caller's team id and auth object in the metadata buckets as given ([TARGETS-082]-[TARGETS-084]) and does no authentication of its own, so an SDK caller that sets them gets that team's or admin's deployment access during selection ([RSELECT-020], [RSELECT-041]).
- [IF-442] {confirmed} `litellm/router.py:6993-7000` A multi-deployment `acreate_file` fails as a whole when one upload fails, without cleaning up the other uploads ([RDISP-059], [RDISP-281]).
- [IF-443] {confirmed} `litellm/router.py:2815-2835` `print_deployment(deployment)` and the masking it applies are specified in [RSETUP-150]-[RSETUP-152]; selection log lines use its result ([RSELECT-289]).
- [IF-444] {confirmed} `litellm/router.py:1489-1496`, `litellm/main.py:396-434` `router.chat.completions.create(messages, model=None, **kwargs)` calls `completion` (or `acompletion` when `default_litellm_params` had `acompletion: True`), and each kwarg passed is written permanently into the router's `default_litellm_params` dict ([RSETUP-042]), so it also applies to every later call (suspected defect [RSETUP-300]).
- [IF-445] {confirmed} `litellm/router.py:1116-1122` The class-level attribute defaults visible on every Router (including the `model_names` set shared by all instances until a model list is built) are listed in [RSETUP-046].
- [IF-446] {confirmed} `litellm/router.py:11519-11630` `get_configured_token_limits`, `get_configured_mode`, `get_configured_display_name`, `routable_model_group`, `get_configured_service_tiers` and `get_routable_upstream_model` are specified in [RDEPLOY-114]-[RDEPLOY-119].
- [IF-447] {confirmed} `litellm/router.py:14015-14022` `get_routable_deployments(model)` returns the candidate deployments for `model` as a tuple, or an empty tuple when resolution fails; the details are in [RSELECT-012].
- [IF-448] {confirmed} `litellm/router_utils/fallback_event_handlers.py:989-990`, `litellm/router_utils/response_headers.py` `run_non_standard_fallback_format` ([FAILURE-136]) and the module `litellm/router_utils/response_headers.py` ([FAILURE-190]) have no observable behavior.
- [IF-449] {confirmed} `litellm/router.py:1495-1496` Because the constructor defaults `default_litellm_params["max_retries"]` to `0` ([RSETUP-043]) and deployment binding merges it into each call ([RCALL-064]), provider SDK clients do no retries of their own unless the caller sets `max_retries`; retries come only from the Router loop ([RDISP-153]).

## Error catalog

Litellm exception classes add their own class prefix to the message the router passes in, and some
add two (a `ContentPolicyViolationError` renders as `litellm.BadRequestError: litellm.ContentPolicyViolationError: ...`).
The rendered form of each router-raised message is given in the claim each row points to. Errors from
the provider SDK are re-raised as the same object; only the appended explanations in [IF-387], [IF-243]
and [IF-244] change their message.

- [IF-200] {confirmed} `litellm/router.py:487-505` Environment gating raises `ValueError` with one of four messages, one per check of [RSETUP-203]-[RSETUP-206] and decided by the first failing check; the exact text, and how the offending value, the offending entry and the `model_info` argument render (with `str()`: a dict repr for a plain dict, the `ModelInfo` field listing when called by the deployment loader), are stated in those claims and [RSETUP-305].
- [IF-201] {confirmed} `litellm/router.py:2616-2628` Fallback validation raises `ValueError` for a non-dict item or for a dict without exactly one key; the exact messages are in [RSETUP-132] and [RSETUP-133].
- [IF-202] {confirmed} `litellm/router_utils/routing_groups.py:23-35` An unknown strategy raises `ValueError` whose text is `Invalid routing_strategy: '<value>'. Valid options: [...]. Check 'router_settings.routing_strategy' in your config.yaml or the 'routing_strategy' parameter if using the Router SDK directly.`, with `str()` of the value between literal single quotes and the options rendered as the Python list repr of the eight accepted names; the fully rendered text is in [CONTRACTS-117].
- [IF-203] {confirmed} `litellm/router_utils/routing_groups.py:47-79`, `litellm/types/router.py:102-114`, `litellm/router.py:1872-1874` Routing-group validation raises `ValueError` with `routing_groups: group_name must be non-empty.`, `routing_groups: 'default' is reserved for the implicit fallback group.`, `routing_groups: group names must be unique, duplicate group_name '<name>'.` (naming only the lexicographically smallest duplicate, for example `'a'`), one model-overlap message listing every conflicting model (for example `routing_groups: model_name 'a' appears in 'g1' and 'g2' and 'g3'; model_name 'b' appears in 'g1' and 'g2'. Each model may belong to at most one group.`, rendered as in [CONTRACTS-128]), `Priority routing group names must not shadow a model or alias`, `model_priorities requires routing_strategy='priority'`, `Priority routing groups require nonempty, distinct models`, `model_priorities must contain exactly the group's models` or `Priority routing groups use model_priorities, not routing_strategy_args`.
- [IF-204] {confirmed} `litellm/router.py:5172-5178` Prompt-management calls raise `ValueError` for a missing or non-string `prompt_id` or non-dict `prompt_variables`; the exact messages and how the values render are in [RCALL-095].
- [IF-205] {confirmed} `litellm/router.py:3004-3008`, `litellm/router.py:4356-4360` A completion response flagged by the content-policy rule raises `ContentPolicyViolationError` inside the router as specified in [RSETUP-171] (sync attempts) and [RCALL-051] (async attempts).
- [IF-206] {confirmed} `litellm/router.py:8064-8070` Assistants calls without a provider or `assistants_config` raise the plain `Exception` whose exact text, backticks and spacing are given in [RDISP-041].
- [IF-207] {confirmed} `litellm/router.py:11783-11806` The two `ValueError`s of `get_router_model_info` (no deployment, invalid `litellm_params`) and how they render are specified in [RDEPLOY-120].
- [IF-208] {confirmed} `litellm/router.py:14933-14948`, `litellm/router.py:15859-15875` Pass-through selection raises `BadRequestError` for a deployment without `use_in_pass_through` or a group with none; the async messages are in [RSELECT-131] and [RSELECT-132] and the differently worded sync message in [RSELECT-134] and [RSELECT-135].
- [IF-209] {confirmed} `litellm/router.py:15629-15641`, `litellm/router.py:15076-15077` With `plugins` configured, any call that reaches the sync selector raises the `ValueError` stated in [RSELECT-120]; on the async path, plugins that narrow the candidates to nothing raise the `ValueError` stated in [RSELECT-089].
- [IF-210] {confirmed} `litellm/router.py:8525-8548`, `litellm/router.py:8808-8813` Mock flags raise `InternalServerError` (`mock_testing_fallbacks`), `ContextWindowExceededError` (`mock_testing_context_fallbacks`), `ContentPolicyViolationError` (`mock_testing_content_policy_fallbacks`) or `RateLimitError` (`mock_testing_rate_limit_error`), the last carrying `num_retries` from a single-deployment group's config. The exact messages and how the fallback list renders are in [RDISP-151] and [RDISP-152]. For example group `g` with no fallbacks gives `litellm.InternalServerError: This is a mock exception for model=g, to trigger a fallback. Fallbacks=None`, where the list prints with Python `str()`.
- [IF-211] {confirmed} `litellm/router.py:4679-4683` A request-supplied string `litellm_credential_name` that differs from a per-user GitHub OAuth deployment's configured credential name raises `litellm.BadRequestError` (status `400`, `llm_provider=""`, model = the deployment's model group) whose message renders as `litellm.BadRequestError: litellm_credential_name cannot be overridden on a deployment that uses per-user GitHub OAuth`, during deployment binding and before any provider call; the same name, an absent key or a non-string value pass ([RCALL-075]).
- [IF-212] {confirmed} `litellm/types/router.py:1416-1424` A fallback dict carrying a server-owned identity field raises the `ValueError` `Rejected Request: ...` whose full rendered text is in [FAILURE-139].
- [IF-213] {confirmed} `litellm/router.py:14266-14272`, `litellm/types/router.py:882` When no deployment matches the requested name after every resolution step, selection raises the `BadRequestError` `You passed in model=... There are no healthy deployments for this model` specified, with its rendering, in [RSELECT-288].
- [IF-214] {confirmed} `litellm/router.py:14281-14292`, `litellm/types/router.py:883-886` When every candidate is a strategy-router marker, selection raises the `BadRequestError` specified, with its rendering, in [RSELECT-016].
- [IF-215] {confirmed} `litellm/router.py:14294-14310` When an active access window removes every candidate, selection raises the `BadRequestError` `Deployment ... is reserved for another team until ...` specified, with its rendering, in [RSELECT-024].
- [IF-216] {confirmed} `litellm/router.py:14311-14316` When PTU shares withhold every candidate, selection raises the `BadRequestError` `Deployment ... is reserved for the teams holding a PTU share of it` specified in [RSELECT-024].
- [IF-217] {confirmed} `litellm/router.py:14073-14083`, `litellm/router_utils/common_utils.py:282-290` A proxy admin with no team who names a model that several teams own gets the `BadRequestError` `Model name '...' matches deployments from multiple teams. ...` specified in [RSELECT-014] (public-name lookup) and [TARGETS-104] (team filter).
- [IF-218] {confirmed} `litellm/router.py:14415-14422`, `litellm/router.py:15654-15661` When the request resolves to a single paused deployment, selection raises the `ServiceUnavailableError` specified, with its rendering, in [RSELECT-042] (async) and [RSELECT-121] (sync); paused deployments in a group are filtered out instead ([RSELECT-046]).
- [IF-219] {confirmed} `litellm/types/router.py:1113-1144`, `litellm/router_utils/handle_error.py:73-107`, `litellm/router.py:15735-15791` When filtering leaves no deployment, or the strategy selector returns none, selection raises `RouterRateLimitError` (a `ValueError` with `status_code = 429`); its message, cooldown reason and `type` are stated in [FAILURE-179] and [RSELECT-283].
- [IF-220] {confirmed} `litellm/router.py:13980-13983`, `litellm/types/router.py:1092-1105` When pre-call checks exclude every candidate and at least one exclusion was for RPM, selection raises `RouterRateLimitErrorBasic` (a `ValueError` with status `429`); the exact condition and message are in [RSELECT-209].
- [IF-221] {confirmed} `litellm/router.py:13971-13979` With `enable_pre_call_checks`, when no deployment of the group supports the requested params, selection raises the `UnsupportedParamsError` specified, with its full rendered text, in [RSELECT-208].
- [IF-222] {confirmed} `litellm/router.py:13985-13990` With `enable_pre_call_checks`, when no deployment's context window fits the input, selection raises the `ContextWindowExceededError` specified in [RSELECT-210], with per-deployment detail as in [RSELECT-202].
- [IF-223] {confirmed} `litellm/router_utils/client_initalization_utils.py:34-46`, `litellm/types/router.py:877`, `litellm/router.py:4334-4348`, `litellm/router.py:8605-8688` When a deployment's concurrency slots are full, the attempt raises the `RateLimitError` specified, with its message, category and type, in [TARGETS-072] and [TARGETS-073]. Slots are held only on the async call paths, and the Router's retry loop retries that 429 like a provider 429, so a caller sees it only when retries are off or every retry also finds the slots full ([TARGETS-076]).
- [IF-224] {confirmed} `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:196-235`, `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:277-322` With `enforce_model_rate_limits`, a deployment at its TPM or RPM limit raises the `RateLimitError` described in [LIMITS-060] (status `429`, header `retry-after: 60`); the async check's `num_retries=0` is in [LIMITS-061].
- [IF-225] {confirmed} `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:346-364` A deployment over its input or output token-per-minute limit raises the `RateLimitError` specified, with its message and `num_retries=0`, in [LIMITS-099].
- [IF-226] {confirmed} `litellm/router.py:9644-9700` `async_admit_deployment_turn(model_group, opened_on, request_kwargs)` raises `RateLimitError` when the budget limiter or the strategy selector refuses a turn, as specified in [RDISP-221] and [RDISP-223].
- [IF-227] {confirmed} `litellm/router.py:10670-10690` Registration rejects a deployment whose provider is not supported, with one of two errors chosen by how the provider resolves; the full rule is in [RDEPLOY-024]. When the resolver accepts the provider (an explicit `custom_llm_provider` such as `notaprovider`) but it is in no supported list, the error is a plain `Exception("Unsupported provider - notaprovider")`. When no provider can be resolved from the model (for example `foo` or `notaprovider/foo` with no `custom_llm_provider`), the resolver's `litellm.BadRequestError` (`LLM Provider NOT provided. ...`) propagates instead.
- [IF-228] {confirmed} `litellm/router.py:10122-10139` A semantic auto-router deployment missing its config, default model or embedding model raises the `ValueError`s listed, in check order, in [RDEPLOY-063].
- [IF-229] {confirmed} `litellm/router.py:10206-10225`, `litellm/router.py:10439-10441`, `litellm/router.py:10516-10522` Strategy-router registration raises `ValueError` for a capability over the limit ([RDEPLOY-065], text in [CONTRACTS-063]) or a missing complexity, adaptive or quality configuration ([RDEPLOY-066], [RDEPLOY-069], [RDEPLOY-068]).
- [IF-230] {confirmed} `litellm/router.py:10280-10286` Registering a second strategy router with the same `model_name` and tags raises `ValueError`; the message and the four labels are in [RDEPLOY-061].
- [IF-231] {confirmed} `litellm/router.py:10061-10068` An invalid `tag_regex` pattern raises the `ValueError` specified, with a rendered example, in [RDEPLOY-022] before the deployment is added.
- [IF-232] {confirmed} `litellm/router.py:9977-9984` Invalid PTU or `access_windows` config raises `ValueError` with the helper's text, as specified in [RDEPLOY-015] and [RDEPLOY-016].
- [IF-233] {confirmed} `litellm/router.py:10809-10813` A `vertex_ai` pass-through deployment lacking project or location raises the `ValueError` specified in [RDEPLOY-032].
- [IF-234] {confirmed} `litellm/router.py:14139-14157` The `ValueError` of [RSELECT-022] (`LiteLLM Router: Trying to call specific deployment, but Model ID ... does not exist in Model ID map`) needs the id index and the deployment lookup to disagree, which the index helpers prevent ([RDEPLOY-057], [RDEPLOY-058]), so it is unreachable in normal operation; the related empty-filter case is the open question [RSELECT-023].
- [IF-235] {confirmed} `litellm/router.py:6946`, `litellm/router.py:7000`, `litellm/router.py:7275`, `litellm/router.py:7291` File and batch calls raise plain `Exception`s whose messages are in [RDISP-062] (`acreate_file` preconditions), [RDISP-067] and [RDISP-080] (no healthy deployments) and [RDISP-083] (batch not found).
- [IF-236] {confirmed} `litellm/router.py:11300-11307`, `litellm/router.py:11338-11345` `get_deployment` and `get_deployment_by_model_group_name` raise a plain `Exception` for a stored entry of the wrong type, as specified, with rendered examples, in [RDEPLOY-095] and [RDEPLOY-096].
- [IF-237] {confirmed} `litellm/router_utils/search_api_router.py:111-112`, `litellm/router_utils/search_api_router.py:137-138`, `litellm/router_utils/search_api_router.py:217-218` Search calls raise `ValueError` for a missing tool name, an unknown tool or a tool without `search_provider`; the messages and their rendering are in [TARGETS-142], [TARGETS-141] and [TARGETS-147].
- [IF-243] {confirmed} `litellm/router.py:4390-4402` With `litellm.expose_router_debug_in_errors` (default `True`), a `litellm.Timeout` from a routed async chat attempt has the selected deployment's stored `request_timeout`, `timeout` and `stream_timeout` appended to its `message`, rendered with Python `str()` as the deployment stores them (`timeout` and `stream_timeout` are float-or-string fields, so a configured `12` renders `12.0` and a string `'12'` renders `12`; `request_timeout` is not a declared field and renders as configured, for example `7`; unset values render `None`): for example `litellm.Timeout: timed out` becomes `litellm.Timeout: timed out\n\nDeployment Info: request_timeout: None\ntimeout: 12.0\nstream_timeout: 3.0` for a deployment with `timeout: 12` and `stream_timeout: 3`; full rules in [RCALL-056].
- [IF-244] {confirmed} `litellm/router.py:8318-8360` With `litellm.expose_router_debug_in_errors`, a context-window or content-policy error gets a hint appended only when its dedicated list (`context_window_fallbacks` or `content_policy_fallbacks`) is `None`, and the generic fallbacks are then tried. When the dedicated list is set but has no chain for the group, no hint is added, the generic fallbacks are not tried, and the original error is raised with the `No fallback was attempted.` outcome text. The exact hint text, rendering and examples are in [RDISP-109] and [RDISP-110], and the miss behavior in [RDISP-108].
- [IF-245] {confirmed} `litellm/router.py:9585-9623` A `RateLimitError` raised by a routing-strategy pre-call check also puts that deployment into cooldown before it propagates, as specified in [RDISP-216].

| ID | Condition | Error type / message (exact; `<x>` marks a value, rendering in the cited claim) | Surface | Retried / falls back | Specified in |
|---|---|---|---|---|---|
| [IF-200] | `supported_environments` or `LITELLM_ENVIRONMENT` invalid | `ValueError`, one of four messages | constructor and `set_model_list` (row skipped instead with `ignore_invalid_deployments`), `deployment_is_active_for_environment`, direct calls; not `add_deployment` ([RDEPLOY-042]) | n/a | [RSETUP-203]-[RSETUP-206], [RSETUP-305], [RDEPLOY-033] |
| [IF-201] | bad `fallbacks` / `content_policy_fallbacks` item | `ValueError` `Item '<item>' is not a dictionary.` or `Dictionary '<item>' must have exactly one key, but has <n> keys.` | constructor | n/a | [RSETUP-132], [RSETUP-133] |
| [IF-202] | unknown routing strategy | `ValueError` `Invalid routing_strategy: '<value>'. Valid options: [...]. ...` (value via `str()`, options as a list repr) | constructor, `update_settings`, `routing_strategy_init` | n/a | [CONTRACTS-117], [RSETUP-071], [RSELECT-159] |
| [IF-203] | invalid routing groups | `ValueError` with a `routing_groups: ...` message, or one of the `Priority routing group...` / `model_priorities ...` messages | constructor, `update_settings` | n/a | [CONTRACTS-122], [CONTRACTS-124]-[CONTRACTS-128], [RSETUP-087] |
| [IF-204] | prompt-management call without valid prompt id/variables | `ValueError` `Prompt ID is not set or not a string. ...` or `Prompt variables is set but not a dictionary. ...` | `acompletion` | no | [RCALL-095] |
| [IF-205] | content-policy rule flags the response | `ContentPolicyViolationError` `Response output was blocked.` | `completion`, `acompletion` | content-policy fallbacks, or generic fallbacks when that list is `None`; caller sees it only when no fallback serves | [RSETUP-171], [RSETUP-172], [RCALL-051] |
| [IF-206] | assistants call without provider | `Exception` `'custom_llm_provider' must be set. ...` | assistants attributes | no | [RDISP-041] |
| [IF-207] | unknown deployment / invalid `litellm_params` | `ValueError` `Deployment not found` or `Deployment missing valid litellm_params. Got: <type>, deployment_id: <id>` | `get_router_model_info` | n/a | [RDEPLOY-120] |
| [IF-208] | no pass-through-enabled deployment | `BadRequestError` `... use_in_pass_through ...` (async and sync wordings differ) | pass-through selection | no | [RSELECT-131], [RSELECT-132], [RSELECT-134], [RSELECT-135] |
| [IF-209] | `plugins` with sync selection, or plugins remove all | `ValueError` `Router(plugins=[...]) is configured, ...` or `No deployments left after routing-plugin filtering. candidate_models=<list>` | sync calls and async calls delegated to the sync path; async selection | fallbacks only | [RSELECT-120], [RSELECT-089] |
| [IF-210] | `mock_testing_*` flags | `InternalServerError` / `ContextWindowExceededError` / `ContentPolicyViolationError` / `RateLimitError` | calls through the retry/fallback loop | fallbacks; the rate-limit mock also goes through the retry gate | [RDISP-151], [RDISP-152] |
| [IF-211] | conflicting `litellm_credential_name` | `BadRequestError`, rendered `litellm.BadRequestError: litellm_credential_name cannot be overridden on a deployment that uses per-user GitHub OAuth` | routed attempts (deployment binding) | not retried unless a retry policy applies (status `400`); fallbacks | [RCALL-075] |
| [IF-212] | fallback dict with server-owned identity param | `ValueError` `Rejected Request: <param> is a server-owned ...` | fallback step | no | [FAILURE-139] |
| [IF-213] | name resolves to no deployment | `BadRequestError` `You passed in model=<model>. There are no healthy deployments for this model` | all routed calls | fallbacks | [RSELECT-288] |
| [IF-214] | only strategy-router markers | `BadRequestError` `You passed in model=<model>. Every deployment for it is a strategy router marker ...` | all routed calls | fallbacks | [RSELECT-016] |
| [IF-215] | access window reserves all candidates | `BadRequestError` `Deployment <model> is reserved for another team until <HH:MM> <tz>` | all routed calls | fallbacks | [RSELECT-024] |
| [IF-216] | PTU shares withhold all candidates | `BadRequestError` `Deployment <model> is reserved for the teams holding a PTU share of it` | all routed calls | fallbacks | [RSELECT-024] |
| [IF-217] | admin names a model owned by several teams | `BadRequestError` `Model name '<model>' matches deployments from multiple teams. ...` | all routed calls | fallbacks | [RSELECT-014], [TARGETS-104] |
| [IF-218] | the one resolved deployment is paused | `ServiceUnavailableError` `Model '<model>' is currently paused and cannot accept requests.` | all routed calls | fallbacks | [RSELECT-042], [RSELECT-121] |
| [IF-219] | nothing left after cooldown/health/limit filters | `RouterRateLimitError` (`429`) `No deployments available for selected model, Try again in <s> seconds. ...` | all routed calls | fallbacks | [FAILURE-179], [RSELECT-283] |
| [IF-220] | pre-call rate-limit exclusion of all | `RouterRateLimitErrorBasic` (`429`) `No deployments available for selected model.` | all routed calls | fallbacks | [RSELECT-209] |
| [IF-221] | no deployment supports requested params | `UnsupportedParamsError` `no deployment of model=<model> supports [...] ...` | calls with `enable_pre_call_checks` | fallbacks only if `fallback_on_unsupported_params` | [RSELECT-208], [RDISP-101] |
| [IF-222] | input exceeds every context window | `ContextWindowExceededError` `litellm._pre_call_checks: Context Window exceeded ...` | calls with `enable_pre_call_checks` | context-window fallbacks | [RSELECT-210] |
| [IF-223] | concurrency slots full | `RateLimitError` `Deployment has all max_parallel_requests slots in use. ...` | all routed calls | retry, fallbacks | [TARGETS-072], [TARGETS-073] |
| [IF-224] | TPM/RPM limit with `enforce_model_rate_limits` | `RateLimitError` `Model rate limit exceeded. TPM limit=<n>, current usage=<n>` (or `RPM`) | all routed calls | async path: no retry unless the request sets `num_retries` or a retry policy applies; fallbacks | [LIMITS-060], [LIMITS-061], [RDISP-138] |
| [IF-225] | ITPM/OTPM limit | `RateLimitError` `Model rate limit exceeded. ITPM limit=<n>, current usage=<n>` (or `OTPM`) | all routed calls | no retry unless the request sets `num_retries` or a retry policy applies; fallbacks | [LIMITS-099], [RDISP-136], [RDISP-138] |
| [IF-226] | turn admission refused | `RateLimitError` with the budget limiter's message or the no-deployment message | realtime/websocket turns | no | [RDISP-221], [RDISP-223] |
| [IF-227] | unsupported or unresolvable provider | `Exception` `Unsupported provider - <provider>` (for example `Unsupported provider - notaprovider`), or the resolver's `litellm.BadRequestError` `LLM Provider NOT provided. ...` | registration | n/a | [RDEPLOY-024] |
| [IF-228] | semantic auto-router config missing | `ValueError` `... is required for auto-router deployments. ...` | registration | n/a | [RDEPLOY-063] |
| [IF-229] | other strategy-router config missing or over limit | `ValueError` (see claim) | registration | n/a | [RDEPLOY-065], [RDEPLOY-066], [RDEPLOY-068], [RDEPLOY-069] |
| [IF-230] | duplicate strategy router name+tags | `ValueError` `<Kind> deployment <name> with tags [...] already exists. ...` | registration | n/a | [RDEPLOY-061] |
| [IF-231] | invalid `tag_regex` | `ValueError` `Invalid regex in tag_regex for model '<name>': ...` | registration | n/a | [RDEPLOY-022] |
| [IF-232] | invalid PTU / access-window config | `ValueError` (helper text) | registration | n/a | [RDEPLOY-015], [RDEPLOY-016] |
| [IF-233] | vertex pass-through without project/location | `ValueError` `vertex_project, and vertex_location must be set ...` | registration | n/a | [RDEPLOY-032] |
| [IF-234] | id index inconsistency | `ValueError` `LiteLLM Router: Trying to call specific deployment, ...` | unreachable | n/a | [RSELECT-022] |
| [IF-235] | file/batch preconditions | `Exception` `file and file_purpose are required for create_file`, `No healthy deployments found.`, `Unable to find batch in any model. Received errors - []` | `acreate_file`, `aretrieve_batch` | `acreate_file`: retry/fallback loop, falling back only within its own group ([FAILURE-142]); `aretrieve_batch`: no | [RDISP-062], [RDISP-067], [RDISP-080], [RDISP-083] |
| [IF-236] | corrupt model-list entry | `Exception` `Model invalid format - <type>` or `Model Name invalid - <type>` | lookups | n/a | [RDEPLOY-095], [RDEPLOY-096] |
| [IF-237] | search tool missing or misconfigured | `ValueError` `Search tool '<name>' not found in router.search_tools` and others | `asearch` | fallbacks | [TARGETS-141], [TARGETS-142], [TARGETS-147] |
| [IF-083] | unknown guardrail name | `ValueError` `No guardrail found with name: <name>` | `aguardrail` | fallbacks | [RCALL-115] |
| [IF-313] | every fastest-response task failed | `Exception` `All tasks failed` | `abatch_completion_fastest_response` | no | [RCALL-089] |
| [IF-104] | non-integer value for an integer setting | `ValueError` (or `TypeError` for `None`) from `int()` | `update_settings` | n/a | [RSELECT-153] |
