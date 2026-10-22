# Gaps

Every `{gap}` claim in the specification, grouped by the spec that holds it. A gap is a question the code
does not answer on its own: the behavior depends on code outside the specified scope, on deployment data,
or on an intent nobody wrote down. Each entry gives the claim ID, where the uncertainty arises, the
question, and what would resolve it. Where a gap also has a suspected-defect claim, that claim is named;
the defect list itself is `_meta/suspected-defects.md`.

Totals: 74 gaps (router-setup 6, router-calls 6, router-dispatch 7, router-selection 6,
router-deployments 7, failure-handling 6, deployment-limits 7, affinity-checks 8, request-targets 6,
routing-contracts 6, interfaces 2, data 4, config 3).

Kinds of resolution used below:
- **Test**: a unit or integration test that pins the behavior, then turn the gap into a claim.
- **Read**: a named dependency outside the specified scope whose code settles the question.
- **Ask**: an intent question for the owners of the Router or the proxy; the code works either way.

## router-setup (RSETUP)

- **[RSETUP-285]** `litellm/router.py:1326`, `litellm/router.py:1653-1669`. Does building the Redis client open a connection or ping Redis during construction, and what happens when Redis is unreachable then? *Resolve:* read `RedisCache.__init__` and `RedisClusterCache` in `litellm/caching/redis_cache.py`; test a Router built with an unreachable `redis_host`.
- **[RSETUP-286]** `litellm/router.py:1630-1651`. Is it intended that `discard()` leaves strategy selectors and the Slack alerting logger on the global callback lists? *Resolve:* ask the Router owners; test that a per-request `user_config` router leaves no callbacks after `discard()`. Suspected defect: [RSETUP-298].
- **[RSETUP-287]** `litellm/router.py:1404-1413`. With `ignore_invalid_deployments=True`, does an entry without `litellm_params` make the latency-map loop raise `KeyError`? *Resolve:* test `Router(model_list=[{"model_name": "x"}], ignore_invalid_deployments=True)`.
- **[RSETUP-288]** `litellm/router.py:2985-2986`. A sync attempt addressed by deployment id skips the global pre-call checks, including RPM accounting for `usage-based-routing-v2`; intended, and does the async body match? *Resolve:* test both paths with a deployment id and a usage-based-routing-v2 selector; ask the owners.
- **[RSETUP-289]** `litellm/router.py:1467-1478`. Is the growth of the global `litellm.fallbacks` list by one wildcard entry per construction intended? *Resolve:* ask the owners. Suspected defect: [RSETUP-299].
- **[RSETUP-290]** `litellm/router.py:1124-1601`. Is a router that is never `discard()`ed ever removed from the global callback lists? *Resolve:* read the callback manager in `litellm/litellm_core_utils/logging_callback_manager.py` for size caps or weak references.

## router-calls (RCALL)

- **[RCALL-182]** `litellm/router.py:5530`. What do the rerank SDK call and each provider do with the callable `input` that `arerank` stores? *Resolve:* read `litellm/rerank_api/main.py` and the provider transformations; test `arerank` with a mock provider that records kwargs. Suspected defect: [RCALL-190].
- **[RCALL-184]** `litellm/router.py:3965-3972`, `litellm/router.py:4026-4030`. Is falling back after Responses output already reached the client intended? *Resolve:* ask the owners; test a Responses stream that breaks after `response.output_text.delta`. Suspected defect: [RCALL-191].
- **[RCALL-185]** `litellm/router.py:3492-3494`, `litellm/router.py:4186-4187`. How do proxy and SDK consumers handle the single `None` chunk yielded when a chat stream's fallback is non-streaming? *Resolve:* read the proxy streaming generator in `litellm/proxy/proxy_server.py`; test end to end. Suspected defect: [RCALL-192].
- **[RCALL-186]** `litellm/router.py:5249`, `litellm/router.py:5906`. Are credentials in debug-logged kwargs masked by any logging handler? *Resolve:* read the `verbose_router_logger` handler setup in `litellm/_logging.py`. Suspected defect: [RCALL-193].
- **[RCALL-187]** `litellm/router.py:5247`, `litellm/router.py:5264`. Does any consumer read the per-model call counters and so miss sync image calls keyed under `""`? *Resolve:* grep the proxy and integrations for `success_calls` and `total_calls`. Suspected defect: [RCALL-194].
- **[RCALL-188]** `litellm/router.py:4391-4405`. Are timeouts deliberately excluded from `fail_calls`? *Resolve:* ask the owners.

## router-dispatch (RDISP)

- **[RDISP-027]** `litellm/router.py:2566`, `litellm/router.py:7865-7876`, `litellm/router.py:8034`. Does wrapping the synchronous `create_interaction` in the async wrapper raise `TypeError` for a non-awaitable SDK result? *Resolve:* read `litellm/interactions/main.py::create`; test `await router.create_interaction(...)` with a mock.
- **[RDISP-290]** `litellm/router.py:2291-2293`, `litellm/router.py:2507-2516`, `litellm/router.py:2543-2545`, `litellm/router.py:2566-2572`. Are the bound names that match no dispatch branch intentional? *Resolve:* ask the owners. Suspected defect: [RDISP-296].
- **[RDISP-291]** `litellm/router.py:6989-6997`. What happens to files already created on other deployments when one upload of a multi-deployment file creation fails? *Resolve:* read the managed-files hook in `litellm/proxy/hooks/managed_files.py`; test with one failing deployment. Suspected defect: [RDISP-299].
- **[RDISP-292]** `litellm/router.py:8462`, `litellm/router.py:8191-8203`. Should `include_fallback_errors` follow the strict `is True` check or the truthiness that decides the header? *Resolve:* ask the owners.
- **[RDISP-293]** `litellm/router.py:9518-9536`. Is the synchronous `_get_healthy_deployments` used outside tests, given its inconsistent return type? *Resolve:* grep callers across the repository. Suspected defect: [RDISP-300].
- **[RDISP-294]** `litellm/router.py:8255-8259`. Is raising the last order level's error without the outcome suffix intended? *Resolve:* ask the owners. Suspected defect: [RDISP-298].
- **[RDISP-295]** `litellm/router.py:8754-8761`. Is the backoff sleep after the final failed retry intended? *Resolve:* ask the owners; a timing test pins it. Suspected defect: [RDISP-297].

## router-selection (RSELECT)

- **[RSELECT-023]** `litellm/router.py:14142-14153`. When the reservation or PTU filter empties a single id-addressed deployment without raising, does indexing `[0]` surface an `IndexError`? *Resolve:* test an id-addressed request for a deployment with an active window that excludes the caller.
- **[RSELECT-119]** `litellm/router.py:15218-15232`. Is the tolerance of session-binding write failures provided entirely by the two-tier cache, including the in-memory write? *Resolve:* read `DualCache.async_set_cache` in `litellm/caching/dual_cache.py`.
- **[RSELECT-270]** `litellm/router.py:15045-15047`, `litellm/router.py:15066-15077`. Is carrying the stale plugin candidate list into a fallback group intended? *Resolve:* ask the owners. Suspected defect: [RSELECT-276].
- **[RSELECT-271]** `litellm/router.py:13566-13567`. Is a stale access-group map acceptable after an alias update? *Resolve:* ask the owners. Suspected defect: [RSELECT-277].
- **[RSELECT-272]** `litellm/router.py:15644-15693`. Can a team-owned deployment under a shared `model_name` serve another team's sync request? *Resolve:* read `should_include_deployment` and team-scoped `get_all_deployments` ([RDEPLOY-162], [RDEPLOY-163]); test a sync `completion` from another team. Related defect: [RSELECT-278].
- **[RSELECT-273]** `litellm/router.py:13510-13518`. After switching to `lar1`, what does a non-shuffle pick return on the pass-through and sync paths? *Resolve:* test `update_settings(routing_strategy="lar1")` followed by a sync call.

## router-deployments (RDEPLOY)

- **[RDEPLOY-075]** `litellm/router.py:10563-10565`. Do strategy objects dropped by `set_model_list` hold resources or callbacks that outlive the reset? *Resolve:* read the strategy routers under `litellm/router_strategy/`.
- **[RDEPLOY-199]** `litellm/router.py:10552-10568`, `litellm/router.py:1406`. Is a second `set_model_list` call on a live router supported? *Resolve:* ask the owners. Suspected defect: [RDEPLOY-205].
- **[RDEPLOY-200]** `litellm/router.py:10604-10623`. Is one shared id for every organization-expanded deployment intended? *Resolve:* ask the owners. Suspected defect: [RDEPLOY-208].
- **[RDEPLOY-201]** `litellm/router.py:10635`. Should names of dropped rows still count as known models? *Resolve:* ask the owners; read the proxy's model-recognition checks.
- **[RDEPLOY-202]** `litellm/router.py:12274-12278`. Should a dict alias without `hidden` default to visible instead of raising `KeyError`? *Resolve:* read the alias type in `litellm/types/router.py` to see whether `hidden` is required.
- **[RDEPLOY-203]** `litellm/router.py:12198-12201`, `litellm/router.py:12117-12127`. Is the first-member asymmetry in group `tpm`/`rpm` totals intended? *Resolve:* ask the owners; test a two-member group whose first member has only catalog limits.
- **[RDEPLOY-204]** `litellm/router.py:10820-10851`. Are runtime-added deployments meant to skip the environment gate, `tag_regex` and access-window checks? *Resolve:* read the proxy's model write endpoints in `litellm/proxy/management_endpoints/model_management_endpoints.py`. Suspected defect: [RDEPLOY-207].

## failure-handling (FAILURE)

- **[FAILURE-020]** `litellm/router_utils/cooldown_cache.py:150-151`. What happens when a stored cooldown dict lacks `timestamp` or `cooldown_time`? *Resolve:* test with a hand-written cooldown entry.
- **[FAILURE-054]** `litellm/router_utils/cooldown_handlers.py:697-717`. What happens if `router.allowed_fails` becomes `None` after construction? *Resolve:* test `update_settings(allowed_fails=None)` (note `update_settings` int-casts, [RSELECT-153]) and direct attribute assignment.
- **[FAILURE-200]** `litellm/router_utils/cooldown_handlers.py:706-716`, `litellm/caching/redis_cache.py:894-897`. What expiry does a Redis allowed-fails counter get with a TTL override of `0`? *Resolve:* read `RedisCache.increment_cache`; test against a real Redis.
- **[FAILURE-201]** `litellm/router_utils/cooldown_callbacks.py:21-78`. Is ignoring `cooldown_time` in the cooldown event callback intended? *Resolve:* ask the owners of the Prometheus integration.
- **[FAILURE-202]** `litellm/router_utils/cooldown_handlers.py:254-258`. Is suppressing cooldown on any message containing `APIConnectionError` intended? *Resolve:* ask the owners. Suspected defect: [FAILURE-209].
- **[FAILURE-205]** `litellm/router_utils/fallback_event_handlers.py:547-553`, `litellm/router_utils/fallback_event_handlers.py:857-861`. Can a caller steer fallback lookup through `model_group` or `original_model_group` in its own metadata? *Resolve:* read the proxy's metadata sanitising in `litellm/proxy/litellm_pre_call_utils.py`.

## deployment-limits (LIMITS)

- **[LIMITS-190]** `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:346-348`, `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:298-311`. Do success-callback kwargs always carry the reservation stash where reconciliation looks? *Resolve:* read how the logging object builds callback kwargs in `litellm/litellm_core_utils/litellm_logging.py`; test the Anthropic messages surface. Suspected defect: [LIMITS-200].
- **[LIMITS-191]** `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:180-198`, `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:237-238`. Is subtracting cache reads from Anthropic-style input intended? *Resolve:* ask the owners; compare with the provider usage normalisation. Suspected defect: [LIMITS-199].
- **[LIMITS-192]** `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:132-140`, `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:366-378`. Are `litellm_params.model` and the logged `litellm_model_name` always the same string? *Resolve:* read where `hidden_params.litellm_model_name` is set; test with a provider-prefixed model. Same question as [DATA-044]. Suspected defect: [LIMITS-198].
- **[LIMITS-193]** `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:346-364`, `litellm/exceptions.py:463-486`. Is the default category `vendor_rate_limit` on the module's own rejections intended? *Resolve:* ask the owners. Suspected defect: [LIMITS-197].
- **[LIMITS-194]** `litellm/caching/redis_cache.py:894-950`, `litellm/caching/dual_cache.py:590-597`. Does the async Redis increment with `refresh_ttl=False` set the TTL the same way as the sync one? *Resolve:* read `RedisCache.async_increment`.
- **[LIMITS-195]** `litellm/router.py:9605-9614`, `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:323-326`. Can a reservation already refunded on a TPM/RPM rejection be refunded a second time by the failure handlers? *Resolve:* read whether the logging object copies metadata; test the counters after a rejected request.
- **[LIMITS-196]** `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:407-417`. Can a non-comparable I/O limit value reach the check? *Resolve:* read the deployment field types in `litellm/types/router.py` and the proxy's model validation.

## affinity-checks (AFFINITY)

- **[AFFINITY-190]** `litellm/router_utils/pre_call_checks/prompt_caching_deployment_check.py:141-198`. Does the logging layer catch a `KeyError` from the prompt-cache success callback, and does it stop other callbacks? *Resolve:* read success-callback dispatch in `litellm/litellm_core_utils/litellm_logging.py`.
- **[AFFINITY-191]** `litellm/proxy/litellm_pre_call_utils.py:387-420`, `litellm/router_utils/pre_call_checks/deployment_affinity_check.py:252-257`. Can a caller send `litellm_session_id_generated` to opt its session out of pinning? *Resolve:* read the proxy's untrusted-metadata list; test a request carrying the field.
- **[AFFINITY-192]** `litellm/router_utils/pre_call_checks/prompt_caching_deployment_check.py:155-159`. Which `call_type` do async `/v1/messages` calls log, and is excluding them from pin writes intended? *Resolve:* test an `aanthropic_messages` call and inspect the standard logging object; ask the owners.
- **[AFFINITY-193]** `litellm/router_utils/pre_call_checks/encrypted_content_affinity_check.py:362-363`. Can `litellm_metadata` arrive as a non-dict value? *Resolve:* grep proxy request preparation for writers of `litellm_metadata`.
- **[AFFINITY-194]** `litellm/router_utils/pre_call_checks/deployment_affinity_check.py:485-494`. Is pinning a caller to a deployment whose first request failed intended? *Resolve:* ask the owners. Related defect: [AFFINITY-198].
- **[AFFINITY-195]** `litellm/router_utils/prompt_caching_cache.py:135-139`, `litellm/router_utils/pre_call_checks/prompt_caching_deployment_check.py:134-137`. Is prompt-cache affinity silently disabled for a deployment whose `model_info.id` is not a string? *Resolve:* test with an integer id.
- **[AFFINITY-196]** `litellm/router_utils/prompt_caching_cache.py:369`, `litellm/caching/dual_cache.py:401-436`. How long can another pod's throttled batch read miss a freshly written pin? *Resolve:* read the batch-read throttle in `DualCache`; measure with two routers on one Redis.
- **[AFFINITY-197]** `litellm/router_utils/pre_call_checks/deployment_affinity_check.py:379-394`. When `previous_response_id` names a non-candidate, does the upstream reject the request, and should the router degrade instead? *Resolve:* test against a provider; ask the owners.

## request-targets (TARGETS)

- **[TARGETS-180]** `litellm/router_utils/clientside_credential_handler.py:28-79`, `litellm/router_utils/clientside_credential_handler.py:134`. Is a named credential still forwarded to a caller-redirected host? *Resolve:* read the federation wire-name lists and named-credential hydration; test an `api_base` redirect on a deployment with `litellm_credential_name`. Related defect: [TARGETS-207].
- **[TARGETS-181]** `litellm/router_utils/client_initalization_utils.py:73-78`. Can the in-memory cache evict a parallel-request limiter while slots are held? *Resolve:* read the `DualCache` in-memory default TTL and eviction policy.
- **[TARGETS-182]** `litellm/router_utils/pattern_match_deployments.py:183-230`. Is the leading-wildcard rewrite meant to keep the provider prefix, as the docstring says? *Resolve:* ask the owners. Suspected defect: [TARGETS-208].
- **[TARGETS-183]** `litellm/router_utils/kubernetes_pod_discovery.py:99-101`. How many synchronous DNS lookups can stall at once? *Resolve:* test with a resolver that never returns; read the thread-pool default.
- **[TARGETS-184]** `litellm/router_utils/common_utils.py:212-217`. Is `get_litellm_params_sensitive_credential_hash` dead code? *Resolve:* grep for callers outside tests; ask the owners.
- **[TARGETS-185]** `litellm/router_utils/search_api_router.py:157-162`. Can the debug log of search kwargs contain request-level secrets? *Resolve:* read the logger handler setup; test with an `api_key` in the search kwargs.

## routing-contracts (CONTRACTS)

- **[CONTRACTS-147]** `litellm/router_utils/auto_router_model_naming.py:99-105`, `litellm/router_utils/auto_router_model_naming.py:163`. Is skipping object-form complexity tiers in dependency listing intended? *Resolve:* ask the owners. Suspected defect: [CONTRACTS-155].
- **[CONTRACTS-148]** `litellm/router_utils/baseline_request.py:80-85`, `litellm/router_utils/baseline_request.py:113-116`. What does JSON validation do with tuples, non-string keys and non-finite floats? *Resolve:* test `capture_baseline_parameters` against the installed pydantic.
- **[CONTRACTS-149]** `litellm/router_utils/auto_router_tuning_baseline.py:113-122`. Is "last row wins" intended for routers that share an identity? *Resolve:* ask the owners; check production configs for duplicate identities.
- **[CONTRACTS-150]** `litellm/router_utils/auto_router_model_naming.py:218-221`, `litellm/router_utils/auto_router_model_naming.py:305-307`. Can rows with both classifier keys exist in the database, and which count is authoritative? This is the open question carried in `_meta/questions.md`. *Resolve:* query production data; ask the licensing owners. Suspected defect: [CONTRACTS-157].
- **[CONTRACTS-151]** `litellm/router_utils/reasoning_effort_capability.py:177-184`. Should a declared `reasoning_effort_levels` imply reasoning support? *Resolve:* ask the owners. Suspected defect: [CONTRACTS-156].
- **[CONTRACTS-152]** `litellm/router.py:12206-12220`, `litellm/router_utils/reasoning_effort_capability.py:198-205`. Which group rule is intended for unknown deployments? *Resolve:* ask the owners. Suspected defect: [RDEPLOY-210].

## Interfaces (IF)

- **[IF-077]** `litellm/router.py:1229-1230`, `litellm/router.py:8879-8885`, `litellm/router.py:3028-3035`. Does weighted failover take effect on the sync path despite the docstring, and is mid-stream continuation ever applied to sync streams? *Resolve:* test `completion()` with `enable_weighted_failover=True` and a failing deployment.
- **[IF-318]** `litellm/router.py:5530`, `litellm/router.py:5567-5574`. Does the provider rerank call ignore, reject or serialise the stray `input`? Same question as [RCALL-182].

## Data (DATA)

- **[DATA-044]** `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:366-386`, `litellm/router_utils/pre_call_checks/model_rate_limit_check.py:132-140`. Are the TPM write and read keys always the same string? Same question as [LIMITS-192].
- **[DATA-149]** `litellm/router.py:9104-9139`, `litellm/router.py:8957-8990`. Can one call fire both the sync and async success callbacks and double-count `<id>:successes`? *Resolve:* read how the logging object chooses sync versus async success callbacks; test one async call and inspect the counter.
- **[DATA-150]** `litellm/router.py:9266-9297`, `litellm/router.py:9055-9081`. Is it intended that failures always add to the global `rpm` counter while successes add only for limited deployments? *Resolve:* ask the owners.
- **[DATA-151]** `litellm/router.py:13589-13640`, `litellm/router.py:1142`. Are the cached-client reads dead, so provider clients are never reused through the router? *Resolve:* grep for writers of `<id>_async_client` and `<id>_client` across the repository. Suspected defect: [RSELECT-280].

## Config (CFG)

- **[CFG-131]** `litellm/router.py:8497-8549`. Does the proxy strip `mock_testing_*` flags from client requests? *Resolve:* read the proxy's request-body filtering; test a proxy request carrying `mock_testing_fallbacks`.
- **[CFG-183]** `litellm/router.py:1570`, `litellm/router.py:1145-1175`. Can routers built with shared mutable defaults leak configuration into each other? *Resolve:* test two routers built with defaults, mutate one's `model_group_retry_policy`, inspect the other. Related defect: [RSETUP-299].
- **[CFG-184]** `litellm/router_utils/router_callbacks/track_deployment_metrics.py:44-75`. Does each increment refresh the per-minute counter TTL? Answered for the in-memory tier by [FAILURE-073] and [FAILURE-051] (a live TTL is not extended, so the window is fixed); the claim can be closed after a test pins it.
