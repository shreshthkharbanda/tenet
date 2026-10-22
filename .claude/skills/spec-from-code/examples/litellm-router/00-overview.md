---
kind: overview
prefix: SYS
commit: 93b79d2587d186fb7266556a34a22d03f187a3da
status: draft
---
# LiteLLM Router: overview

## Purpose
The Router is the load-balancing and reliability layer of the LiteLLM SDK. A caller (an SDK user, or the
LiteLLM proxy, which builds one `litellm.Router` from its `router_settings` and sends all its LLM traffic
through it) asks for a *model group*, a public `model_name` that several *deployments* share. For each
call the Router picks one healthy, eligible deployment, binds that deployment's credentials, client and
timeouts into the call, invokes the matching `litellm.*` SDK function, retries within the group, falls
back to other groups, and cools down deployments that keep failing. The specification covers
`litellm/router.py` and `litellm/router_utils/**`; the strategy selectors, caches, scheduler, provider SDK
and proxy are context only.

The ten modules and what each decides:
- **router-setup** (RSETUP): how a Router is built from its settings, which strategy selector serves each model, which pre-call checks and endpoint attributes exist, and the `completion`/`acompletion` entry points.
- **router-calls** (RCALL): what one routed attempt sends and records, and how a stream that breaks after it opened is retried, sent to a fallback or continued.
- **router-dispatch** (RDISP): the endpoint factory, the retry loop, the cross-group fallback dispatcher, and the success and failure callbacks that count usage and trigger cooldowns.
- **router-deployments** (RDEPLOY): the deployment registry (load, add, upsert, delete, ids, prices, strategy-router registration) and every per-group metadata query.
- **router-selection** (RSELECT): which deployment serves a request (resolution, the filter pipeline, the pre-routing hook, the strategy pick) and the runtime settings API.
- **failure-handling** (FAILURE): whether and for how long a failed deployment cools down, retry-policy counts, fallback-chain lookup and walking, retry/fallback headers and the no-deployment error.
- **deployment-limits** (LIMITS): per-deployment TPM/RPM checks, input/output-token reservations, PTU shares and reserved access windows.
- **affinity-checks** (AFFINITY): optional filters that keep a caller, session, encrypted item or prompt-cache prefix on the deployment that holds its state, and mid-stream continuation targets.
- **routing-contracts** (CONTRACTS): pure contracts shared with the proxy: routing-group parsing, strategy validation, auto-router naming and licensing gates, baseline requests and reasoning-effort capability.
- **request-targets** (TARGETS): helpers that turn a chosen deployment into one concrete target: wildcard patterns, Kubernetes pod IPs, client-side credentials, concurrency caps, team filters, batch JSONL rewriting and search-tool routing.

## System map
| Module | Prefix | Responsibility | Depends on | Entry points |
|---|---|---|---|---|
| router-setup | RSETUP | Construction, strategy selectors, routing groups, endpoint wiring, chat entry points (`router.py:1-3315`) | all other modules | `Router(...)`, `completion`, `acompletion`, `routing_strategy_init`, `add_optional_pre_call_checks`, `update_redis_cache`, `discard` |
| router-calls | RCALL | Per-attempt execution, deployment binding, stream recovery, non-chat wrappers (`router.py:3316-6605`) | router-selection, router-dispatch, failure-handling, affinity-checks, request-targets | `_acompletion`, `aimage_generation`, `atranscription`, `aspeech`, `arerank`, `atext_completion`, `abatch_completion*`, `schedule_acompletion`, `aguardrail` |
| router-dispatch | RDISP | Endpoint factory, retry loop, fallback dispatcher, usage and failure callbacks, files and batches (`router.py:6606-9865`) | router-calls, router-selection, failure-handling, deployment-limits, request-targets | `factory_function`, `async_function_with_fallbacks`, `async_function_with_retries`, `function_with_fallbacks`, `aembedding`, `acreate_file`, `acreate_batch`, `aretrieve_batch` |
| router-deployments | RDEPLOY | Deployment registry, prices, strategy-router registries, group info and usage (`router.py:9866-13216`) | routing-contracts, request-targets, deployment-limits, failure-handling | `set_model_list`, `add_deployment`, `upsert_deployment`, `delete_deployment`, `get_deployment`, `get_model_group_info` |
| router-selection | RSELECT | Resolution, filter pipeline, pre-routing hook, strategy pick, settings API (`router.py:13217-16278`) | failure-handling, deployment-limits, affinity-checks, routing-contracts, request-targets, router-deployments | `async_get_available_deployment`, `get_available_deployment`, `async_get_healthy_deployments`, `get_model_list`, `get_settings`, `update_settings` |
| failure-handling | FAILURE | Cooldowns, health state, retry policy, fallback walk, headers, alerts (11 files in `router_utils/`) | request-targets | `set_cooldown_deployments`, `CooldownCache`, `run_async_fallback`, `get_fallback_model_group`, `get_num_retries_from_retry_policy` |
| deployment-limits | LIMITS | TPM/RPM, I/O-token reservations, PTU shares, access windows (4 files) | failure-handling | `ModelRateLimitingCheck`, `async_io_token_pre_call_check`, `filter_ptu_shared_deployments`, `team_ptu_ceiling`, `filter_reserved_deployments` |
| affinity-checks | AFFINITY | Affinity and continuation filters, prompt-cache pin store (6 files) | none in scope | `DeploymentAffinityCheck`, `EncryptedContentAffinityCheck`, `PromptCachingDeploymentCheck`, `ContinuationPrefillDeploymentCheck`, `PromptCachingCache` |
| routing-contracts | CONTRACTS | Routing groups, strategy names, auto-router naming and gates, baseline requests, reasoning effort (5 files) | none in scope | `parse_routing_groups`, `validate_routing_strategy`, `classify_strategy_router_model`, `capture_baseline_parameters`, `resolve_supported_reasoning_efforts` |
| request-targets | TARGETS | Wildcards, pod discovery, client credentials, concurrency caps, team filters, batch JSONL, search tools (7 files) | failure-handling | `PatternMatchRouter`, `KubernetesPodDiscovery`, `get_dynamic_litellm_params`, `filter_team_based_models`, `replace_model_in_jsonl`, `SearchAPIRouter` |

The first five modules are contiguous slices of one 16,278-line `Router` class, so they share state:
attributes assigned in the constructor (router-setup) are read by every other slice, and the five slices
call each other by method name. The `router_utils` modules are stateless helpers or self-contained
callback objects that the class calls into.

- [SYS-001] {confirmed} `litellm/router.py:1-460`, `litellm/router_utils/search_api_router.py:1-30` The Router is an in-process Python library with no CLI, HTTP route or process of its own; every entry point is a callable on a `Router` instance or a `router_utils` function ([IF-001]).
- [SYS-002] {confirmed} `litellm/router.py:1333-1343` Each Router owns three two-tier caches (in-memory plus an optional shared Redis client): the router cache for usage, cooldown, health and strategy state, the session-router binding cache, and the prompt-cache pin cache ([RSETUP-014]); cooldown entries live in a dedicated cooldown store with its own in-memory tier ([RSETUP-027], [FAILURE-008]).
- [SYS-003] {confirmed} `litellm/router.py:1529-1547` Construction registers four bound-method callbacks on the process-global `litellm` success and failure lists ([RSETUP-049]), so usage counting and cooldown decisions are driven by LiteLLM's logging callbacks after each provider call, not by the call path itself ([RDISP-170], [RDISP-190], [RDISP-196]).
- [SYS-004] {confirmed} `litellm/router.py:2598-2614`, `litellm/router.py:7471-7600` Most non-chat endpoints are instance attributes built at construction by the endpoint factory rather than methods ([RSETUP-111], [RDISP-001]); their sync or async shape and routing are decided by call type ([RDISP-002], [RDISP-007]).
- [SYS-005] {confirmed} `litellm/router.py:14846-14850`, `litellm/router.py:15802-15806` The public selectors `async_get_available_deployment` and `get_available_deployment` are the internal selection functions wrapped by Kubernetes pod resolution, so every selection result may come back as a copy whose `api_base` points at one pod ([TARGETS-059], [TARGETS-046]).

## Main paths

### 1. Async chat completion that succeeds
1. The caller invokes `Router.acompletion(model, messages, **kwargs)`. It writes `model`, `messages`, `stream` and the per-attempt function into the kwargs ([RSETUP-186]), stamps the trace id and the metadata bucket ([RCALL-058], [RCALL-059]), snapshots the request's own fallback controls ([RSETUP-189], [FAILURE-124]), and sends an int priority through the scheduler ([RSETUP-190], [RCALL-091]).
2. `async_function_with_fallbacks` resets the fallback stamps, reads the per-request fallback lists ([RDISP-092], [RDISP-093]) and runs the retry loop, which pops its control keys (the per-attempt function, fallback lists, retry policy, `num_retries`) and stamps `attempted_retries`/`max_retries` ([RDISP-130]-[RDISP-133]).
3. The loop's `make_call` runs the per-attempt function `_acompletion` ([RDISP-134], [RDISP-150]), which asks `async_get_available_deployment` for a deployment ([RCALL-045]).
4. Selection runs the pre-routing hook for auto, complexity, adaptive and quality routers and the session binding ([RSELECT-061], [RSELECT-090]-[RSELECT-116]), then resolves the strategy and selector from the per-request override, routing group or top-level setting ([RSELECT-063], [RSETUP-105]-[RSETUP-108]).
5. The healthy-deployment pipeline resolves the name ([RSELECT-020]) and filters in a fixed order: access windows and PTU shares ([RSELECT-024], [LIMITS-008], [LIMITS-021]), team and web search ([RSELECT-041], [TARGETS-100], [TARGETS-106]), health checks ([RSELECT-043]), cooldowns ([RSELECT-044], [FAILURE-011]), paused deployments ([RSELECT-046]), the optional callback filters ([RSELECT-047], [AFFINITY-009]), context-window, RPM, region and parameter checks ([RSELECT-048], [RSELECT-200]-[RSELECT-211]), tags, plugins, `order`, failover and retry exclusions ([RSELECT-049]-[RSELECT-053]).
6. The strategy picks one survivor: weighted random for `simple-shuffle` ([RSELECT-067]) or the strategy selector ([RSELECT-068], [RSETUP-083]); the pick is recorded and traced ([RSELECT-069], [RSELECT-070]) and may be rewritten to a pod IP ([SYS-005]).
7. `_update_kwargs_with_deployment` binds the pick: router defaults ([RCALL-064]), client-side credentials ([RCALL-065], [TARGETS-063]), tools, metadata bucket and tags ([RCALL-066]-[RCALL-074]), I/O-token slot reset ([RCALL-071], [LIMITS-083]), timeouts ([RCALL-078], [RCALL-082], [RCALL-083]) and the cached client ([RCALL-081]).
8. The provider call `litellm.acompletion` runs inside the deployment's concurrency slot together with the strategy pre-call checks ([RCALL-049], [RCALL-050], [RDISP-218], [TARGETS-072]); a filtered response becomes `ContentPolicyViolationError` when a content-policy fallback exists ([RCALL-051]).
9. On return the attempt counts the success ([RCALL-054]); the success callback increments `<id>:successes` and the per-minute TPM/RPM usage keys ([RDISP-172], [RDISP-173], [RDISP-182]); `make_call` adds usage headers ([RDEPLOY-147]); the loop and the entry add `x-litellm-attempted-retries` and `x-litellm-attempted-fallbacks: 0` ([RDISP-134], [RDISP-095]).

### 2. A deployment fails: cooldown and same-group retry
1. The attempt logs the error, counts it and stamps the failed deployment id and its configured `num_retries` on the exception ([RCALL-057], [RCALL-060], [RCALL-061]).
2. LiteLLM's failure callback reaches `deployment_callback_on_failure`, which skips some cases, increments `<id>:fails` and asks `set_cooldown_deployments` ([RDISP-190]-[RDISP-193], [FAILURE-021]).
3. The cooldown decision applies its gates ([FAILURE-022]-[FAILURE-030]), the status gate ([FAILURE-031]), then either the deployment's own policy ([FAILURE-036]-[FAILURE-041]), the rate-based default rules ([FAILURE-042]-[FAILURE-045], [CFG-118]) or the allowed-fails counter ([FAILURE-046]-[FAILURE-049]), and writes `deployment:<id>:cooldown` with a TTL ([FAILURE-001], [FAILURE-006], [FAILURE-052]).
4. The retry loop resolves the retry count ([RDISP-131], [RDISP-136]) and an applicable retry policy ([RDISP-138], [FAILURE-099]-[FAILURE-105]) or the generic eligibility checks ([RDISP-140], [RDISP-155]-[RDISP-158]), sleeps the backoff ([RDISP-142], [RDISP-160]-[RDISP-162]) and retries, recording breadcrumbs and a skip list ([RDISP-143]-[RDISP-148], [RDISP-200]-[RDISP-202]).
5. The next selection excludes cooled and skipped deployments ([RSELECT-044], [RSELECT-053], [RSELECT-140]); when nothing survives it raises `RouterRateLimitError` with status `429` ([RSELECT-054], [FAILURE-179]).

### 3. Retries exhausted: cross-group fallback
1. The fallback dispatcher receives the final error ([RDISP-096]) and re-raises at once for the cases in [RDISP-101]: fallbacks disabled, no `model`, a guardrail intervention, or an unsupported-parameter error while `fallback_on_unsupported_params` is off.
2. It first tries `order` levels within the group ([RDISP-103], [RDISP-104]) and, when enabled, weighted failover to the group's other deployments ([RDISP-106], [RDISP-120]-[RDISP-124]).
3. It picks a chain: context-window ([RDISP-108]), content-policy ([RDISP-110]) or generic ([RDISP-111]), resolved per lookup group by [FAILURE-114]-[FAILURE-120].
4. `run_async_fallback` walks the chain one target at a time: depth cap ([FAILURE-138]), skip rules including the access and budget gates ([FAILURE-140]-[FAILURE-145]), breadcrumbs and re-entry into the fallback entry with `fallback_depth + 1` ([FAILURE-146]-[FAILURE-149]), cooldown of a failed hop ([FAILURE-067]-[FAILURE-070]), and response headers on success ([FAILURE-150], [FAILURE-157], [FAILURE-158]).
5. A successful hop's response is returned ([RDISP-113]); otherwise the original exception is raised with an outcome message appended ([RDISP-112], [RDISP-115], [TARGETS-091]).

### 4. A stream breaks after it opened
1. `_acompletion` opens a deferred stream eagerly and reads the first chunk before returning, so a pre-content failure is retried like any other error ([RCALL-052], [RCALL-053]), then wraps the stream ([RCALL-055], [RCALL-001]).
2. On a mid-stream error the chat wrapper decides whether output was committed ([RCALL-005]): an uncommitted break re-enters the fallback chain with the snapshot kwargs ([RCALL-007]); a committed, continuation-eligible break continues on a prefill-capable deployment ([RCALL-008], [RCALL-019], [AFFINITY-130]-[AFFINITY-141]); any other break surfaces the provider's original error ([RCALL-006]).
3. The Responses API wrapper holds lifecycle events and falls back on any mid-stream error ([RCALL-027]-[RCALL-036]); the `/v1/messages` wrapper buffers frames until commit and retries within the group before falling back ([RCALL-128]-[RCALL-152]).

### 5. Non-chat endpoints through the factory
1. Construction binds endpoint attributes such as `aresponses`, `aanthropic_messages`, vector-store, video, container, skills, interactions and agent calls ([RSETUP-110]-[RSETUP-127]).
2. The factory gives each call type a sync or async wrapper ([RDISP-002]-[RDISP-007]) and routes it by branch: generic chain, Responses chain, Anthropic chain, vector-store, container, response-id, interactions and agent routers ([RDISP-008]-[RDISP-021], [RDISP-030]-[RDISP-046]); names with no branch return `None` ([RDISP-023]-[RDISP-026], suspected defect [RDISP-296]).
3. The generic chain `_ageneric_api_call_with_fallbacks` runs the same fallback and retry loop as chat ([RCALL-116], [RDISP-090]), selects and binds per attempt with the `litellm_metadata` bucket and pass-through timeouts ([RCALL-117]-[RCALL-122], [RCALL-077], [TARGETS-136]).
4. Embeddings, files and batches have hand-written entries in router-dispatch ([RDISP-052]-[RDISP-087]); search tools go through `SearchAPIRouter` ([TARGETS-139]-[TARGETS-149]).

### 6. Loading and changing deployments
1. The constructor stores settings and loads `model_list` through `set_model_list` ([RSETUP-001]-[RSETUP-058], [RSETUP-022]), which resets the registries and builds each row ([RDEPLOY-001]-[RDEPLOY-011]).
2. Building a row assigns the stable id ([RDEPLOY-007], [RDISP-240]), expands `os.environ/` secrets ([RDEPLOY-006]), applies the environment gate ([RDEPLOY-014], [RSETUP-202]-[RSETUP-207]), validates PTU terms, access windows and `tag_regex` ([RDEPLOY-015], [RDEPLOY-016], [RDEPLOY-022]), inherits and registers prices ([RDEPLOY-019], [RDEPLOY-020], [RDEPLOY-080]), and registers wildcards and strategy routers ([RDEPLOY-026], [RDEPLOY-060]-[RDEPLOY-072], [CONTRACTS-014]).
3. At runtime the proxy calls `add_deployment`, `upsert_deployment` and `delete_deployment` ([RDEPLOY-040]-[RDEPLOY-056]), which apply fewer checks than the model-list path ([RDEPLOY-042], suspected defect [RDEPLOY-207]), and `update_settings` changes the allowed settings in place ([RSELECT-152]-[RSELECT-162]).
4. A per-request Router is detached with `discard()` ([RSETUP-062], [RSETUP-063]), which leaves some global registrations behind ([RSETUP-064], suspected defect [RSETUP-298]).

## Global invariants
- [SYS-010] {confirmed} `litellm/router.py:1-3315`, `litellm/router.py:1303-1346` The Router writes no files and no database rows; its only durable state is TTL-bound keys in the two-tier caches, and the registry, counters and pod caches live only in the process ([RSETUP-270], [DATA-133], [DATA-134]).
- [SYS-011] {confirmed} `litellm/router_utils/cooldown_cache.py:122-128`, `litellm/router_utils/router_callbacks/track_deployment_metrics.py:52-58` With Redis configured, cooldown entries, allowed-fails counters, health state, TPM/RPM usage counters and affinity and prompt-cache pins are shared across replicas ([DATA-131], [FAILURE-187]); the per-minute success and failure counters, pre-call RPM reads and concurrency slots stay per process ([DATA-132], [FAILURE-072], [RSELECT-232], [TARGETS-079]).
- [SYS-012] {confirmed} `litellm/router.py:4436-4438`, `litellm/router.py:8446-8464` The Router writes its per-request bookkeeping in place into the caller's metadata bucket, chosen as `metadata` or `litellm_metadata` by the calling function's name ([RCALL-161], [RDISP-261], [TARGETS-136]); a caller that reuses one metadata dict across requests sees their stamps mixed ([RDISP-285]).
- [SYS-013] {confirmed} `litellm/router.py:8690-8761`, `litellm/router_utils/fallback_event_handlers.py:820-900` Retries of one request run strictly one after another, fallback targets are tried one at a time in chain order, and nothing carries an idempotency key, so a retried or re-targeted non-idempotent operation is sent again ([RDISP-282], [FAILURE-194], [RDISP-286]).
- [SYS-014] {confirmed} `litellm/router.py:14436-14452`, `litellm/router.py:14786-14797` Selection takes no locks: cooldown and health state are read once per call, so a deployment can enter cooldown between selection and the provider call ([RSELECT-261]).
- [SYS-015] {confirmed} `litellm/router.py:13524-13573`, `litellm/router.py:8465-8467` Router-level settings are read from router attributes at call time, so a change through `update_settings` applies from the next call without rebuilding the router ([RSELECT-252], [RDISP-273], [FAILURE-193]).
- [SYS-016] {confirmed} `litellm/router.py:9082`, `litellm/router.py:12300-12301` Per-minute usage keys use the UTC wall-clock minute formatted `%H-%M` (no date), and cooldown and health expiry compare stored wall-clock timestamps with the reader's clock ([RDISP-266], [RDEPLOY-194], [LIMITS-150], [FAILURE-188]); only pod discovery uses a monotonic clock ([TARGETS-167]).
- [SYS-017] {confirmed} `litellm/router.py:14830-14844`, `litellm/router.py:8417-8431` Errors are passed through unwrapped: selection re-raises the original exception object ([RSELECT-226]), `completion` re-raises the loop's exception as is ([RSETUP-265]), and when every fallback fails the dispatcher raises the original exception, not a fallback's ([RDISP-115]).
- [SYS-018] {confirmed} `litellm/router.py:4348`, `litellm/router.py:6787-6795` Provider traffic leaves only through `litellm.*` SDK functions ([RCALL-164], [RDISP-265]); the Router's own network use is limited to Redis, DNS lookups for pod discovery ([TARGETS-164]) and the optional `/v1/models` limit probe ([RDEPLOY-108]).
- [SYS-019] {inferred} `litellm/router.py:2019-2028`, `litellm/router.py:14506` The Router performs no authentication or authorization of its own: it trusts the team id, priority, strategy override and internal control keys it finds in the request kwargs ([RSETUP-293], [RSELECT-221], [LIMITS-156], [RDISP-258]); the proxy is expected to sanitise them.
- [SYS-020] {confirmed} `litellm/router.py:15618-15800`, `litellm/router.py:2908-2925` The sync paths do less than the async ones: sync selection skips the pre-routing hook, team filter, callback filters, tags and plugins ([RSELECT-128]), sync chat has no priority scheduling or alerting ([RSETUP-160]), and `function_with_fallbacks` runs the async loop on a separate event loop ([RDISP-165]).

## Cross-cutting concerns
- **Errors.** Every error a caller can see is catalogued in `01-interfaces.md` ([IF-200]-[IF-245]). The no-deployment error is built in failure-handling ([FAILURE-178]-[FAILURE-181]); fallback outcome messages are formatted in request-targets ([TARGETS-089]-[TARGETS-095]) and gated by `litellm.expose_router_debug_in_errors` ([RDISP-272]).
- **Retries and fallbacks.** Decided in three places: the retry loop and dispatcher (router-dispatch, [RDISP-130]-[RDISP-165], [RDISP-100]-[RDISP-124]), the retry policy and fallback walk (failure-handling, [FAILURE-099]-[FAILURE-155]), and stream recovery (router-calls, [RCALL-001]-[RCALL-016], [RCALL-142]-[RCALL-152]). Precedence of request, deployment and router values is in `03-config.md` ([CFG-110]-[CFG-119]).
- **Cooldowns and health.** Cooldown decision and storage in failure-handling ([FAILURE-001]-[FAILURE-054]); health-check state in [FAILURE-078]-[FAILURE-087]; how selection applies both in [RSELECT-140]-[RSELECT-146].
- **Limits and concurrency.** Concurrency caps in request-targets ([TARGETS-071]-[TARGETS-080]); TPM/RPM, I/O tokens, PTU shares and access windows in deployment-limits ([LIMITS-001]-[LIMITS-115]); pre-call RPM and context-window checks in [RSELECT-200]-[RSELECT-216].
- **Timeouts.** Resolved per attempt in [RCALL-082]-[RCALL-084] and [RCALL-077]; selection and the stream wrappers impose none of their own ([RSELECT-225], [RCALL-165]).
- **Logging, tracing and alerts.** Router logs go to `verbose_router_logger`; deployment printing masks keys ([RSETUP-150]); some debug lines print full kwargs ([RCALL-167]). Selection and retries emit trace events ([RSELECT-070], [RDISP-205]); Slack alerts are fire-and-forget ([RSETUP-194], [FAILURE-175]-[FAILURE-177]).
- **Process-global state.** The Router writes `litellm.suppress_debug_info`, `litellm.cache`, the `litellm.*` callback lists and `litellm.model_cost` ([RSETUP-002], [RSETUP-267], [RDEPLOY-188]), so several routers in one process affect each other ([RSETUP-064], [RDEPLOY-073]).
- **Configuration.** Every setting, default and environment variable is in `03-config.md`; runtime changes go through `update_settings` ([RSELECT-152]).
- **Randomness and time.** Randomness only in the shuffle pick, backoff jitter, search-tool choice and UUIDs ([RSELECT-236], [RDISP-267], [TARGETS-168], [RCALL-166]); clocks as in [SYS-016].
- **Suspected defects.** Each module ends with a "Suspected defects" section; the collected list is `_meta/suspected-defects.md`. The highest-impact ones are [TARGETS-207] (admin `api_key` kept on a caller-chosen `api_base`), [RSETUP-297] (`default_priority` breaks every async chat call), [RSELECT-274] (`flush_cache()` issues `FLUSHALL`) and [RDISP-296] (endpoint names that silently return `None`).

## Glossary
- **Model group**: the public `model_name` a caller asks for; several deployments may share it.
- **Deployment**: one `model_list` entry with `model_name`, `litellm_params` (provider model, credentials, limits) and `model_info` (always an `id`).
- **Deployment id**: `model_info.id`; derived as a SHA-256 of the group name and params when not given ([RDISP-240]).
- **Metadata bucket**: the request kwarg `metadata` or `litellm_metadata` that the Router writes bookkeeping into, in place ([TARGETS-136]).
- **Strategy (routing strategy)**: the rule that picks one deployment among the survivors: `simple-shuffle`, `least-busy`, `usage-based-routing`, `usage-based-routing-v2`, `latency-based-routing`, `cost-based-routing`, plus the accepted names `lar1` and `provider-budget-routing` ([CONTRACTS-116]).
- **Selector**: the object that implements a non-shuffle strategy and doubles as a logging callback ([RSETUP-068], [RSETUP-078]).
- **Routing group**: a named set of model groups that share a strategy, or a `priority` group callable by its own name ([RSETUP-085]-[RSETUP-099], [CONTRACTS-120]).
- **Strategy router (auto-router)**: a deployment whose `litellm_params.model` starts with `auto_router/`; it picks a target group in the pre-routing hook instead of calling a provider ([CONTRACTS-013]-[CONTRACTS-016], [RSELECT-090]).
- **Pre-call check**: a `CustomLogger` registered on `litellm.callbacks` that filters candidates (`async_filter_deployments`) or vetoes a pick (`async_pre_call_check`) ([RSETUP-136], [RDISP-215]-[RDISP-219]).
- **Cooldown**: a time-boxed exclusion of a deployment from selection, stored under `deployment:<id>:cooldown` ([FAILURE-001]).
- **Fallback chain**: the list of other model groups tried after retries are exhausted, chosen from `fallbacks`, `context_window_fallbacks` or `content_policy_fallbacks` ([FAILURE-114]).
- **Committed stream**: a stream whose generated output already reached the caller, so a restart would duplicate it ([RCALL-005]).
- **Continuation**: finishing a broken chat stream on another deployment by sending the partial output as an assistant prefill ([RCALL-008], [AFFINITY-130]).
- **Pin**: a cache entry mapping a caller, session or prompt prefix to a deployment id ([AFFINITY-036], [AFFINITY-109]).
- **PTU share**: a team's slice of a shared provisioned deployment, which restricts who it serves and caps the team's tokens per minute ([LIMITS-020]-[LIMITS-043]).
- **Access window**: a daily local-time interval during which a deployment is reserved for listed teams ([LIMITS-003]-[LIMITS-012]).

## Reading order
1. `01-interfaces.md`: the constructor settings, call methods, per-request control kwargs and error catalog, so you know what callers can do.
2. `modules/router-setup.md`: how a Router is built, which state every other slice reads, and the chat entry points where path 1 starts.
3. `modules/router-selection.md`: the selection pipeline, the heart of path 1 and the place most routing questions are answered.
4. `modules/router-calls.md`: what one attempt sends and how streams are recovered (paths 1 and 4).
5. `modules/router-dispatch.md`: the endpoint factory, retry loop and fallback dispatcher (paths 2, 3 and 5).
6. `modules/failure-handling.md`: cooldowns, retry policy and the fallback walk that router-dispatch drives.
7. `modules/router-deployments.md`: the registry and group metadata behind every lookup (path 6).
8. `modules/deployment-limits.md` and `modules/affinity-checks.md`: the filters and checks that plug into selection.
9. `modules/request-targets.md` and `modules/routing-contracts.md`: helpers and shared contracts, best read on demand.
10. `02-data.md` and `03-config.md` as reference; `_meta/gaps.md` and `_meta/suspected-defects.md` for what needs a decision.
