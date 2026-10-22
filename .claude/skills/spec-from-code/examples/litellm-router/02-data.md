---
kind: data
prefix: DATA
commit: 93b79d2587d186fb7266556a34a22d03f187a3da
status: draft
---
# Data

Scope: the state that the LiteLLM Router (`litellm/router.py` and `litellm/router_utils/**`) keeps
beyond one call. This file is an index: each store, key and record shape below points to the module
claim that specifies it. Claims stated here in full are the facts no module owns: values read from
code outside the scope (the shared cache layer, the Responses id codecs, the proxy's SQL), and
invariants that only hold across several modules.

The Router owns no database, schema migration or on-disk file ([DATA-010]). Its durable state is
key/value entries in an optional shared Redis, reached through two-tier caches (process memory first,
Redis second). Everything else lives in process memory, scoped to a router instance or to the process.
The proxy owns persistence (PostgreSQL) and pushes deployments, health results and search tools into
the Router.

Terms used below:
- *Deployment*: one entry of the Router's model list (`model_name`, `litellm_params`, `model_info`).
  Its id is `model_info.id`.
- *Model group*: every deployment that shares one public `model_name`.
- *Two-tier cache*: the shared `DualCache` class (out of scope here). A write goes to process memory and,
  unless the write is marked local-only, also to Redis. A read checks memory first and falls back to
  Redis, then copies a Redis hit back into memory.
- *Minute bucket*: the string `HH-MM` built from the current UTC time with format `%H-%M`. It carries no
  date.

## Stores

### Store inventory

| ID | Store | Medium | Scope | Writers | Readers | Specified in |
|---|---|---|---|---|---|---|
| [DATA-001] | Router cache (`Router.cache`) | memory (200 entries, [DATA-016]) plus optional Redis | per router; Redis tier shared by every process on that Redis | usage callbacks, allowed-fails counters, health results, affinity pins, rate-limit checks, strategy selectors, concurrency slots | selection filters, strategy selectors, usage headers | [RSETUP-014], [RSETUP-269] |
| [DATA-002] | Cooldown store (`CooldownCache.cooldown_store`) | own memory tier plus the Router cache's Redis, attached on first access | per router; Redis tier shared | failure callback | cooldown filter, retry back-off | [FAILURE-008], [RSETUP-027] |
| [DATA-003] | Session-router binding cache | memory (200 entries, [DATA-016]) plus optional Redis | per router; Redis tier shared | pre-routing hook | pre-routing hook | [RSETUP-014], [RSELECT-231] |
| [DATA-004] | Prompt-cache pin cache (`Router.prompt_caching_pin_cache`) | memory (`10000` entries) plus optional Redis | per router; Redis tier shared | prompt-caching success callback | prompt-caching pre-call filter | [RSETUP-014], [AFFINITY-007] |
| [DATA-005] | Deployment registry (`model_list` plus three indexes) | memory | per router | constructor, `set_model_list`, `add_deployment`, `upsert_deployment`, `delete_deployment` | every lookup | [RDEPLOY-186], [RDEPLOY-187], [RDEPLOY-002] |
| [DATA-006] | Process-global cost map (`litellm.model_cost`) | memory | process | deployment registration and price-map replay | cost calculation outside the Router | [RDEPLOY-188] |
| [DATA-007] | Kubernetes pod address cache | memory | per router | pod discovery | pod discovery | [TARGETS-023], [TARGETS-158] |
| [DATA-008] | Derived-value caches (model-group info, access groups, zero-cost, PTU, discovered limits, routing-group rows) | memory | per router, or per class for model-group info | the Router on demand | Router queries | [RSETUP-018], [RSELECT-235], [RDEPLOY-143], [RDEPLOY-109] |
| [DATA-009] | Request scheduler queue | Redis client shared with the Router cache | process; Redis tier shared | `schedule_acompletion` | scheduler | [RSETUP-015] |
| [DATA-159] | Auto-router tuning baselines (proxy database config row `auto_router_tuning_baseline_v3`) | database row written by the proxy | deployment-wide | proxy at boot | proxy license check | [CONTRACTS-067], [CONTRACTS-079], [CONTRACTS-006], [CONTRACTS-139] |

- [DATA-001] {confirmed} `litellm/router.py:1333-1335` The Router cache (`Router.cache`), a two-tier cache over a default memory tier and the constructor's Redis client or none, is specified in [RSETUP-014].
- [DATA-002] {confirmed} `litellm/router.py:1422`, `litellm/router_utils/cooldown_cache.py:41-76` The cooldown store, a separate two-tier cache that picks up the Router cache's Redis client on first access, is specified in [FAILURE-008], and the default cooldown time the Router gives it in [RSETUP-027].
- [DATA-003] {confirmed} `litellm/router.py:1336-1339` The session-router binding cache, a third two-tier cache on the same Redis client, is specified in [RSETUP-014] and [RSELECT-231].
- [DATA-004] {confirmed} `litellm/router.py:1340-1343`, `litellm/constants.py:505` The prompt-cache pin cache is created as in [RSETUP-014]; its `10000`-entry memory cap and its Redis tier are specified in [AFFINITY-007].
- [DATA-005] {confirmed} `litellm/router.py:10552-10642` The deployment registry's in-memory form is specified in [RDEPLOY-186] and [RDEPLOY-187], and its full reset by `set_model_list` in [RDEPLOY-002].
- [DATA-006] {confirmed} `litellm/router.py:11130-11176` The Router's writes into the process-global `litellm.model_cost` map are specified in [RDEPLOY-188].
- [DATA-007] {confirmed} `litellm/router.py:1302`, `litellm/router_utils/kubernetes_pod_discovery.py:86-109` The per-router `KubernetesPodDiscovery` instance is specified in [TARGETS-023], and its in-process pod cache in [TARGETS-158].
- [DATA-008] {confirmed} `litellm/router.py:1376-1397` The derived-value caches the constructor creates empty are specified in [RSETUP-018], their invalidation in [RSELECT-235], the class-level model-group-info LRU in [RDEPLOY-143], and the discovered-limits cache in [RDEPLOY-109].
- [DATA-009] {confirmed} `litellm/router.py:1346` The request `Scheduler`'s use of the Router's Redis client is specified in [RSETUP-015]; the queue itself lives outside the Router's files, and its key is [DATA-160].
- [DATA-160] {confirmed} `litellm/scheduler.py:20-24`, `litellm/scheduler.py:44-49`, `litellm/scheduler.py:145-169`, `litellm/caching/dual_cache.py:505-514`, `litellm/constants.py:569` The scheduler keeps each model group's priority queue under `scheduler:queue:<model group>` (for example `scheduler:queue:gpt-4o`) as a list of `(priority, request_id)` pairs, in its own two-tier cache over the Redis client the Router hands it ([RSETUP-015]). With Redis configured, every save writes both tiers with a TTL of `DEFAULT_IN_MEMORY_TTL` seconds (env, default `5`), because the scheduler's in-memory default TTL is also passed to the Redis write; without Redis the memory copy gets the memory tier's default of [DATA-016].
- [DATA-159] {confirmed} `litellm/router_utils/auto_router_tuning_baseline.py:13-14`, `litellm/router_utils/auto_router_tuning_baseline.py:113-122` The auto-router tuning-baseline database row, whose name and content the in-scope code defines and the proxy persists, is specified in [CONTRACTS-067] (row name), [CONTRACTS-079] (identity-to-fingerprint content), [CONTRACTS-073] (fingerprint encoding) and [CONTRACTS-139] (written once by the proxy at boot).
- [DATA-010] {inferred} `litellm/router.py:1296-1346`, `litellm/router_utils/kubernetes_pod_discovery.py:145-155` Across the in-scope files the Router opens no SQL connection, no file for writing and no socket of its own. Its only network dependencies for state are Redis, reached through the cache objects ([RSETUP-270]), and DNS lookups for pod discovery ([TARGETS-030]). This rests on a search of the in-scope files for database, file-open and socket APIs; the one `open(` in `router.py` sits in a docstring example.

### Redis connection

- [DATA-011] {confirmed} `litellm/router.py:1303-1326` The condition under which the Router builds a Redis client is specified in [RSETUP-006]; without one, every two-tier cache it creates stays memory-only until a later attach ([RSETUP-065], [FAILURE-008]).
- [DATA-012] {confirmed} `litellm/router.py:1306-1325` The Redis config keys, their conversions and the `cache_kwargs` override are specified in [RSETUP-007], and the `redis_db` deprecation warning in [RSETUP-008].
- [DATA-013] {confirmed} `litellm/router.py:1654-1669` The choice between a Redis Cluster client and a single-node Redis client is specified in [RSETUP-010].
- [DATA-014] {confirmed} `litellm/router.py:1671-1684`, `litellm/caching/dual_cache.py:119-136` Late attachment of a Redis client by `update_redis_cache`, which never replaces a client and never copies memory-only entries, is specified in [RSETUP-065] and [RSETUP-066].
- [DATA-015] {confirmed} `litellm/router.py:1328-1332` Creation of the process-global `litellm.cache` when `cache_responses` is set is specified in [RSETUP-012].

### Memory tier limits shared by the caches

- [DATA-016] {confirmed} `litellm/router.py:1333-1339`, `litellm/caching/in_memory_cache.py:28-56`, `litellm/caching/dual_cache.py:96-107`, `litellm/__init__.py:386-388` The memory tiers of the Router cache and of the session-router binding cache each hold at most `200` entries, because the Router creates them with no size ([RSETUP-014]) and `200` is the shared in-memory cache's default. A plain set written without a TTL expires after `litellm.default_in_memory_ttl` seconds when that process-global is set at the moment the cache is built, and after `600` seconds otherwise (default `None`, so `600`).
- [DATA-017] {inferred} `litellm/caching/in_memory_cache.py:110-160` When a memory tier is full, the entries with the earliest expiry are evicted first, whatever kind of key they hold. Usage counters, allowed-fails counters, affinity pins, the health snapshot and concurrency slots therefore compete for the Router cache's 200 slots, and the 60-second counters go first (inferred from the shared `InMemoryCache` eviction policy, which lives outside the Router).
- [DATA-018] {inferred} `litellm/caching/in_memory_cache.py:110-160`, `litellm/caching/in_memory_cache.py:162-192`, `litellm/caching/in_memory_cache.py:245-251` The memory tier's rule that a live entry keeps its first expiry, which normally makes every per-minute counter a fixed window from its first write, is specified in [LIMITS-143] and [FAILURE-073]; at the tier's 200-item cap, capacity eviction ([DATA-017]) can instead slide that window or drop a count early, as specified in [FAILURE-073] and, for the allowed-fails counter, [FAILURE-051].
- [DATA-019] {inferred} `litellm/router_utils/cooldown_cache.py:51-54`, `litellm/constants.py:152`, `litellm/caching/dual_cache.py:299-325`, `litellm/router.py:1333-1343` The cooldown store's Redis re-read interval is specified in [FAILURE-009]. The Router cache, the session-router cache and the prompt-cache pin cache are built without an interval ([RSETUP-014]), so their batch reads re-read a memory-missed key from Redis at most once per `litellm.default_redis_batch_cache_expiry` seconds as set when the cache is built, else once per `10` seconds.
- [DATA-020] {inferred} `litellm/caching/dual_cache.py:218-260`, `litellm/caching/dual_cache.py:349-383` On a batch read, a key that is present in the memory tier is served from memory and Redis is not consulted for it. Only memory misses go to Redis. So a live local copy hides newer Redis values until it expires.

## Schemas

The Router has no tables or migrations. Its schemas are cache key formats, cache value shapes,
in-memory record shapes and the fields it writes into request metadata. No key or value carries a
version number except the keys marked `v1` below, so a format change is a silent incompatibility
between processes that share a Redis.

### Key catalog

| ID | Key format (literal) | Store | Value | TTL | Specified in |
|---|---|---|---|---|---|
| [DATA-021] | `deployment:<id>:cooldown` | cooldown store | cooldown record | the cooldown time, in seconds | [FAILURE-001], [FAILURE-002], [FAILURE-006] |
| [DATA-026] | `deployment:<id>:allowed_fails`, or with `:<ExceptionClass>` or `:generic` appended | Router cache | integer fail count | the effective cooldown time | [FAILURE-049], [FAILURE-048] |
| [DATA-029] | `<id>:successes`, `<id>:fails` | Router cache, memory only | integer | 60 s | [FAILURE-072] |
| [DATA-031] | `global_router:<id>:<model>:tpm:<HH-MM>` and `...:rpm:<HH-MM>` | Router cache | integer | 60 s | [RDISP-182], [RDISP-183] |
| [DATA-036] | `global_router:<id>:<model>:itpm:<HH-MM>` and `...:otpm:<HH-MM>` | Router cache | integer (reserved tokens) | 60 s | [LIMITS-089], [LIMITS-080] |
| [DATA-041] | `<id>:<model>:tpm:<HH-MM>` and `<id>:<model>:rpm:<HH-MM>` | Router cache | integer | 60 s | [LIMITS-053], [LIMITS-067], [FAILURE-215] |
| [DATA-045] | `<id>` (bare deployment id) | Router cache, memory only | integer request count | 60 s from first write | [RDISP-208] |
| [DATA-046] | `<group>:rpm:<HH-MM>` | Router cache, read from memory only | map of deployment id to count | set by its writer, usage-based routing v1 (outside the Router) | [RSELECT-203], [RSELECT-232] |
| [DATA-047] | `<id>_max_parallel_requests_client` | Router cache, memory only | concurrency-slot object | memory default ([DATA-016]) | [TARGETS-079] |
| [DATA-050] | `litellm:health_check:deployment_health_state` | Router cache | map of deployment id to health record | `int(1.5 * staleness threshold)` s | [FAILURE-078], [FAILURE-081] |
| [DATA-055] | `deployment_affinity:v1:<group>:<hashed caller>` | Router cache | pin record | `deployment_affinity_ttl_seconds` (default 3600 s), sliding on a same-deployment claim | [AFFINITY-036], [AFFINITY-045], [AFFINITY-003], [AFFINITY-047] |
| [DATA-056] | `deployment_affinity:v1:session:<group>:<hashed caller or unscoped>:<session id>` | Router cache | pin record | marker TTL, else the affinity TTL | [AFFINITY-037], [AFFINITY-046] |
| [DATA-061] | `deployment:<sha256 hex>:prompt_caching` | prompt-cache pin cache | pin record | 300 s, or 3600 s for one-hour breakpoints | [AFFINITY-105], [AFFINITY-112], [AFFINITY-113] |
| [DATA-066] | `claude_code_session_router:v1:<user_api_key_hash>:<session id>` | session-router cache | model name string | 3600 s | [RSELECT-110], [RSELECT-231] |
| [DATA-095] | `upstream_model_info:<sha256 hex>` | Router cache, memory only | parsed `/v1/models` listing | 300 s, or 60 s after a failed fetch | [RDEPLOY-108] |
| [DATA-160] | `scheduler:queue:<model group>` | the scheduler's own two-tier cache over the Router's Redis client | list of `[priority, request_id]` pairs | `DEFAULT_IN_MEMORY_TTL` (default `5` s) in both tiers when Redis is configured | [RSETUP-015] |
| [DATA-151] | `<id>_client`, `<id>_stream_client`, `<id>_async_client`, `<id>_stream_async_client` | Router cache (read only; no writer found) | provider client | none written | [RSELECT-176], [RDEPLOY-151] |

### Cooldown record

- [DATA-021] {confirmed} `litellm/router_utils/cooldown_cache.py:133-136`, `litellm/router_utils/cooldown_cache.py:122-128` The cooldown key format is specified in [FAILURE-001], and its two-tier write with a TTL equal to the cooldown time in [FAILURE-006].
- [DATA-022] {confirmed} `litellm/router_utils/cooldown_cache.py:27-31`, `litellm/router_utils/cooldown_cache.py:78-93` The cooldown record (`CooldownCacheValue`) and its four fields `exception_received`, `status_code`, `timestamp` and `cooldown_time` are specified in [FAILURE-002].
- [DATA-023] {confirmed} `litellm/router_utils/cooldown_cache.py:55-61`, `litellm/litellm_core_utils/sensitive_data_masker.py:57-72` The masking of `exception_received` (first 50 characters kept, length preserved) is specified in [FAILURE-003].
- [DATA-024] {confirmed} `litellm/router_utils/cooldown_cache.py:98-120` The record's default cooldown time is specified in [FAILURE-005], and the fact that `update_settings(cooldown_time=...)` does not change that default in [RSELECT-282].
- [DATA-025] {confirmed} `litellm/router_utils/cooldown_cache.py:138-160` The wall-clock activeness test on read is specified in [FAILURE-012], and the rewrite of an over-long memory TTL in [FAILURE-013].
- [DATA-026] {confirmed} `litellm/router_utils/cooldown_handlers.py:706-717` The allowed-fails counter key and its suffixes are specified in [FAILURE-049], and its TTL in [FAILURE-048].
- [DATA-027] {confirmed} `litellm/router_utils/cooldown_handlers.py:720-731` The two-tier increment of the allowed-fails counter is specified in [FAILURE-049], and its fallback to this process's count on a Redis failure in [FAILURE-050].
- [DATA-028] {confirmed} `litellm/router_utils/cooldown_cache.py:213-231` `get_min_cooldown` (smallest stored `cooldown_time`, expiry not checked) is specified in [FAILURE-017].

### Per-minute success and failure counters

- [DATA-029] {confirmed} `litellm/router_utils/router_callbacks/track_deployment_metrics.py:45-75` The process-local success and failure counters (`<id>:successes`, `<id>:fails`, for example `dep-a:successes`) are specified in [FAILURE-072].
- [DATA-030] {confirmed} `litellm/router_utils/router_callbacks/track_deployment_metrics.py:78-113`, `litellm/router_utils/cooldown_handlers.py:450-490` The cooldown decision's memory-only read of these counters is specified in [FAILURE-045] and [FAILURE-074], and their fixed 60-second window in [FAILURE-073].

### Router usage counters (global namespace)

- [DATA-031] {confirmed} `litellm/types/router.py:1176-1180` The `global_router:` key templates, constants in the shared router types, are specified in [RDISP-182] for `tpm` and `rpm` and in [LIMITS-089] for `itpm` and `otpm`.
- [DATA-032] {confirmed} `litellm/router.py:9044-9102`, `litellm/router.py:997-998` The success-path increment of the global `tpm` and `rpm` counters is specified in [RDISP-182] and [RDISP-183], and the `60` s TTL constant in [RSETUP-250].
- [DATA-033] {confirmed} `litellm/router.py:9055-9081` The cases in which the success path writes no usage (no `tpm`, `rpm`, `itpm` or `otpm` limit, or nothing to add) are specified in [RDISP-181].
- [DATA-034] {confirmed} `litellm/router.py:9097-9101` The write-back of the fleet-wide totals Redis returns into the memory tier is specified in [RDISP-183].
- [DATA-035] {confirmed} `litellm/router.py:9266-9297` The failure-path `rpm` increment, made even when the deployment has no limit, is specified in [RDISP-197].

### Input and output token reservations

- [DATA-036] {confirmed} `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:118-127` The reservation counter keys, and the absence of a key when the id or model is missing, are specified in [LIMITS-089].
- [DATA-037] {confirmed} `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:367-417` The increment-then-compare reservation with its rollback on overshoot is specified in [LIMITS-097].
- [DATA-038] {confirmed} `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:333-343`, `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:444-471` The input reservation amount is specified in [LIMITS-092], the output reservation basis in [LIMITS-093], and the zero-output case in [LIMITS-095].
- [DATA-039] {confirmed} `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:45-48`, `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:258-279` The four reservation fields are named in [LIMITS-080], and where they are written in the request metadata in [LIMITS-100].
- [DATA-040] {confirmed} `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:553-664` Reconciliation on success is specified in [LIMITS-106] (resolved usage), [LIMITS-107] (unresolved usage) and [LIMITS-108] (field removal), and the billable input it uses in [LIMITS-105]; it runs only when the success kwargs carry the reservation fields where [LIMITS-066] looks, which the router's own success events never do, so on router calls the reservations stay until their counters expire ([LIMITS-190]).
- [DATA-102] {confirmed} `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:667-745` The refund on failure is specified in [LIMITS-109].
- [DATA-103] {confirmed} `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:51-65`, `litellm/router.py:4632-4636` The refund of a previous attempt's reservation at each deployment bind is specified in [LIMITS-083], and the stripping of caller-supplied reservation fields in [LIMITS-082] and [LIMITS-112].
- [DATA-153] {confirmed} `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:40-65` The context variable that holds the request kwargs, and its reset to `None` for deployments without `itpm`/`otpm` limits, are specified in [LIMITS-081], [LIMITS-082] and [LIMITS-176].

### Counters shared with the per-deployment rate-limit check and usage-based routing

- [DATA-041] {confirmed} `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:132-140`, `litellm/router_strategy/lowest_tpm_rpm_v2.py:459-470`, `litellm/router.py:2776-2777`, `litellm/router.py:1733-1737` The `enforce_model_rate_limits` check keys its counters `<id>:<model>:tpm:<HH-MM>` and `<id>:<model>:rpm:<HH-MM>` (for example `dep-a:gpt-4o:rpm:14-05`; [LIMITS-053], [LIMITS-067]), and usage-based routing v2 reads ([FAILURE-215]) and writes the same un-prefixed format. Both are built over the Router cache ([RSETUP-143], [RSETUP-072]), so when both are enabled they read and write the same counters.
- [DATA-042] {confirmed} `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:296-319` The increment-before-compare `rpm` check, which keeps a rejected request counted, is specified in [LIMITS-059].
- [DATA-043] {confirmed} `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:153-162` The `tpm` read path (memory first, then Redis, with the circuit-breaker fallback) is specified in [LIMITS-057].
- [DATA-154] {confirmed} `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:63-83` The ever-growing set of deployment ids already warned about is specified in [LIMITS-145] and [LIMITS-065].
- [DATA-044] {gap} `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:366-386`, `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:132-140` Can the rate-limit check write `tpm` under a key it never reads, because it writes under the logged `hidden_params.litellm_model_name` and reads under `litellm_params.model`? The open question is owned by [LIMITS-192] (suspected defect [LIMITS-198]).
- [DATA-045] {confirmed} `litellm/router.py:9359-9374`, `litellm/router.py:4288-4290`, `litellm/router.py:16133-16144` The memory-only request counter keyed by the bare deployment id is specified in [RDISP-208], and its increment at each async deployment pick in [RSELECT-148].
- [DATA-046] {confirmed} `litellm/router.py:13870-13913` The pre-call RPM filter's memory-only reads of the bare-id counter and the `<group>:rpm:<HH-MM>` map (for example `gpt-4o:rpm:14-05`) are specified in [RSELECT-203] and [RSELECT-232].

### Concurrency slots

- [DATA-047] {confirmed} `litellm/router_utils/client_initalization_utils.py:53-78` The concurrency-slot object, stored in memory only with no explicit TTL, is specified in [TARGETS-079], and its cap in [TARGETS-077] and [TARGETS-078].
- [DATA-048] {confirmed} `litellm/router.py:13603-13609`, `litellm/router_utils/client_initalization_utils.py:34-50` The lazy creation of a missing slot object is specified in [RSELECT-175], its `429` rejection at the cap in [TARGETS-072], and its release in [TARGETS-075].
- [DATA-049] {inferred} `litellm/router_utils/client_initalization_utils.py:73-78`, `litellm/caching/in_memory_cache.py:28-56` The slot object of [TARGETS-079] gets the memory tier's default TTL ([DATA-016], `600` s by default) and can be evicted with the 200-entry tier ([DATA-017]). A later request then builds a fresh object whose in-flight count is `0` ([RSELECT-175]) while earlier requests still hold slots on the old one, so the limit admits more requests than configured for a while. This answers the open question [TARGETS-181] from the shared cache layer's defaults, which live outside the Router.

### Health snapshot

- [DATA-050] {confirmed} `litellm/router_utils/health_state_cache.py:28-31`, `litellm/router_utils/health_state_cache.py:54` The single Router-cache entry that holds background health results, its key and its per-deployment value shape are specified in [FAILURE-078].
- [DATA-051] {confirmed} `litellm/router_utils/health_state_cache.py:60-88` The health write is specified in [FAILURE-079] (read source), [FAILURE-080] (merge and prune) and [FAILURE-081] (two-tier write with TTL `int(1.5 * threshold)` seconds).
- [DATA-052] {confirmed} `litellm/router_utils/health_state_cache.py:95-106` The unhealthy test (falsy `is_healthy`, younger than the staleness threshold) is specified in [FAILURE-083].
- [DATA-053] {confirmed} `litellm/router.py:1434-1437`, `litellm/constants.py:1945`, `litellm/constants.py:1952` The health-state staleness threshold (default `600` seconds) is specified in [RSETUP-030].
- [DATA-054] {inferred} `litellm/router_utils/health_state_cache.py:73-88`, `litellm/proxy/proxy_server.py:4759` The unlocked read-merge-write of the snapshot is specified in [FAILURE-197]. Its only caller in the repository is the proxy's background health check, so concurrent writers are proxy workers sharing one Redis (inferred from a search for callers of the health-state setters).

### Affinity pins

- [DATA-055] {confirmed} `litellm/router_utils/pre_call_checks/deployment_affinity_check.py:239-242` The caller pin key is specified in [AFFINITY-036], its claim with TTL `ttl_seconds` in [AFFINITY-045], the router's default TTL of `3600` s in [AFFINITY-003], and the sliding expiry on a same-deployment claim in [AFFINITY-047].
- [DATA-056] {confirmed} `litellm/router_utils/pre_call_checks/deployment_affinity_check.py:244-250` The session pin key is specified in [AFFINITY-037], and its claim and TTL in [AFFINITY-046].
- [DATA-057] {confirmed} `litellm/router_utils/pre_call_checks/deployment_affinity_check.py:116-143` The hashing of caller keys before they enter a pin key is specified in [AFFINITY-035].
- [DATA-058] {confirmed} `litellm/router_utils/pre_call_checks/deployment_affinity_check.py:279-298` The caller key (`user_api_key_hash`, else `user_id:<user_api_key_user_id>`, for example `user_id:alice`) is specified in [AFFINITY-034].
- [DATA-059] {inferred} `litellm/caching/affinity_cache.py:19-50`, `litellm/caching/affinity_cache.py:90-119` The first-writer-wins pin claim is specified in [AFFINITY-047], and its atomic Redis script in [AFFINITY-048].
- [DATA-060] {confirmed} `litellm/router_utils/pre_call_checks/deployment_affinity_check.py:418-427`, `litellm/router_utils/pre_call_checks/deployment_affinity_check.py:454-462` The two readable pin shapes (a `{"model_id": ...}` record or a legacy bare string id) are specified in [AFFINITY-161].

### Prompt-cache pins

- [DATA-061] {confirmed} `litellm/router_utils/prompt_caching_cache.py:98-111` The prompt-cache pin key format, one key per content unit of the cacheable prefix, is specified in [AFFINITY-105].
- [DATA-062] {confirmed} `litellm/router_utils/prompt_caching_cache.py:58-95` The SHA-256 chain behind each key is specified in [AFFINITY-106] and [AFFINITY-107].
- [DATA-063] {confirmed} `litellm/router_utils/prompt_caching_cache.py:330-352`, `litellm/router_utils/pre_call_checks/prompt_caching_deployment_check.py:186-198` The write of only the breakpoint block's key with value `{"model_id": <id>}` (for example `{"model_id": "dep-a"}`) is specified in [AFFINITY-113], and the success callback's tool-free keying in [AFFINITY-091].
- [DATA-064] {confirmed} `litellm/router_utils/prompt_caching_cache.py:39-40`, `litellm/router_utils/prompt_caching_cache.py:121-127`, `litellm/router_utils/prompt_caching_cache.py:282-300` The pin lifetime (`300` s, or `3600` s for a one-hour breakpoint on a deployment that honors one-hour TTLs) is specified in [AFFINITY-112] and [AFFINITY-113].
- [DATA-065] {confirmed} `litellm/router_utils/prompt_caching_cache.py:114-118`, `litellm/router_utils/prompt_caching_cache.py:354-370`, `litellm/constants.py:504` The lookback of `PROMPT_CACHE_LOOKBACK_POSITIONS` (`20`) positions is specified in [AFFINITY-110], and the newest-first read in [AFFINITY-111].
- [DATA-152] {confirmed} `litellm/router_utils/prompt_caching_cache.py:346-352`, `litellm/router_utils/prompt_caching_cache.py:321-328` The delete-then-set pin write that restarts the TTL is specified in [AFFINITY-113] and [AFFINITY-114].

### Session-router bindings

- [DATA-066] {confirmed} `litellm/router.py:15153-15164`, `litellm/router.py:522-523` The binding key and the conditions for building it are specified in [RSELECT-110], the stored value and its `3600` s TTL in [RSELECT-231], and the constants in [RSETUP-252].
- [DATA-067] {confirmed} `litellm/router.py:15177-15190` The binding read, straight from Redis when Redis is attached and treated as no binding on failure, is specified in [RSELECT-117].
- [DATA-068] {confirmed} `litellm/router.py:15209-15224` The sub-agent path (read, rewrite with a fresh TTL, or delete) is specified in [RSELECT-113], [RSELECT-114] and [RSELECT-115].
- [DATA-069] {confirmed} `litellm/router.py:15196-15233` When a main-agent request writes the binding, and when no binding traffic happens, is specified in [RSELECT-112] and [RSELECT-116].

### Deployment ids carried in client-visible identifiers

- [DATA-155] {confirmed} `litellm/router_utils/pre_call_checks/encrypted_content_affinity_check.py:10-18`, `litellm/responses/utils.py:393-397`, `litellm/responses/utils.py:434-438` Encrypted-content affinity keeps no server-side state ([AFFINITY-164]); the Router only decodes ([AFFINITY-058]) ids that the Responses layer encodes outside the scope as either an item id `encitem_<base64>` whose payload renders as `litellm:model_id:<id>;item_id:<original id>` (for example `litellm:model_id:dep-a;item_id:rs_1`), or wrapped content `litellm_enc:<base64>;<original encrypted content>` whose base64 payload renders as `model_id:<id>`.
- [DATA-156] {confirmed} `litellm/router_utils/pre_call_checks/responses_api_deployment_check.py:41-55`, `litellm/responses/utils.py:623-634`, `litellm/types/utils.py:4699` Responses API affinity decodes ([AFFINITY-122]) a `previous_response_id` that the Responses layer issues as `resp_<base64>` whose payload renders as `litellm:custom_llm_provider:<provider>;model_id:<id>;response_id:<upstream id>` (for example `litellm:custom_llm_provider:openai;model_id:dep-a;response_id:resp_x`). Changing that format would break affinity for responses issued before the change.

### Deployment registry records

- [DATA-070] {confirmed} `litellm/router.py:10923-10968`, `litellm/router.py:10070-10075` The registry entry shape (a plain dict with `None` fields omitted) is specified in [RDEPLOY-186], its append in [RDEPLOY-023], and the three position indexes in [RDEPLOY-187].
- [DATA-071] {confirmed} `litellm/router.py:10923-10939` The team index and `team_public_model_names` entries, made only when both `team_id` and `team_public_model_name` are set, are specified in [RDEPLOY-057].
- [DATA-072] {confirmed} `litellm/router.py:10713-10728` The storage of wildcard deployments in the proxy-wide or per-team pattern registry is specified in [RDEPLOY-026].
- [DATA-073] {confirmed} `litellm/router_utils/pattern_match_deployments.py:75-90`, `litellm/router_utils/pattern_match_deployments.py:28-58` The pattern registry's regex form is specified in [TARGETS-006], its specificity order in [TARGETS-003] and [TARGETS-020], and its stable ties in [TARGETS-004].
- [DATA-074] {confirmed} `litellm/router.py:10596-10600`, `litellm/types/router.py:481-484` The resolution of `os.environ/` values before a config deployment is stored, which leaves resolved credentials in the registry, is specified in [RDEPLOY-006].
- [DATA-075] {confirmed} `litellm/router.py:11292-11309` `get_deployment`'s fresh `Deployment` object on every call is specified in [RDEPLOY-095].
- [DATA-076] {confirmed} `litellm/router.py:10552-10569`, `litellm/router.py:10635` What `set_model_list` resets is specified in [RDEPLOY-002], and its `model_names` that keep skipped rows in [RDEPLOY-010].
- [DATA-077] {confirmed} `litellm/router.py:10552-10569` What `set_model_list` does not reset (the proxy-wide wildcard registry, `provider_default_deployment_ids`, `deployment_names`, the adaptive routers) and the consequences of a second call are specified in [RDEPLOY-003].

### Deployment identity

- [DATA-078] {confirmed} `litellm/router.py:9771-9800` The generated deployment id (SHA-256 of the model name and the `litellm_params` keys and values in insertion order) is specified in [RDISP-240] and [RDISP-241].
- [DATA-079] {confirmed} `litellm/router.py:9762-9768` The restart-stable rendering of non-JSON values inside dict params is specified in [RDISP-243].
- [DATA-080] {confirmed} `litellm/router.py:10596-10609` The id's dependence on the env-expanded `litellm_params` is specified in [RDEPLOY-007], and on their key order in [RDISP-241].
- [DATA-081] {confirmed} `litellm/router.py:10606-10630` The single shared id of deployments expanded from an `organization` list is specified in [RDEPLOY-009].
- [DATA-082] {confirmed} `litellm/router.py:4516-4549` The per-request deployment built for caller-supplied credentials, with its own generated id and `model_info.original_model_id`, is specified in [RCALL-065], and its cost-map-only footprint in [RCALL-163].

### Process-global cost map entries

- [DATA-083] {confirmed} `litellm/router.py:11154-11176`, `litellm/router.py:11070-11075` The entry registered under the deployment id is specified in [RDEPLOY-080], and the filtered shared entries under backend model keys in [RDEPLOY-081].
- [DATA-084] {confirmed} `litellm/router.py:11151-11152` The removal of custom pricing for strategy-router pseudo-models is specified in [RDEPLOY-082].
- [DATA-085] {confirmed} `litellm/router.py:10042-10057` The cost-map registration that happens before the environment gate, so environment-inactive rows still leave entries, is specified in [RDEPLOY-020].
- [DATA-086] {confirmed} `litellm/router.py:11206-11243` `delete_deployment` leaving cost-map entries in place is specified in [RDEPLOY-056].
- [DATA-087] {confirmed} `litellm/router.py:1001-1014`, `litellm/router.py:11178-11203` Membership in the process-wide live-router set is specified in [RSETUP-023] and [RSETUP-255], and the replay each live router runs after a price reload in [RDEPLOY-085].
- [DATA-088] {confirmed} `litellm/router.py:1630-1652` `discard()` leaving the live-router set and the global callback lists is specified in [RSETUP-062].

### Derived-value caches

- [DATA-089] {confirmed} `litellm/router.py:12409-12416` The class-level model-group-info LRU (`DEFAULT_MAX_LRU_CACHE_SIZE`, default `64`, shared and cleared across all routers) is specified in [RDEPLOY-143].
- [DATA-090] {inferred} `litellm/router.py:12409-12416`, `litellm/router.py:1001-1005`, `litellm/router.py:1529-1547`, `litellm/router.py:1630-1644` A router that has not called `discard()` never drops out of the live-router set on its own ([RSETUP-255]), because its bound-method callbacks on the process-global callback lists keep it referenced until `discard()` removes them ([RSETUP-062]). After `discard()` it no longer takes part in price replays, but when its group info was cached the class-level LRU still holds a strong reference to it ([RDEPLOY-143]), so it stays in memory until those entries are evicted or the LRU is cleared. This is inferred from standard weak-set and LRU-cache semantics.
- [DATA-091] {confirmed} `litellm/router.py:13376-13397`, `litellm/router.py:10941-10948` What a registry change clears is specified in [RSELECT-007], and that every registry change triggers it in [RDEPLOY-143].
- [DATA-092] {confirmed} `litellm/router.py:13413-13443` `get_model_access_groups` caching only its no-argument call is specified in [RSELECT-008].
- [DATA-093] {confirmed} `litellm/router.py:1392-1395`, `litellm/router.py:11391-11438` The discovered-limits cache, its size, TTL and discard rules are specified in [RDEPLOY-109].
- [DATA-094] {confirmed} `litellm/router.py:11440-11449` A discovered limit served only for the stored row it was probed from, and only for unset fields, is specified in [RDEPLOY-110].
- [DATA-095] {confirmed} `litellm/llms/openai_like/model_info.py:69-92`, `litellm/router.py:11428` The cached upstream `/v1/models` listing, its hashed key and its `300` s / `60` s lifetimes are specified in [RDEPLOY-108].

### Kubernetes pod address cache

- [DATA-096] {confirmed} `litellm/router_utils/kubernetes_pod_discovery.py:66-71`, `litellm/router_utils/kubernetes_pod_discovery.py:405-418` The pod cache entry (pod IPs, resolve and last-use times, round-robin cursor) keyed by `(host, port)` is specified in [TARGETS-158], its sorted IP set in [TARGETS-031], and its update on a successful lookup in [TARGETS-032].
- [DATA-097] {confirmed} `litellm/router_utils/kubernetes_pod_discovery.py:111-127`, `litellm/router_utils/kubernetes_pod_discovery.py:129-197`, `litellm/constants.py:43-49` The refresh and idle-eviction defaults are specified in [TARGETS-022], and the reuse, refresh and eviction rules in [TARGETS-028] and [TARGETS-161].
- [DATA-098] {confirmed} `litellm/router_utils/kubernetes_pod_discovery.py:361-385`, `litellm/router_utils/kubernetes_pod_discovery.py:421-429` A failed refresh keeping the previous IPs is specified in [TARGETS-034], and the empty IP set stored for "no such name" or "no data" in [TARGETS-033].

### Batch input file format (JSONL rewrite)

- [DATA-099] {confirmed} `litellm/router_utils/batch_utils.py:68-78`, `litellm/router.py:6941-6957` When a routed batch file upload is rewritten is specified in [RDISP-063], and the per-row `body.model` replacement in [TARGETS-128].
- [DATA-100] {confirmed} `litellm/router_utils/batch_utils.py:118-144` The re-serialization of rewritten rows is specified in [TARGETS-129], and the returned in-memory `modified_file.jsonl` file in [TARGETS-131].
- [DATA-101] {confirmed} `litellm/router_utils/batch_utils.py:121-130`, `litellm/router_utils/batch_utils.py:137-142`, `litellm/router.py:6953-6957` Byte-order-mark removal is specified in [TARGETS-126], multi-line row accumulation in [TARGETS-127], and the row layout (back to back, or line-preserving for `vertex_ai`) in [TARGETS-130] and [RDISP-063].
- [DATA-104] {confirmed} `litellm/router_utils/batch_utils.py:82-103`, `litellm/router_utils/batch_utils.py:146-168` The cases that return the original content unchanged are specified in [TARGETS-124], [TARGETS-132], [TARGETS-133] and [TARGETS-134].
- [DATA-105] {inferred} `litellm/router_utils/batch_utils.py:166-168` The handle left unrewound after a decode or type error is specified in [TARGETS-134].

### Bookkeeping written into request metadata

These fields are written into the request's `metadata` or `litellm_metadata` dict, in place. The proxy and
the logging layer read them after the call, so their names and shapes are a data contract.

- [DATA-106] {confirmed} `litellm/router_utils/batch_utils.py:171-191` The choice between `litellm_metadata` and `metadata` by the internal function name is specified in [TARGETS-136].
- [DATA-107] {confirmed} `litellm/router.py:4612-4631` The deployment fields written at bind time are specified in [RCALL-068], and the pod-routing mirror into the other bucket in [RCALL-070].
- [DATA-108] {confirmed} `litellm/router.py:9313-9357`, `litellm/router.py:1017` The retry breadcrumbs are specified in [RDISP-200] (bucket choice), [RDISP-201] (record), [RDISP-202] (`previous_models`, at most `4` records) and [RDISP-203] (`request_retry_count`).
- [DATA-109] {confirmed} `litellm/router.py:9008-9042`, `litellm/constants.py:1644` The `_litellm_router_usage_counted_tokens` field is specified in [RDISP-178] (write), [RDISP-179] (removal on failure) and [FAILURE-077] (read).

### Per-router counters and lists in memory

- [DATA-110] {confirmed} `litellm/router.py:1485-1487`, `litellm/router.py:4372`, `litellm/router.py:4409` The per-router `total_calls`, `success_calls` and `fail_calls` counters and their inconsistent keys are specified in [RCALL-160] and [RDISP-260].
- [DATA-111] {confirmed} `litellm/router.py:1499`, `litellm/router.py:16138-16143` `deployment_stats` is created empty ([RSETUP-044]) and no line of `router.py` ever writes it, so it stays an empty dict for the router's lifetime.
- [DATA-112] {confirmed} `litellm/router.py:1295`, `litellm/router.py:1411-1413` `deployment_latency_map` is filled once at construction ([RSETUP-024]) and no other line of the repository writes the Router's copy, so every value stays `0`.
- [DATA-113] {confirmed} `litellm/router.py:10692-10693`, `litellm/router.py:10853-10921`, `litellm/router.py:10552-10569` `deployment_names` never shrinks: every registration that passes provider validation appends the deployment's provider model string, including registrations that fail later ([RDEPLOY-034]); the list survives `set_model_list` ([RDEPLOY-003]) and deletion does not touch it ([RDEPLOY-056]), so it keeps duplicates and deleted deployments.
- [DATA-114] {confirmed} `litellm/router_utils/search_api_router.py:54-87` The wholesale replacement of `search_tools` on each sync and its record shape are specified in [TARGETS-139].
- [DATA-115] {confirmed} `litellm/router.py:2054-2064`, `litellm/router.py:1821-1830` The cached per-request override selectors and their lifetime are specified in [RSETUP-102] and [RSETUP-271].

### Batched routing reads

- [DATA-116] {confirmed} `litellm/router_utils/routing_read_batch.py:187-223` The one multi-key read of cooldown and usage keys during selection is specified in [FAILURE-090], and the kept usage values in [FAILURE-092].
- [DATA-117] {confirmed} `litellm/router_utils/routing_read_batch.py:136-152` The single-use prefetch that must cover every needed key is specified in [FAILURE-096].
- [DATA-118] {confirmed} `litellm/router_utils/routing_read_batch.py:73-93`, `litellm/router_utils/routing_read_batch.py:46-60` The rollback of read reservations and the memory backfill after a prefetch are specified in [FAILURE-095].

### Lifecycle operations that erase state

- [DATA-119] {confirmed} `litellm/router.py:16263-16278`, `litellm/caching/redis_cache.py:1902-1903` `Router.flush_cache()`, which runs `FLUSHALL` on the whole Redis server when Redis is attached, is specified in [RSELECT-183] (suspected defect [RSELECT-274]).
- [DATA-120] {confirmed} `litellm/router.py:16263-16278` The stores `flush_cache()` empties are listed in [RSELECT-183]; the cooldown store's memory tier, the pod cache and the derived-value caches are not among them.
- [DATA-121] {confirmed} `litellm/router.py:16271-16278` `Router.reset()` is specified in [RSELECT-184].
- [DATA-122] {inferred} `litellm/router.py:16263-16278` No code under `litellm/` outside `router.py` calls `Router.flush_cache` ([RSELECT-183]) or `Router.reset` ([RSELECT-184]); only tests do (inferred from a search of `litellm/`).

### Registry changes

- [DATA-123] {confirmed} `litellm/router.py:10820-10851` `add_deployment`'s no-op condition and its registration steps are specified in [RDEPLOY-040] and [RDEPLOY-041].
- [DATA-124] {confirmed} `litellm/router.py:10970-10991` `upsert_deployment`'s no-change case is specified in [RDEPLOY-046].
- [DATA-125] {confirmed} `litellm/router.py:10992-11030` The remove-and-re-add upsert is specified in [RDEPLOY-047], and its move of the row to the last position in [RDEPLOY-197].
- [DATA-126] {confirmed} `litellm/router.py:11031-11067` The restore after a failed upsert under `ignore_invalid_deployments` is specified in [RDEPLOY-049] and [RDEPLOY-050].
- [DATA-127] {confirmed} `litellm/router.py:11206-11243` `delete_deployment`'s results for an unknown id and on a swallowed exception are specified in [RDEPLOY-053] and [RDEPLOY-055].
- [DATA-128] {confirmed} `litellm/router.py:10853-10921` The index repair on removal is specified in [RDEPLOY-058].
- [DATA-129] {inferred} `litellm/router.py:10853-10921`, `litellm/router.py:11206-11243` Removing or replacing a deployment touches only the registry structures listed in [RDEPLOY-058] and [RDEPLOY-053]. Its cooldown record, allowed-fails and usage counters, affinity and prompt-cache pins and health entry stay in memory and Redis until their TTLs expire; the affinity filters ignore a pin naming a removed id ([AFFINITY-162]), and the other filters only match ids among the current candidates (inferred from the absence of any delete of those keys in the removal paths).
- [DATA-130] {confirmed} `litellm/router.py:10571-10576`, `litellm/router.py:10941-10968` The acceptance of duplicate `model_info.id` values, with the id index pointing at the later row, is specified in [RDEPLOY-004] and [RDEPLOY-180].

### Stored deployment configuration read by SQL

- [DATA-157] {confirmed} `litellm/router_utils/auto_router_model_naming.py:234-309` The PostgreSQL JSONB predicate templates over the stored `complexity_router_config` are specified in [CONTRACTS-051], [CONTRACTS-064], [CONTRACTS-065] and [CONTRACTS-066]. The class docstring says each template answers the same question as its in-process check; rows holding both classifier keys, where the two answers disagree, are the open question [CONTRACTS-150].
- [DATA-158] {confirmed} `litellm/proxy/management_endpoints/model_management_endpoints.py:461-476` The proxy fills `{config}` with the `complexity_router_config` member of `litellm_params` in the `"LiteLLM_ProxyModelTable"` table, decoding rows where `litellm_params` was stored as a JSON string. The Router's templates therefore fix the stored JSON field names: renaming one in the config schema without migrating stored rows makes the database count disagree with the in-process check.

## Invariants

### Where each piece of state lives

| ID | State | Shared across processes on one Redis | Survives a process restart | Specified in |
|---|---|---|---|---|
| [DATA-131] | Cooldown records, allowed-fails counters, global usage counters, I/O token reservations, rate-limit counters, health snapshot, affinity pins, prompt-cache pins, session bindings | yes, when Redis is configured | yes, until each key's TTL | [FAILURE-187], [RDISP-183], [LIMITS-142], [AFFINITY-048], [AFFINITY-113], [RSELECT-231] |
| [DATA-132] | Per-minute success and failure counters, bare-id request counters, concurrency slots, upstream `/v1/models` cache | no | no | [FAILURE-187], [RDISP-262], [TARGETS-079], [RDEPLOY-108] |
| [DATA-133] | Deployment registry, indexes, pattern registries, derived-value caches, pod cache, call counters, override selectors, `search_tools` | no | no (rebuilt from config and proxy pushes) | [RDEPLOY-186], [TARGETS-158], [TARGETS-163], [RSETUP-271] |

- [DATA-131] {confirmed} `litellm/router_utils/cooldown_cache.py:122-128`, `litellm/router_utils/cooldown_handlers.py:720-731`, `litellm/router.py:9093-9096`, `litellm/router_utils/health_state_cache.py:84-88`, `litellm/router_utils/prompt_caching_cache.py:347-352`, `litellm/router.py:15228-15232` These entries are written through the two-tier caches without the local-only flag ([FAILURE-187], [RDISP-183], [LIMITS-142], [AFFINITY-048], [AFFINITY-113], [RSELECT-231]), so with Redis configured every process sharing that Redis reads and writes the same keys.
- [DATA-132] {confirmed} `litellm/router_utils/router_callbacks/track_deployment_metrics.py:52-58`, `litellm/router.py:9368-9374`, `litellm/router_utils/client_initalization_utils.py:74-78`, `litellm/router.py:11428` These entries are written local-only or straight into a memory tier ([FAILURE-072], [RDISP-208], [TARGETS-079], [RDEPLOY-108]), so every process keeps its own copy and the limits built on them (the failure-rate cooldown, the pre-call RPM filter, `max_parallel_requests`) apply per process, not fleet-wide ([FAILURE-045], [RSELECT-232]).
- [DATA-133] {confirmed} `litellm/router.py:10552-10642`, `litellm/router_utils/kubernetes_pod_discovery.py:104-109`, `litellm/router_utils/search_api_router.py:80-81` The registry ([RDEPLOY-186]) and the other per-router structures ([TARGETS-158], [TARGETS-163]) exist only in the router object and are lost when the process ends.
- [DATA-134] {inferred} `litellm/router.py:1303-1346` With no Redis configured ([RSETUP-006]), every store above is memory-only, so cooldowns, usage limits and pins apply per process and several proxy workers each enforce them separately ([RSETUP-269], [LIMITS-147], [FAILURE-207]). No code path warns about it (inferred from the cache wiring).

### Consistency and atomicity

- [DATA-135] {inferred} `litellm/caching/dual_cache.py:150-183`, `litellm/caching/dual_cache.py:644-673` Every two-tier write updates memory first and Redis second, with no transaction across keys or tiers. A Redis failure leaves the memory tier updated and Redis not, and the two tiers can then disagree until the memory entry expires.
- [DATA-136] {confirmed} `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:367-417`, `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:296-319` The increment-then-compare admission of the RPM and I/O token checks is specified in [LIMITS-170] and [LIMITS-171]; the I/O reservation's rollback on overshoot is in [LIMITS-097], and the RPM check's absence of one in [LIMITS-059].
- [DATA-137] {inferred} `litellm/router_utils/health_state_cache.py:73-88` Among the Router's shared-cache writes indexed in this file, the health snapshot ([FAILURE-197]) is the only entry updated by read-modify-write of a whole map; every other write is an increment, a single-key set or an atomic claim. This rests on the write sites listed in the key catalog.
- [DATA-138] {confirmed} `litellm/router.py:10930-10968`, `litellm/router.py:10853-10921` The registry index invariant kept on every add and remove is specified in [RDEPLOY-187], with the duplicate-id exceptions in [RDEPLOY-009] and [RDEPLOY-180].
- [DATA-139] {inferred} `litellm/router.py:10552-10642`, `litellm/router.py:10970-11039` The lock-free registry mutations and what another thread can observe during them are specified in [RDEPLOY-195].

### Time, keys and expiry

- [DATA-140] {confirmed} `litellm/router.py:9082`, `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:268-270`, `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:498-500` The UTC `%H-%M` minute in every per-minute key, independent of the host time zone, is specified in [RDISP-266], [LIMITS-141] and [RSELECT-233].
- [DATA-141] {inferred} `litellm/router.py:997-998`, `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:38` The daily reuse of a minute-bucket key name, safe only because the 60-second TTL has expired it, is specified in [LIMITS-141] and [RDISP-266].
- [DATA-142] {confirmed} `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:621-647` Reconciliation against the minute the reservation was made in is specified in [LIMITS-106].
- [DATA-143] {confirmed} `litellm/router_utils/cooldown_cache.py:82`, `litellm/router_utils/health_state_cache.py:78`, `litellm/router_utils/kubernetes_pod_discovery.py:92` The wall-clock cooldown and health timestamps are specified in [FAILURE-002] and [FAILURE-188], and the pod cache's monotonic clock in [TARGETS-167].
- [DATA-144] {inferred} `litellm/router_utils/cooldown_cache.py:138-160`, `litellm/router_utils/health_state_cache.py:95-106` The effect of clock skew between processes on cooldown and health expiry is specified in [FAILURE-188].
- [DATA-145] {inferred} `litellm/router_utils/cooldown_cache.py:122-128`, `litellm/router.py:9089-9096`, `litellm/router_utils/health_state_cache.py:84-88`, `litellm/router_utils/prompt_caching_cache.py:347-352`, `litellm/router.py:15218-15232`, `litellm/caching/redis_cache.py:867-930` Every in-scope write to Redis passes a TTL: cooldown records ([FAILURE-006]), allowed-fails counters ([FAILURE-048]), global and I/O counters ([RDISP-182], [LIMITS-080]), rate-limit counters ([LIMITS-053]), the health snapshot ([FAILURE-081]), pins ([AFFINITY-045], [AFFINITY-113]) and session bindings ([RSELECT-231]). So no Router key outlives its purpose without a writer. TTLs reach Redis truncated to whole seconds: a TTL below 1 second, including `0`, deletes an allowed-fails counter right after its increment ([FAILURE-051], [FAILURE-200]) and makes Redis reject a cooldown record, which then stays in this process only ([FAILURE-006]). This rests on the write sites surveyed here.

### Secrets in state

- [DATA-146] {confirmed} `litellm/router_utils/pre_call_checks/deployment_affinity_check.py:131-143`, `litellm/router.py:15153-15164`, `litellm/llms/openai_like/model_info.py:69-71` No key in the catalog above contains a raw API key: affinity keys hash the caller key ([AFFINITY-035]), session bindings use the proxy's key hash verbatim ([RSELECT-110]), and the upstream model-list key hashes its headers ([RDEPLOY-108]).
- [DATA-147] {inferred} `litellm/router_utils/cooldown_cache.py:86-91`, `litellm/router_utils/cooldown_cache.py:55-61` The storage in Redis of the unmasked first 50 characters of the exception text, including any credential fragment there, is specified in [FAILURE-204] (suspected defect [FAILURE-210]).
- [DATA-148] {confirmed} `litellm/router.py:10596-10600`, `litellm/router.py:11311-11324` The plain resolved credentials held in the registry are specified in [RDEPLOY-006], and their return by `get_deployment_credentials` (except for blocked deployments) in [RDEPLOY-097].

### Open questions

- [DATA-149] {gap} `litellm/router.py:9104-9139`, `litellm/router.py:8957-8990` Both the sync success callback ([RDISP-187]) and the async success callback ([RDISP-172]) increment `<id>:successes` (for example `dep-a:successes`). Can one call fire both callbacks, double-counting successes in the failure-rate cooldown?
- [DATA-150] {gap} `litellm/router.py:9266-9297`, `litellm/router.py:9055-9081` Failed calls add `1` to the global `rpm` counter for every deployment ([RDISP-197]), but successful calls add to it only when the deployment configures a limit ([RDISP-181]). Is the asymmetry intended, given that the usage headers read the same counter?
- [DATA-151] {gap} `litellm/router.py:13589-13640`, `litellm/router.py:1142` Nothing in the repository writes the `<id>_client`, `<id>_stream_client`, `<id>_async_client` or `<id>_stream_async_client` keys (for example `dep-0_async_client`) that `_get_client` reads ([RSELECT-176]), since per-deployment client initialization is commented out ([RDEPLOY-151]), and `client_ttl` (default `3600`) is stored but never read. Are these reads dead, so provider clients are never reused through the Router cache (suspected defect [RSELECT-280])?
