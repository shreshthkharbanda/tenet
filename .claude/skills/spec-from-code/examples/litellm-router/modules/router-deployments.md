---
kind: module
module: router-deployments
prefix: RDEPLOY
commit: 93b79d2587d186fb7266556a34a22d03f187a3da
status: draft
scope:
  - litellm/router.py:9866-13216
---
# Deployment registry and model metadata (RDEPLOY)

## Purpose
This module owns the Router's deployment registry. A *deployment* is one `model_name` / `litellm_params` / `model_info` row.
The module decides five things that no other module decides:
- how a config row becomes a stored deployment: validation, id assignment, secret expansion, pricing inheritance, environment gating and strategy-router registration;
- how deployments are added, upserted, deleted and indexed;
- what each deployment contributes to the process-global price catalog `litellm.model_cost`, and how that is rebuilt after a catalog reload;
- how a model name, a deployment id or a team's public name resolves to deployments, credentials and metadata;
- how per-group metadata is aggregated: limits, prices, capabilities, usage and rate-limit headers.

It also builds and tears down the four strategy-router registries (`auto_routers`, `complexity_routers`, `adaptive_routers`, `quality_routers`).

## Scope and boundaries
In scope: `litellm/router.py` lines 9866-13216, from `_inherit_builtin_base_rates_for_off_peak` through `_deployment_supports_param`. The rest of `Router` is context only.

Out of scope, by owner:
- `router-setup` (router.py:1-3315) owns the following. This module relies on them as {inferred} context:
  - `__init__`, which creates the indexes and registries, calls `set_model_list` and adds the router to the `_live_routers` WeakSet;
  - `generate_model_id`, `_inherit_builtin_cache_pricing`, `_inherit_builtin_service_tier_pricing` and `_cost_map_backend_model` (router.py:9762-9864, owned by `router-dispatch`, [RDISP-240], [RDISP-244]-[RDISP-246]);
  - `get_routing_group` and `is_recognized_model` ([RSETUP-092], [RSETUP-096]);
  - `_ensure_deployment_affinity_callback` and `add_optional_pre_call_checks` ([RSETUP-146], [RSETUP-136]).
- `router-selection` (router.py:13217-16278) owns the following. This module calls them:
  - `get_model_list`, `get_model_list_of_routed_group` and `_get_wildcard_deployments` ([RSELECT-001], [RSELECT-005], [RSELECT-002]);
  - `get_model_from_alias`, `_try_early_resolve_deployments_for_model_not_in_names`, `is_deployment_blocked` ([RSELECT-011], [RSELECT-018], [RSELECT-143]);
  - `_invalidate_model_group_info_cache`, `_invalidate_access_groups_cache` and `_tier_params_the_target_accepts` ([RSELECT-007], [RSELECT-031]).
- `routing-contracts`: strategy-router model naming, capability ceilings, routing-group priority, reasoning-effort capability ([CONTRACTS-014], [CONTRACTS-063], [CONTRACTS-118], [CONTRACTS-115]).
- `request-targets`: the wildcard `PatternMatchRouter`, `team_may_use_deployment`, capability-flag stripping, credential-mismatch warnings ([TARGETS-190], [TARGETS-085], [TARGETS-117], [TARGETS-111]).
- `deployment-limits`: PTU and access-window validation ([LIMITS-002], [LIMITS-046]).
- `failure-handling`: header helpers and the health-state cache ([FAILURE-171], [FAILURE-083]).
- Outside the survey scope: the strategy-router implementations (`litellm/router_strategy/**`), `litellm.get_model_info`, `litellm.register_model`, `get_llm_provider`, the upstream `/v1/models` fetcher and the caches.

Inbound callers:
- the proxy: model add/update/delete jobs, `/v1/models` listing, `/model_group/info`, credential and passthrough endpoints, budget reservation, health filtering;
- `router-calls` (`set_response_headers`, `_register_deployment_pricing` for client-side credentials);
- `router-selection` (`_region_routable_deployments`, `_async_routable_cooled_deployment_ids`, `_deployment_accepts_param`, `_deployment_supports_param`, `get_all_deployments`);
- `router-dispatch` (`set_response_headers` after a call).

Dead code in range:
- `_build_model_name_index` and `_build_model_id_to_deployment_index_map` have no production caller, only tests ([RDEPLOY-150]).
- Two blocks in `_add_deployment` are commented out: the `*` default-deployment logic and the client initialization ([RDEPLOY-151]).

## Public surface
| Entry point | Kind | Inputs | Outputs | Errors | Claims |
|---|---|---|---|---|---|
| `Router.set_model_list(model_list)` | method | list of deployment dicts | none; rebuilds registry | `ValueError`/`Exception` from row validation unless `ignore_invalid_deployments` | [RDEPLOY-001]..[RDEPLOY-012], [RDEPLOY-013]..[RDEPLOY-027] |
| `Router.add_deployment(deployment)` | method | `Deployment` | stored `Deployment` (capability flags stripped) or `None` if id exists | any error propagates | [RDEPLOY-040]..[RDEPLOY-045] |
| `Router.upsert_deployment(deployment)` | method | `Deployment` | input `Deployment`, or `None` (unchanged or failed) | propagates unless `ignore_invalid_deployments`; id-lookup and flag-stripping errors always propagate | [RDEPLOY-046]..[RDEPLOY-052] |
| `Router.delete_deployment(id)` | method | deployment id | removed row (dict as stored) or `None` | never raises | [RDEPLOY-053]..[RDEPLOY-056] |
| `Router.deployment_is_active_for_environment(deployment)` | method | `Deployment` | bool | `ValueError` on bad env config | [RDEPLOY-014] |
| `Router.config_deployments()` | generator | none | rows without truthy `model_info.db_model` | none | [RDEPLOY-077] |
| `Router.auto_router_capability_violation(capability)` | method | gated capability | message or `None` | none | [RDEPLOY-076] |
| `Router.init_auto_router_deployment`, `init_complexity_router_deployment`, `init_quality_router_deployment`, `init_adaptive_router_deployment` | methods | `Deployment` | none | `ValueError` | [RDEPLOY-060]..[RDEPLOY-075] |
| `Router.replay_model_cost_registrations()` (alias `_replay_model_cost_registrations`, bound at router.py:11204) | method | none | none | never raises per row | [RDEPLOY-085], [RDEPLOY-086] |
| `Router.get_router_deployment_budget_limiter()` (alias `_get_router_deployment_budget_limiter`, router.py:11264) | method | none | `RouterBudgetLimiting` or `None` | none | [RDEPLOY-090] |
| `Router.get_deployment(model_id)` | method | id | `Deployment` or `None` | `Exception("Model invalid format - <type>")` | [RDEPLOY-095] |
| `Router.get_deployment_by_model_group_name(model_group_name)` | method | name | first `Deployment` or `None` | `Exception("Model Name invalid - <type>")` | [RDEPLOY-096] |
| `Router.get_deployment_credentials(model_id)` | method | id | credential dict or `None` | none | [RDEPLOY-097] |
| `Router.deployment_usable_by_team(model, team_id)` (static; alias `_deployment_usable_by_team`, router.py:11358) | static method | row or `Deployment`, team id | bool | none | [RDEPLOY-098] |
| `Router.get_credential_deployment(model_id, team_id=None)` | method | id or name | `Deployment` or `None` | none | [RDEPLOY-099], [RDEPLOY-100] |
| `Router.get_deployment_credentials_with_provider(model_id, team_id=None)` | method | id or name | credential dict with `model`, `custom_llm_provider` | none | [RDEPLOY-101]..[RDEPLOY-103] |
| `Router.arefresh_model_info(client=None)` | async method | optional HTTP handler | none | never raises | [RDEPLOY-105]..[RDEPLOY-109] |
| `Router.get_discovered_model_info(model_id)` | method | id | read-only mapping of limits | none | [RDEPLOY-110] |
| `Router.get_model_listing_info(model_name)` | method | name | `DeploymentModelListingInfo` or `None` | none | [RDEPLOY-112], [RDEPLOY-113] |
| `Router.get_configured_token_limits(model_name)` | method | name | `(max_input, max_output)` | none | [RDEPLOY-114], [RDEPLOY-212] |
| `Router.get_configured_mode(model_name)` / `get_configured_display_name(model_name)` | methods | name | str or `None` | none | [RDEPLOY-115] |
| `Router.routable_model_group(model_name)` | method | name | group name | none | [RDEPLOY-116] |
| `Router.get_configured_service_tiers(model_name, team_id=None)` | method | name, team | tuple of raw values | none | [RDEPLOY-117], [RDEPLOY-118] |
| `Router.get_routable_upstream_model(model_name, team_id=None)` | method | name, team | `litellm_params.model` or `None` | none | [RDEPLOY-119] |
| `Router.get_router_model_info(deployment, received_model_name, id=None)` | method | row/`Deployment` or id | merged model-info dict | `ValueError("Deployment not found")`, `ValueError("Deployment missing valid litellm_params. ...")`, unmapped-model exception | [RDEPLOY-120]..[RDEPLOY-125] |
| `Router.get_model_info(id)` | method | id | stored row (same object) or `None` | none | [RDEPLOY-126] |
| `Router.get_model_group(id)` | method | id | `get_model_list(model_name)` of its group or `None` | none | [RDEPLOY-127] |
| `Router.get_deployment_model_info(model_id, model_name)` | method | id, litellm model name | `ModelInfo` dict or `None` | never raises | [RDEPLOY-128]..[RDEPLOY-130] |
| `Router.get_model_group_info(model_group, include_hidden=False)` | method | group or alias | `ModelGroupInfo` or `None` | none | [RDEPLOY-131]..[RDEPLOY-142] |
| `Router.cached_model_group_info(model_group)` | method | group | cached `ModelGroupInfo` | none | [RDEPLOY-143] |
| `Router.get_model_group_usage(model_group)` | async method | group | `(tpm, rpm)` this minute | none | [RDEPLOY-144] |
| `Router.get_model_group_io_token_usage(model_group)` | async method | group | `(itpm, otpm)` this minute | none | [RDEPLOY-145] |
| `Router.get_remaining_model_group_usage(model_group)` | async method | group | header dict | none | [RDEPLOY-146] |
| `Router.set_response_headers(response, model_group=None, request_kwargs=None)` | async method | response | the response (possibly wrapped) | none | [RDEPLOY-147], [RDEPLOY-148] |
| `Router.get_model_ids(model_name=None, exclude_team_models=False)` | method | name | list of ids | none | [RDEPLOY-059] |
| `Router.get_candidate_model_ids_for_route(model, team_id=None)` | method | name | frozenset of ids | none | [RDEPLOY-155], [RDEPLOY-156] |
| `Router.has_model_id(candidate_id)` | method | id | bool | none | [RDEPLOY-157] |
| `Router.resolve_model_name_from_model_id(model_id, custom_llm_provider=None)` | method | id/name | model name or `None` | none | [RDEPLOY-158] |
| `Router.resolve_served_model_name(model_name, served_model)` | method | names | name | none | [RDEPLOY-159] |
| `Router.map_team_model(team_model_name, team_id, custom_llm_provider=None)` | method | name, team | name, deployment id or `None` | none | [RDEPLOY-160], [RDEPLOY-161] |
| `Router.should_include_deployment(model_name, model, team_id=None)` | method | name, row | bool | none | [RDEPLOY-162] |
| `Router.get_all_deployments(model_name, model_alias=None, team_id=None)` (alias `_get_all_deployments`, router.py:12927) | method | name | list of rows | none | [RDEPLOY-163], [RDEPLOY-164] |
| `Router.get_model_names(team_id=None)` | method | team | list of names (may repeat) | none | [RDEPLOY-165] |
| `Router.get_fully_blocked_model_names()` | method | none | set of names | none | [RDEPLOY-166] |
| `Router.are_all_deployments_blocked(deployments)` (static; alias `_are_all_deployments_blocked`, router.py:12979) | static method | rows | bool | none | [RDEPLOY-167] |
| `Router.async_get_fully_unhealthy_model_names()` | async method | none | set of names | none | [RDEPLOY-168] |
| `Router.get_model_list_from_model_alias(model_name=None)` | method | alias | rows renamed to alias | none | [RDEPLOY-170] |
| `Router.get_model_list_from_routing_groups(model_name=None)` | method | group | rows renamed to group | none | [RDEPLOY-171], [RDEPLOY-172] |
| `Router.TIER_PARAMS_NEVER_DROPPED` | class constant (frozenset) | none | names | none | [RDEPLOY-175] |

## Behaviors

### Loading a model list (`set_model_list`)
- [RDEPLOY-001] {confirmed} `litellm/router.py:10552-10553`, `litellm/router.py:10593-10602` `set_model_list` works on a deep copy of the caller's list. It pops `model_name`, `litellm_params` and `model_info` from the copy, so the caller's list and dicts are never mutated.
- [RDEPLOY-002] {confirmed} `litellm/router.py:10554-10568` Before any row is processed, `set_model_list` resets the following and invalidates the model-group-info and access-group caches:
  - the discovered-limits cache;
  - `model_list`, the id index, the name index and the team index;
  - `team_pattern_routers` and `team_public_model_names`;
  - `quality_routers`, `complexity_routers` and `auto_routers`;
  - the provider-unresolved retry list.
- [RDEPLOY-003] {confirmed} `litellm/router.py:10552-10568`, `litellm/router.py:10693`, `litellm/router.py:10713-10718` `set_model_list` does not reset `adaptive_routers`, the proxy-wide wildcard `pattern_router`, `provider_default_deployment_ids` or `deployment_names`. A second call therefore keeps the previous list's wildcard deployments in `pattern_router`, appends re-listed wildcard deployments to it again as duplicates, and keeps the earlier entries of the other two lists, so a request matching a wildcard that the new list dropped is still routed to, and served by, the dropped deployment.
- [RDEPLOY-004] {confirmed} `litellm/router.py:10571-10576` Any `model_info.id` declared (not `None`) on more than one input row is collected into a duplicate-id set. Ids are compared after string conversion, so `12345` and `"12345"` collide, and so do `0` and `"0"`. The set is consulted only by the PTU identity rule ([RDEPLOY-015]).
- [RDEPLOY-005] {confirmed} `litellm/router.py:10578-10591` When PTU cost attribution is disabled and at least one config-sourced row declares PTU fields, `set_model_list` logs one warning naming every such row. A row is config-sourced when `model_info.db_model` is not `True`. The row names are joined with `, ` in list order, and the variable named is always `LITELLM_ENABLE_PTU_COST_ATTRIBUTION`, so two rows `gpt-ptu` and `gpt-ptu-2` render as `PTU fields are set on config.yaml deployment(s) gpt-ptu, gpt-ptu-2, but PTU cost attribution is disabled, so no flat cost accrues and this traffic is billed per token. Set LITELLM_ENABLE_PTU_COST_ATTRIBUTION=True to enable it`.
- [RDEPLOY-006] {confirmed} `litellm/router.py:10596-10600` Each top-level string value in `litellm_params` that starts with `os.environ/` is replaced by `get_secret(value)` before the deployment is built, with one exception: a field for which `holds_secret_pointer(key)` is true, meaning a `*_ref` workload-identity pointer field, is left as written. Nested values are not expanded.
- [RDEPLOY-007] {confirmed} `litellm/router.py:10604-10609`, `litellm/router.py::generate_model_id` When `model_info` has no `id` key, the id is `generate_model_id(model_name, litellm_params)`. That is the SHA-256 hex digest of the model name concatenated with every key and value of the already env-expanded `litellm_params`, so the same config yields the same id across restarts.
- [RDEPLOY-008] {inferred} `litellm/router.py:10604-10609`, `litellm/types/router.py:317-322` When `model_info` contains `id: null`, no id is derived. `ModelInfo` then assigns a random UUID4 string, which differs on every load. An integer id is stored as its decimal string. This is inferred from the `ModelInfo` constructor, which is out of scope.
- [RDEPLOY-009] {confirmed} `litellm/router.py:10611-10623` When `litellm_params.organization` is a list, one deployment is created per organization, each with `organization` set to that single value. All of them share the one id computed before the loop, so they are indexed under a single id and the id index points at the last one.
- [RDEPLOY-010] {confirmed} `litellm/router.py:10635` After loading, `model_names` is set to every `model_name` in the caller's input list. That includes rows dropped as invalid or as inactive for the current environment, so `model_names` can contain names that have no stored deployment.
- [RDEPLOY-011] {confirmed} `litellm/router.py:10642` After all rows are created, `set_model_list` runs the deferred adaptive-router pass ([RDEPLOY-072]). Adaptive routers therefore see every other deployment of the list regardless of row order.
- [RDEPLOY-012] {inferred} `litellm/router.py:1404-1409` Only a router constructed with a non-`None` `model_list` runs `set_model_list` at construction ([RSETUP-022]) and joins the live-router set used for price-reload replay ([RSETUP-023]), so a router built with no list and filled by `add_deployment` is never replayed.

### Building one row (`_create_deployment`)
Checks run in this order; the first failure raises:

| Claim | Step | Applies to | Outcome on failure |
|---|---|---|---|
| [RDEPLOY-015] | PTU identity and config check | config-sourced rows | `ValueError(<ptu message>)` only when the row declares `ptu_shares` or PTU attribution is enabled |
| [RDEPLOY-016] | access-window config check | every row | `ValueError(<access window message>)` |
| [RDEPLOY-017] | `LiteLLM_Params` validation (after PTU zeroing) | every row | pydantic `ValidationError` |
| [RDEPLOY-021] | environment gate | rows with `supported_environments` | returns `None` (not an error) or `ValueError` on bad env config |
| [RDEPLOY-022] | `tag_regex` compile | rows with `tag_regex` | `ValueError("Invalid regex in tag_regex for model '<name>': <pattern repr> — <re error>")` |
| [RDEPLOY-024] | provider validation | non-prompt-management rows | resolved but unsupported provider: `Exception("Unsupported provider - notaprovider")`; unresolvable provider: the resolver's `litellm.BadRequestError` |

- [RDEPLOY-013] {confirmed} `litellm/router.py:9964-9965` A row is *config-sourced* unless `model_info.db_model is True`. Only config-sourced rows get the PTU identity rule and PTU price zeroing.
- [RDEPLOY-014] {confirmed} `litellm/router.py:10537-10550`, `litellm/router.py:478-512` `deployment_is_active_for_environment` decides environment activity by a fixed sequence of checks:
  1. A deployment whose `model_info` is missing, or lacks `supported_environments`, is active.
  2. If `supported_environments` is not a list or tuple, a `ValueError` is raised.
  3. If the `LITELLM_ENVIRONMENT` secret is unset, the error is `Set 'supported_environments' for model but not 'LITELLM_ENVIRONMENT' set in .env`.
  4. If `LITELLM_ENVIRONMENT` is not one of `development`, `staging` or `production`, a `ValueError` is raised.
  5. If a listed environment is invalid, a `ValueError` is raised.
  6. Otherwise the deployment is active exactly when `LITELLM_ENVIRONMENT` is in the list.
- [RDEPLOY-015] {confirmed} `litellm/router.py:9966-9981`, `litellm/litellm_core_utils/ptu_pricing.py:122-156` For a config-sourced row, a PTU error is the row's PTU config error when it has one, else its identity error, so a config error wins over an identity error. The identity error applies only to a row with PTU terms, in two cases: the row declares no id, or an empty one (reason starts `model_info.id is required when PTU fields are set.`), or its declared id is in the duplicate set (reason starts `model_info.id '<id>' is declared on more than one deployment.`). A PTU error raises `ValueError` only when the row declares `ptu_shares` or `LITELLM_ENABLE_PTU_COST_ATTRIBUTION` is enabled. The message is the model name in single quotes and the reason, rendered as in `PTU configuration on model 'gpt-ptu' is invalid: model_info.id 'ptu-1' is declared on more than one deployment. Each would key the same flat-cost row, so one reservation would go unbilled`.
- [RDEPLOY-016] {confirmed} `litellm/router.py:9982-9984` A row with an invalid access-window configuration raises `ValueError` with the message from `access_windows_config_error`. This applies to database rows as well.
- [RDEPLOY-017] {confirmed} `litellm/router.py:9985-10004` While PTU cost attribution is enabled, a capacity warning from `ptu_capacity_warning` is logged at warning level when one applies. For a config-sourced row that has PTU terms while attribution is enabled, zeroed PTU prices are merged over the raw `litellm_params` before `LiteLLM_Params` validation. The row then stores `input_cost_per_token`, `output_cost_per_token` and any other rate it declares as `0.0`. The zeroed values come from `zeroed_ptu_pricing`. With the flag off, or for a database row, nothing is zeroed.
- [RDEPLOY-018] {confirmed} `litellm/router.py:10005-10015` Two warnings are logged but never block the row: one for provider credentials that do not match the resolved provider, one for model-capability flags placed under `litellm_params`. Capability flags under `litellm_params` are then removed from the stored deployment and never sent to the provider.
- [RDEPLOY-019] {confirmed} `litellm/router.py:10016-10018` Every custom-pricing field (`CustomPricingLiteLLMParams` fields) set on `litellm_params` is copied into the row's `model_info`, overwriting a `model_info` value of the same name.
- [RDEPLOY-020] {confirmed} `litellm/router.py:10020-10048` After the pricing copy, missing prices are inherited from the backend model's built-in entry in this order: off-peak base rates ([RDEPLOY-028]), cache prices (only when `input_cost_per_token` is not `None`, so an explicit `0.0` counts as set), service-tier prices (skipped when both `input_cost_per_token` and `output_cost_per_token` are `None`), and the tiered output rate ([RDEPLOY-030]). A worked example is [RDEPLOY-213]. The result is then registered in `litellm.model_cost` ([RDEPLOY-080]). All of this happens before the environment gate and before the tag-regex and provider checks, so a row that later fails or is environment-inactive still leaves cost-map entries until the next replay ([RDEPLOY-085]).
- [RDEPLOY-021] {confirmed} `litellm/router.py:10050-10057` A row that is not active for the current environment is skipped. The method returns `None` and logs a warning with the model name and the `supported_environments` list as a Python list repr, rendered as in `Ignoring deployment m as it is not active for environment ['production', 'staging']`.
- [RDEPLOY-022] {confirmed} `litellm/router.py:10059-10068` Every `tag_regex` pattern is compiled before the row touches router state. The first invalid one raises `ValueError("Invalid regex in tag_regex for model '<model_name>': <pattern repr> — <error>")`, with the regex error as cause. For example, pattern `[` on model `m` renders as `Invalid regex in tag_regex for model 'm': '[' — unterminated character set at position 0`.
- [RDEPLOY-023] {confirmed} `litellm/router.py:10070-10075` A row that passes every check is registered ([RDEPLOY-024]..[RDEPLOY-027]). It is then appended to `model_list` as the deployment's JSON form with `None` fields omitted, and indexed ([RDEPLOY-057]).
- [RDEPLOY-024] {confirmed} `litellm/router.py:10656-10690` Registration skips provider validation when the model contains `/` and its first path segment is a known custom-logger-compatible callback name (for example `langfuse/my-prompt`); such a row is a prompt-management model and its provider is left unset. Every other row resolves its provider with `get_llm_provider`, and one of two errors rejects it before `deployment_names`, the wildcard pattern routers or `model_list` change:
  - When the resolver returns a provider that is in none of `litellm.provider_list`, the JSON provider registry or the registered custom providers, registration raises a plain `Exception` whose message is `Unsupported provider - ` followed by the provider, rendered as in `Unsupported provider - notaprovider`. The resolver returns an explicit `custom_llm_provider` unchanged, so model `foo` with `custom_llm_provider: notaprovider` takes this path.
  - When no provider can be resolved from the model and no `custom_llm_provider` is given (for example model `foo`, or `notaprovider/foo` whose prefix is not a provider), the resolver itself raises `litellm.BadRequestError`, whose text begins `litellm.BadRequestError: LLM Provider NOT provided. Pass in the LLM provider you are trying to call. You passed model=foo`, and that error propagates unchanged.

  Only the second kind is queued for retry by the model-list path ([RDEPLOY-033]).
- [RDEPLOY-025] {confirmed} `litellm/router.py:10650-10655`, `litellm/router.py:10693-10701` Registration does four bookkeeping steps:
  1. It logs a warning when `drop_params` is still a string after parameter validation, which converts flag-like strings such as `true`, `yes`, `1` and `off` to booleans first. The value renders as its repr, as in `model=m drop_params='maybe' is not a flag value, treating it as unset`.
  2. It appends `litellm_params.model` to `deployment_names`. This happens after provider validation, so a provider rejection leaves no entry.
  3. It copies a top-level `rpm` into `litellm_params.rpm` when the latter is unset.
  4. It does the same for `tpm`.
- [RDEPLOY-026] {confirmed} `litellm/router.py:10713-10727` A deployment whose `model_name` contains `*` is added to the proxy-wide wildcard `pattern_router`, and its id is appended to `provider_default_deployment_ids`. A deployment with `model_info.team_id` and a `team_public_model_name` containing `*` is added to that team's own pattern router, which is created on first use.
- [RDEPLOY-027] {confirmed} `litellm/router.py:10729-10738` For each entry in `litellm_params.dataSources`, an `endpoint` or `key` parameter that starts with `os.environ/` is replaced by that environment variable's value read directly from the process environment. A missing variable becomes the empty string. This expansion does not go through `get_secret`.
- [RDEPLOY-031] {confirmed} `litellm/router.py:10745-10771` After the wildcard bookkeeping, a row whose provider resolved is offered for pass-through registration ([RDEPLOY-032]). The row is then classified by its `litellm_params.model` ([RDEPLOY-060]), and the matching semantic, complexity or quality router is built immediately. Adaptive routers are deferred to [RDEPLOY-072].
- [RDEPLOY-032] {confirmed} `litellm/router.py:10775-10818` Pass-through registration acts only when `use_in_pass_through is True` and the provider is `vertex_ai`. Project, location and credentials are taken from the named credential (`litellm_credential_name`) first, then from `litellm_params`. A missing project or location raises `ValueError("vertex_project, and vertex_location must be set in litellm_params for pass-through endpoints.")`, and the values are registered with the proxy's pass-through endpoint router. Other providers are not registered.
- [RDEPLOY-033] {confirmed} `litellm/router.py:10076-10096` When any step raises and `ignore_invalid_deployments` is true, the error is logged at error level with traceback, the error's text rendered in place, as in `Error creating deployment: Unsupported provider - notaprovider, ignoring and continuing with other deployments.`, and the row is dropped (`None`). If the error is a `litellm.BadRequestError`, which is the unresolvable-provider failure of [RDEPLOY-024], the row's creation is also queued for retry on the next price reload ([RDEPLOY-085]). Every other error, including the plain `Unsupported provider - ...` exception, is not queued and is never retried. When `ignore_invalid_deployments` is false the error propagates, and router construction fails.
- [RDEPLOY-034] {confirmed} `litellm/router.py:10076-10096`, `litellm/router.py:10693`, `litellm/router.py:10713-10727` A failure raised after registration started is not rolled back. Strategy-router initialization is one example. The row has already been appended to `deployment_names` and may already sit in a wildcard pattern router, while it never reaches `model_list`.

### Price inheritance helpers
- [RDEPLOY-028] {confirmed} `litellm/router.py:9893-9910` Off-peak inheritance has two preconditions:
  - `model_info.off_peak_pricing` is truthy;
  - none of `input_cost_per_token`, `input_cost_per_second`, `cost_per_second` or `tiered_pricing` is set.

  When both hold, every field of the backend model's raw `litellm.model_cost` entry that is missing or `None` on the deployment is deep-copied in, field by field. The entry is located through `get_model_info(...)["key"]`. Fields the user set are never overwritten.
- [RDEPLOY-029] {confirmed} `litellm/router.py:9900-9906` Off-peak inheritance is a silent no-op in two cases: `get_model_info` raises for the backend model (an unmapped model), or the raw cost-map entry is not a dict. It copies from the raw entry rather than the `get_model_info` view, so a tiered-only backend never gets a synthesized zero flat rate.
- [RDEPLOY-030] {confirmed} `litellm/router.py:9930-9943` Tiered output-rate inheritance applies only when all three conditions hold:
  - `tiered_pricing` is a non-empty list;
  - `output_cost_per_token` is unset;
  - at least one tier lacks an `output_cost_per_token`.

  It then sets `output_cost_per_token` to the backend model's flat output rate. It does nothing when that rate is missing or zero, or when the backend is unmapped.
- [RDEPLOY-035] {inferred} `litellm/router.py:9803-9864` The other two inheritance steps live outside this module's range:
  - Cache-price inheritance fills five cache-price fields from the backend's built-in info. The fields are `cache_creation_input_token_cost`, `..._above_1hr`, `..._above_200k_tokens`, `cache_read_input_token_cost` and `cache_read_input_token_cost_above_200k_tokens`. Only a field that is missing or `None` on the deployment is filled, and only from a non-`None` built-in value.
  - Service-tier inheritance fills missing `*_<tier>` rates from the backend chosen by `base_model` precedence. It is skipped when the deployment has neither base rate, meaning both `input_cost_per_token` and `output_cost_per_token` are `None` (a `0.0` rate counts as present), or when it has PTU terms while attribution is enabled.

  This is inferred from range router.py:9762-9864, which is owned by `router-dispatch` ([RDISP-244]-[RDISP-247]).

### Adding one deployment at runtime (`add_deployment`)
- [RDEPLOY-040] {confirmed} `litellm/router.py:10831-10833` `add_deployment` returns `None` and changes nothing when the deployment's id is truthy and already indexed. It never updates an existing deployment.
- [RDEPLOY-041] {confirmed} `litellm/router.py:10835-10851` Otherwise `add_deployment` runs these steps in order and returns the stored `Deployment`:
  1. Log the credential-mismatch and capability-flag warnings.
  2. Strip capability flags from `litellm_params`.
  3. Register the deployment ([RDEPLOY-024]..[RDEPLOY-032]).
  4. Register its pricing in `litellm.model_cost` ([RDEPLOY-083]).
  5. Append it to `model_list` and indexes, and add its name to `model_names`.
  6. Sync its budget configuration ([RDEPLOY-092]).

  The returned object has the capability flags removed.
- [RDEPLOY-042] {confirmed} `litellm/router.py:10820-10851` `add_deployment` does not apply several of the checks and transforms of the model-list path. Missing are:
  - the PTU identity and config checks and PTU price zeroing;
  - the access-window check;
  - the environment gate (`supported_environments`);
  - `tag_regex` validation;
  - `os.environ/` expansion;
  - organization-list expansion.
- [RDEPLOY-043] {confirmed} `litellm/router.py:10820-10851`, `litellm/router_strategy/budget_limiter.py:113-126` `add_deployment` has no error handling. Any registration error propagates whatever `ignore_invalid_deployments` is set to. Examples are the plain `Exception` rendered as `Unsupported provider - notaprovider`, the resolver's `litellm.BadRequestError` for an unresolvable provider ([RDEPLOY-024]), and the strategy-router `ValueError`s. Nothing is queued for retry on this path. The budget sync (step 6 of [RDEPLOY-041]) runs after the row is appended and indexed, so an error it raises leaves the deployment stored and routable although the call raised. One such error is the `RuntimeError` with text `no running event loop`, raised when the first budget limiter is created outside a running event loop.
- [RDEPLOY-044] {confirmed} `litellm/router.py:10658-10716` When provider validation fails in `add_deployment`, it fails before any router state changes, so `pattern_router` is untouched by a rejected wildcard deployment.
- [RDEPLOY-045] {inferred} `litellm/router.py:10831-10833`, `litellm/types/router.py:317-322` A `Deployment` built without an id gets a random UUID4 id from `ModelInfo`, so the duplicate check never fires for it. Each call adds a new deployment. This is inferred from the `ModelInfo` constructor, which is out of scope.

### Upserting (`upsert_deployment`)
- [RDEPLOY-046] {confirmed} `litellm/router.py:10979-10991` `upsert_deployment` returns `None` without changes when a deployment with the same id exists and three things match the stored one: `model_name`, `litellm_params` after capability flags are stripped, and `model_info`.
- [RDEPLOY-047] {confirmed} `litellm/router.py:10993-11013` When the id exists but anything differs, the stored row is first removed. That means popping it from `model_list`, invalidating caches, repairing indexes ([RDEPLOY-058]) and releasing the old row's strategy-router slots ([RDEPLOY-071]). The new deployment is then added through `add_deployment` and goes to the end of `model_list`. When the id does not exist, the deployment is simply added.
- [RDEPLOY-048] {confirmed} `litellm/router.py:11014-11025` After the add, the deferred adaptive pass ([RDEPLOY-072]) is re-run if either the new or the replaced deployment takes part in adaptive routing. Taking part means an `auto_router/adaptive_router...` model, or a complexity router whose `complexity_router_config.adaptive` is truthy. The method then returns the input deployment object, which is not the flag-stripped stored copy.
- [RDEPLOY-049] {confirmed} `litellm/router.py:10979-10982`, `litellm/router.py:11014-11037`, `litellm/router.py:11048-11049`, `litellm/router.py:10848-10850`, `litellm/router_strategy/budget_limiter.py:113-126` The id lookup and capability-flag stripping run before `upsert_deployment`'s guarded section, so an error there propagates whatever `ignore_invalid_deployments` is set to. When the guarded section raises and `ignore_invalid_deployments` is true, the method logs a warning, attempts the restore of [RDEPLOY-050] and returns `None`. The warning names the incoming deployment's `model_name`, its id and the error's text, rendered as in `Error upserting deployment m2 (id=d2): Unsupported provider - notaprovider. Dropping it and continuing with other deployments.`; an error text that ends in `.` renders as `..` before `Dropping`. What is stored afterwards depends on where the failure happened:
  - Before `add_deployment` appended the new row, for example provider validation, strategy-router initialization at registration or pricing registration: nothing of the new deployment is stored. The previous deployment is re-added at the end of `model_list`, and the info line `Restored deployment m (id=d2); it keeps serving its previous configuration.` follows.
  - After the append, that is the budget sync ([RDEPLOY-092]) or the deferred adaptive pass ([RDEPLOY-048]): the new row stays stored under the id, in `model_list` and every index. The restore is skipped because the id is present again, so the previous deployment is gone even though the warning says `Dropping it`. The same holds for an id that was new: the failed row stays.

  Example of the second case: id `d2`, previously model `m` on `openai/gpt-4o`, is upserted as `m3` with model `auto_router/adaptive_router` and no `adaptive_router_config`. The warning reads `Error upserting deployment m3 (id=d2): adaptive_router_config is required for adaptive-router deployments.. Dropping it and continuing with other deployments.`, no restore line follows, and the method returns `None`. Afterwards `model_list` holds only the `m3` row, `get_deployment("d2").model_name` is `m3` and `adaptive_routers` is empty. The budget sync fails after the append when it must create the first budget limiter outside a running event loop, raising `RuntimeError` with text `no running event loop`.
- [RDEPLOY-050] {confirmed} `litellm/router.py:11041-11067` Restore after a failed upsert works as follows:
  - It does nothing if there was no previous deployment, or if the id is already present again.
  - Otherwise it re-adds the previous deployment through `add_deployment`, with the auto-router capability limit resolver temporarily set to `None`, meaning unlimited. The resolver is put back afterwards even on error.
  - On success it logs at info level, with the previous deployment's `model_name`, for example `Restored deployment m (id=d2); it keeps serving its previous configuration.`
  - On a second failure it logs a warning such as `Could not restore previously served deployment m (id=d2) after the failed upsert: Unsupported provider - notaprovider` (the second error's text) and swallows that error.
  - The restored row is appended at the end of `model_list`.
- [RDEPLOY-051] {confirmed} `litellm/router.py:11003-11025`, `litellm/router.py:11038-11039` When `ignore_invalid_deployments` is false and the re-add fails, the original error propagates unchanged and the old row is not restored. What remains depends on where the failure happened ([RDEPLOY-049]):
  - Before the new row was appended, the deployment is absent from the router. For example, an upsert of id `d2` with `custom_llm_provider: notaprovider` raises the plain `Exception("Unsupported provider - notaprovider")`; afterwards `get_deployment("d2")` returns `None`, and the name leaves `model_names` when it was the last deployment of that name ([RDEPLOY-058]).
  - After the append, the failed new row stays stored. For example, an upsert of id `d2` as `m3` with model `auto_router/adaptive_router` and no `adaptive_router_config` raises `ValueError("adaptive_router_config is required for adaptive-router deployments.")`, and `get_deployment("d2").model_name` is then `m3`.
- [RDEPLOY-052] {confirmed} `litellm/router.py:10850`, `litellm/router.py:11273-11290` Because an upsert re-adds through `add_deployment`, it re-syncs the deployment budget. An upsert that drops `max_budget` or `budget_duration` unregisters the id from the deployment budget limiter.

### Deleting (`delete_deployment`)
- [RDEPLOY-053] {confirmed} `litellm/router.py:11215-11241` `delete_deployment(id)` returns `None` when the id is not indexed. Otherwise it does five things and returns the removed `model_list` entry as stored, normally a plain dict:
  1. Pop the entry.
  2. Invalidate the group-info and access-group caches.
  3. Repair indexes ([RDEPLOY-058]).
  4. Unregister the id from the deployment budget limiter, when one exists.
  5. Release the row's strategy-router slots ([RDEPLOY-071]).
- [RDEPLOY-054] {confirmed} `litellm/router.py:11229-11238` A failure while releasing strategy slots is logged at error level with traceback, with the deleted id rendered as in `delete_deployment: could not release pre-routing strategies for model_id=d1; the deployment is out of the model_list and its indices are repaired`. The deletion still returns the removed row.
- [RDEPLOY-055] {confirmed} `litellm/router.py:11242-11243` Any other exception during deletion is swallowed silently and `None` is returned, even if the row was already popped.
- [RDEPLOY-056] {confirmed} `litellm/router.py:11206-11243` Deletion does not touch `litellm.model_cost`, `deployment_names` or `provider_default_deployment_ids`. Cost-map entries of a deleted deployment disappear only at the next price-reload replay, which walks the live `model_list` ([RDEPLOY-085]).

### Indexes
- [RDEPLOY-057] {confirmed} `litellm/router.py:10941-10968`, `litellm/router.py:10923-10939` Appending a row does four things:
  1. It invalidates the group-info and access-group caches.
  2. It maps the id (the explicit argument, else `model_info.id`) to the new position. A repeated id overwrites the old mapping, so the last row wins, and the older row stays in `model_list`.
  3. It appends the position under `model_name`.
  4. When both `team_id` and `team_public_model_name` are truthy, it appends the position under `(team_id, team_public_model_name)` and adds that public name to `team_public_model_names`.
- [RDEPLOY-058] {confirmed} `litellm/router.py:10853-10921` Removing the row at position `i` repairs every index:
  - It deletes the id's discovered limits.
  - It decrements every id, name and team position greater than `i`.
  - It drops the removed position.
  - It removes a name entry that becomes empty, and also discards that name from `model_names`.
  - It removes an empty team entry.
  - It recomputes `team_public_model_names`.
  - It removes the id from the proxy-wide and every team pattern router, deleting team pattern routers left with no patterns.
- [RDEPLOY-059] {confirmed} `litellm/router.py:12534-12566` `get_model_ids(model_name, exclude_team_models)` has two paths, and `exclude_team_models=True` applies on both, skipping every row whose `model_info.team_id` is truthy:
  - With a name, it returns each `model_info.id` of the rows indexed under that exact name, in position order. Rows whose `model_info` has no `id` key are skipped, two rows sharing one id yield that id twice, and an unknown name yields `[]`.
  - Without a name, it returns every key of the id index in index insertion order, each id once.

  For example, with a shared deployment `s1` and team deployments `t1` (team `team1`) and `t2` (team `team2`), `get_model_ids()` returns `['s1', 't1', 't2']` and `get_model_ids(exclude_team_models=True)` returns `['s1']`.

### Strategy-router deployments
| Claim | `litellm_params.model` | Kind | Built by |
|---|---|---|---|
| [RDEPLOY-060] | not starting with `auto_router/` | none (regular deployment) | none |
| [RDEPLOY-060] | `auto_router/complexity_router...` | complexity | `init_complexity_router_deployment`, at registration |
| [RDEPLOY-060] | `auto_router/adaptive_router...` | adaptive | deferred pass [RDEPLOY-072] |
| [RDEPLOY-060] | `auto_router/quality_router...` | quality | `init_quality_router_deployment`, at registration |
| [RDEPLOY-060] | any other `auto_router/...` | semantic auto-router | `init_auto_router_deployment`, at registration |

- [RDEPLOY-060] {confirmed} `litellm/router.py:10098-10106`, `litellm/router.py:10158-10164`, `litellm/router.py:10241-10243`, `litellm/router.py:10490-10496`, `litellm/router_utils/auto_router_model_naming.py:70-86` Deployments are classified by `litellm_params.model` as in the table above. The prefixes after `auto_router/` are matched with prefix comparison, so `auto_router/quality_router/my-router` is a quality router. A model that merely contains `auto_router/` later in the string is regular.
- [RDEPLOY-061] {confirmed} `litellm/router.py:10260-10295` Each registry maps a `model_name` to a list of entries keyed by the deployment's `tags` tuple, so several routers may share a name if their tags differ. Registering a second router with the same name and tags raises a `ValueError` whose message starts with the registry label, then the name, then the tags as a Python list repr (`[]` when untagged), rendered as in `Quality-router deployment ar with tags ['a', 'b'] already exists. Please use a different model name or set different tags.` The labels are `Auto-router`, `Complexity-router`, `Adaptive-router` and `Quality-router`.
- [RDEPLOY-062] {confirmed} `litellm/router.py:10297-10310` Each registry entry records the deployment and a definition fingerprint. The fingerprint is the `generate_model_id` hash of the deployment name together with the sorted-key JSON of these fields, dropping `None` values:
  - `model` and `tags`;
  - the strategy-router fields `auto_router_config`, `auto_router_config_path`, `auto_router_default_model`, `auto_router_embedding_model` and `auto_router_max_input_chars`;
  - `complexity_router_config` and `complexity_router_default_model`;
  - `adaptive_router_config`;
  - `quality_router_config` and `quality_router_default_model`.

  The fingerprint is `None` when those fields are not JSON-serializable.
- [RDEPLOY-063] {confirmed} `litellm/router.py:10113-10138` `init_auto_router_deployment` validates its inputs in order. The first failure raises `ValueError`:
  1. A config is required. The message is `auto_router_config_path or auto_router_config is required for auto-router deployments. Please set it in the litellm_params`.
  2. A default model is required. The message is `auto_router_default_model is required for auto-router deployments. Please set it in the litellm_params`.
  3. An embedding model is required. The message is `auto_router_embedding_model is required for auto-router deployments. Please set it in the litellm_params`.
- [RDEPLOY-064] {confirmed} `litellm/router.py:10140-10156` A semantic auto-router is built with the following values and registered under `auto_routers`:
  - the deployment's `model_name`;
  - the config path or inline config;
  - the default and embedding models;
  - a back-reference to this router;
  - `max_input_chars` from `auto_router_max_input_chars`, defaulting to `2000` (`DEFAULT_AUTO_ROUTER_MAX_INPUT_CHARS`).
- [RDEPLOY-065] {confirmed} `litellm/router.py:10207-10210` `init_complexity_router_deployment` first checks every licensed capability the `complexity_router_config` claims against the capability ceiling ([RDEPLOY-076]). The first violation raises `ValueError` with the ceiling message.
- [RDEPLOY-066] {confirmed} `litellm/router.py:10212-10224` The complexity router's default model is resolved in one of two ways:
  - When `complexity_router_config` is non-empty, the default is resolved by the validated `ComplexityRouterConfig` from `complexity_router_default_model` and the config. An invalid config raises the config model's validation error.
  - Otherwise the default is `complexity_router_default_model` itself.

  When no default results, the error is `ValueError("complexity_router_default_model is required for complexity-router deployments, or configure tiers in complexity_router_config. Please set it in the litellm_params")`.
- [RDEPLOY-067] {confirmed} `litellm/router.py:10226-10239`, `litellm/router.py:2675-2696` The complexity router is registered under `complexity_routers`. When it pins deployments, the router then ensures a deployment-affinity check exists, looking only at this router's own `optional_callbacks`:
  - If that list already holds a `DeploymentAffinityCheck`, for example one created with flags on by `optional_pre_call_checks=["deployment_affinity"]`, nothing changes and no flags-off check is added.
  - Otherwise it creates a check with all three global affinity flags `False`, carrying this router's cache, `deployment_affinity_ttl_seconds`, `model_group_affinity_config` and routing-group priority test. It appends the check to `optional_callbacks` and offers it to the global `litellm.callbacks` list, which can decline it ([RDEPLOY-214]).
- [RDEPLOY-214] {confirmed} `litellm/litellm_core_utils/logging_callback_manager.py:57-66`, `litellm/litellm_core_utils/logging_callback_manager.py:297-337`, `litellm/router.py:9739-9748` The global list declines a new check when a custom logger with the same key is already in `litellm.callbacks`. The key is the class name plus every public string, integer or boolean attribute. For a default check it renders as `DeploymentAffinityCheck-message_logging=True-turn_off_message_logging=False-ttl_seconds=3600-enable_user_key_affinity=False-enable_responses_api_affinity=False-enable_session_id_affinity=False`. The cache, `model_group_affinity_config` and priority test are not part of the key. As a consequence:
  - When a second `Router` in the same process registers a pinning complexity router with the same `deployment_affinity_ttl_seconds`, its new check stays only in its own `optional_callbacks`.
  - The deployment filter iterates `litellm.callbacks`, so that router's requests are filtered by the first router's check, with the first router's cache, `model_group_affinity_config` and priority test.
  - A router with a different TTL gets its own global entry.
- [RDEPLOY-068] {confirmed} `litellm/router.py:10512-10535` `init_quality_router_deployment` takes its default model from `quality_router_default_model`, else from `quality_router_config["default_model"]`. With neither it raises `ValueError("quality_router_default_model is required for quality-router deployments, or set default_model in quality_router_config. Please configure it in the litellm_params")`. It registers under `quality_routers`.
- [RDEPLOY-069] {confirmed} `litellm/router.py:10439-10443` `init_adaptive_router_deployment` raises `ValueError("adaptive_router_config is required for adaptive-router deployments.")` when the config is absent. The config is parsed into `AdaptiveRouterConfig`, and an invalid config raises that model's validation error.
- [RDEPLOY-070] {confirmed} `litellm/router.py:10445-10488` For each name in `available_models`, the adaptive router reads only the first currently stored deployment of that name. Names with no stored deployment are skipped. From that deployment it reads two things:
  - preferences from `model_info.adaptive_router_preferences`;
  - cost from `litellm_params.input_cost_per_token`, else `model_info.input_cost_per_token`, as a float.

  It then does three things:
  1. Builds the router.
  2. Registers it under `adaptive_routers`.
  3. Adds an `AdaptiveRouterPostCallHook` to the global callback lists.

  Finally it logs at info level the deployment's `model_name` and the count of every name listed in `available_models`, including the skipped ones, rendered as in `AdaptiveRouter[smart] initialized with 2 models`.
- [RDEPLOY-071] {confirmed} `litellm/router.py:10312-10355` Releasing a removed deployment's strategy slots is a no-op unless its model starts with `auto_router/`. Otherwise it removes the exact `(model_name, tags)` entry from all four registries, auto, complexity, quality and adaptive, so a complexity router's adaptive companion is released too. Entries with other tags are left alone, and names with no remaining entries are deleted. The adaptive hooks are re-synced only when an adaptive entry was actually removed.
- [RDEPLOY-072] {confirmed} `litellm/router.py:10357-10398` The deferred adaptive pass runs in three steps:
  1. It builds an adaptive router for every stored `auto_router/adaptive_router...` row whose `(model_name, tags)` is not yet registered. Existing routers are kept with their learned state.
  2. For every registered complexity router whose config enables `adaptive`, it registers the router's companion adaptive router under the same name and tags, when one is not already registered and the companion is created.
  3. It re-syncs the adaptive hooks.
- [RDEPLOY-073] {confirmed} `litellm/router.py:10400-10414`, `litellm/router.py:10398` Re-syncing the adaptive hooks first removes every `AdaptiveRouterPostCallHook` from all global callback lists, including hooks registered by other `Router` instances in the process. It then adds one hook per adaptive router registered on this router. The deferred pass always ends with this re-sync, even when no adaptive routers are configured. So constructing any router from a model list removes the adaptive hooks of every other router.
- [RDEPLOY-074] {confirmed} `litellm/router.py:10552-10568`, `litellm/router.py:10375-10376` Because `adaptive_routers` survives `set_model_list`, an adaptive router whose row is dropped from a reloaded list stays registered with its hook.
- [RDEPLOY-075] {gap} `litellm/router.py:10563-10565` When `set_model_list` resets the semantic, complexity and quality registries, nothing shuts down the strategy objects it drops. Do those objects hold resources or callbacks, such as a complexity router's own hooks or caches, that outlive the reset?
- [RDEPLOY-076] {confirmed} `litellm/router.py:10175-10189`, `litellm/router_utils/auto_router_model_naming.py:345-357` `auto_router_capability_violation(capability)` works as follows:
  - It counts the stored `model_list` rows whose complexity config claims the capability, then adds 1 for the router being registered.
  - It compares that count with the limit returned by calling `auto_router_capability_limit()` on every check. The limit is never cached, and an unset resolver or a `None` result means unlimited.
  - It returns `None` when the count fits. Otherwise it returns a message built from the limit, the capability's subject phrase, the count and the capability's remedy sentence. For the `heuristic_v2` capability with limit 1 it renders as `At most 1 auto-router(s) using the heuristic_v2 classifier can be registered but this would make 2. Choose the heuristic v1 classifier for this router or remove an existing heuristic_v2 router.`

  Because an upsert pops the edited row first, an edit keeps its own slot.
- [RDEPLOY-077] {confirmed} `litellm/router.py:10166-10173` `config_deployments()` yields, in order, every `model_list` mapping whose `model_info` is not a mapping with a truthy `db_model`. These are the rows that came from config rather than the database.

### Price catalog registration (`litellm.model_cost`)
- [RDEPLOY-080] {confirmed} `litellm/router.py:11154-11161` A deployment's full `model_info` is registered under its unique id with `litellm.register_model`. The call is made with:
  - `persist_across_reloads=False`;
  - `warning_display_name` set to the backend model;
  - the deployment's `custom_llm_provider`;
  - `add_to_provider_model_sets=False`.

  Nothing is written under the id when it is `None`.
- [RDEPLOY-081] {confirmed} `litellm/router.py:11163-11176`, `litellm/router.py:11069-11075` The deployment also registers a filtered copy under each shared backend key (`persist_across_reloads=False`). The filter has two parts:
  - `shared_backend_model_info` keeps only cost-map schema fields. It drops per-deployment pricing overrides, `off_peak_pricing`, `id`, `access_via_team_ids` and custom keys.
  - `keep_registered_mode` prevents a deployment's `mode` pin from rewriting a routing mode already registered on the shared row.

  The backend keys are computed as follows:

| Claim | `model` | `custom_llm_provider` | Backend keys |
|---|---|---|---|
| [RDEPLOY-081] | `gpt-4o` | unset | `gpt-4o` |
| [RDEPLOY-081] | `gpt-4o` | `openai` | `openai/gpt-4o` |
| [RDEPLOY-081] | `openai/gpt-4o` | unset | `openai/gpt-4o` |
| [RDEPLOY-081] | `responses/gpt-4o` | `openai` | `openai/responses/gpt-4o`, `openai/gpt-4o` |
| [RDEPLOY-081] | `responses/gpt-4o` | unset | `responses/gpt-4o`, `gpt-4o` |

- [RDEPLOY-082] {confirmed} `litellm/router.py:11151-11152` When the deployment is a strategy router (an `auto_router/...` model), every custom-pricing field is removed before registration. The id entry keeps metadata such as `max_input_tokens` but never a price, so the alias cannot look like an explicitly free model.
- [RDEPLOY-083] {confirmed} `litellm/router.py:11077-11127` The registered payload for a `Deployment` is built in three steps:
  1. Take `model_info` with `None` values dropped.
  2. Add every custom-pricing field set on `litellm_params`.
  3. Apply the four inheritance steps of [RDEPLOY-020].

  So the payload can be rebuilt from the deployment alone. `_register_deployment_pricing` registers this payload for any deployment, including one never added to `model_list`, such as a per-request client-side-credential deployment.
- [RDEPLOY-084] {confirmed} `litellm/router.py:10042-10048`, `litellm/router.py:11086-11112` The model-list path registers the `model_info` dict as mutated during row creation. The add/upsert path registers a payload rebuilt from the stored `Deployment`. Both contain the same pricing fields.
- [RDEPLOY-213] {confirmed} `litellm/router.py:10016-10048`, `litellm/router.py:11150-11176`, `litellm/router.py:11931-11993`, `litellm/utils.py:3539-3553` Worked example of per-deployment price isolation. It uses the bundled catalog at this commit, where `gpt-4o` costs `2.5e-06` input, `1e-05` output and `1.25e-06` cache read per token. Two deployments share the backend model `openai/gpt-4o`: `cheap` (id `cheap-id`) sets `input_cost_per_token: 0.0` and `output_cost_per_token: 0.0` on `litellm_params` and `my_custom_meta: x` in `model_info`, while `std` (id `std-id`) sets no price. After loading:
  - `litellm.model_cost["cheap-id"]` holds `id`, `my_custom_meta`, both `0.0` prices, and built-in prices inherited because `0.0` counts as a set rate ([RDEPLOY-020]), such as `cache_read_input_token_cost` `1.25e-06` and `input_cost_per_token_priority` `4.25e-06`.
  - `litellm.model_cost["std-id"]` is exactly `{"id": "std-id"}`.
  - The shared backend registration ([RDEPLOY-081]) carries neither the `0.0` override, nor `my_custom_meta`, nor `id`. `litellm.register_model` writes it into the built-in entry it matches, here `gpt-4o`, whose prices stay `2.5e-06` and `1e-05`; no `openai/gpt-4o` key is created.
  - `get_deployment_model_info("cheap-id", "openai/gpt-4o")` reports `input_cost_per_token` `0.0`. `get_deployment_model_info("std-id", "openai/gpt-4o")` reports the built-in `2.5e-06` input and `1e-05` output, not `None`, because the built-in entry declares a price ([RDEPLOY-129], [RDEPLOY-130]).
- [RDEPLOY-085] {confirmed} `litellm/router.py:11178-11202` `replay_model_cost_registrations()` runs in four steps:
  1. It takes and clears the queued provider-unresolved row creations, and re-runs each one with the original arguments. A row whose provider now resolves joins `model_list`. A row that fails again is re-queued or dropped per [RDEPLOY-033].
  2. It re-registers the cost-map entries of every row currently in `model_list` ([RDEPLOY-080], [RDEPLOY-081], [RDEPLOY-083]).
  3. Rows that cannot be parsed as a `Deployment` are logged with traceback as `Router: could not rebuild cost-map entry for a deployment during a price data reload` and skipped.
  4. It invalidates the model-group-info caches.
- [RDEPLOY-086] {inferred} `litellm/router.py:1005-1015`, `litellm/router.py:1630-1637` After a price-catalog refresh, the hook registered with `set_live_deployment_replay` calls `replay_model_cost_registrations` on every router still in the module-level `_live_routers` WeakSet. Garbage-collected routers, and routers that called `discard()`, are skipped. Entries of deleted or repointed deployments are therefore not re-asserted on the new catalog. This is inferred from `router-setup` context ([RSETUP-023], [RSETUP-062], [RSETUP-255]); the effect is pinned by tests.

### Deployment budgets
- [RDEPLOY-090] {confirmed} `litellm/router.py:11245-11262` `get_router_deployment_budget_limiter()` returns the remembered limiter. If none is remembered, it takes the first `optional_callbacks` entry whose exact type is `RouterBudgetLimiting`, remembers it and returns it. Subclasses do not match. With no match it returns `None`.
- [RDEPLOY-091] {confirmed} `litellm/router.py:11266-11271` A deployment has budget limits only when three values are all set: `litellm_params.max_budget`, `litellm_params.budget_duration` and `model_info.id`.
- [RDEPLOY-092] {confirmed} `litellm/router.py:11273-11290` Budget sync does nothing for a deployment without an id. A deployment without limits is unregistered from an existing limiter. A deployment with limits causes the `router_budget_limiting` optional pre-call check to be enabled when no limiter exists yet, and is then registered with the limiter.
- [RDEPLOY-093] {confirmed} `litellm/router.py:10552-10642` `set_model_list` and `_create_deployment` never sync deployment budgets. Only `add_deployment`, and through it `upsert_deployment`, does.

### Deployment lookups and credentials
- [RDEPLOY-095] {confirmed} `litellm/router.py:11292-11309` `get_deployment(model_id)` resolves through the id index only. A stored dict is returned as a newly built `Deployment`, so mutating it does not change the stored row. A stored `Deployment` is returned as is. Any other stored type raises a plain `Exception` whose message ends with the stored value's type repr, rendered as in `Model invalid format - <class 'str'>`. An unknown id returns `None`.
- [RDEPLOY-096] {confirmed} `litellm/router.py:11326-11346` `get_deployment_by_model_group_name(name)` returns the first stored deployment of that exact `model_name` as a `Deployment`, or `None`. It does no alias, team or wildcard resolution, and raises a plain `Exception` with the stored value's type repr for an unexpected stored type, rendered as in `Model Name invalid - <class 'str'>`.
- [RDEPLOY-097] {confirmed} `litellm/router.py:11311-11324` `get_deployment_credentials(model_id)` returns `None` for an unknown id and for a deployment whose `model_info.blocked is True` (admin-paused). Otherwise it returns only the credential fields of `litellm_params`, with `None` values dropped.
- [RDEPLOY-098] {confirmed} `litellm/router.py:11348-11356`, `litellm/router_utils/common_utils.py:58-60` `deployment_usable_by_team(model, team_id)` is true when the deployment's `model_info.team_id` is `None` or equals `team_id`. A team-owned deployment is therefore unusable by callers with no team. `model_info` is read with `.get` from dict rows and as the attribute of `Deployment` objects.
- [RDEPLOY-099] {confirmed} `litellm/router.py:11632-11652` `get_credential_deployment(model_id, team_id)` tries four lookups and the first hit wins:
  1. Deployment id.
  2. The first deployment of that `model_name` usable by the team.
  3. With a team, that team's first deployment whose `team_public_model_name` equals the value.
  4. A wildcard match ([RDEPLOY-100]).

  It returns `None` when nothing matches or the match is blocked. An id lookup ignores team ownership.
- [RDEPLOY-100] {confirmed} `litellm/router.py:11663-11679` Wildcard credential resolution prefers the team's own pattern router. It falls back to the proxy-wide pattern matches usable by the team, so another team's wildcard is skipped. It takes the first match.
- [RDEPLOY-101] {confirmed} `litellm/router.py:11710-11717` `get_deployment_credentials_with_provider(model_id, team_id)` returns `None` when `get_credential_deployment` does. Otherwise it starts from the credential fields of `litellm_params`.
- [RDEPLOY-102] {confirmed} `litellm/router.py:11719-11730` When the deployment names a `litellm_credential_name`, the stored credential's values are merged over the credential fields and the name is removed from the result. An unknown credential name, or one whose stored values are empty, logs a warning with the name in single quotes, rendered as in `Credential 'my-cred' not found in credential_list`, and merges nothing.
- [RDEPLOY-103] {confirmed} `litellm/router.py:11732-11743` The result always carries `model` (`litellm_params.model`) and `custom_llm_provider`. The provider is chosen in this order:
  1. The explicit `custom_llm_provider`.
  2. Else the text before the first `/` of the model.
  3. Else `openai`.

### Discovered token limits (`arefresh_model_info`)
- [RDEPLOY-105] {confirmed} `litellm/router.py:11377-11389`, `litellm/llms/openai_like/model_info.py:77-90` `arefresh_model_info` snapshots `model_list` and processes it with 8 concurrent workers (`MODEL_INFO_REFRESH_CONCURRENCY`) that share one iterator, so a slow or waiting endpoint does not hold up the others, and the call returns only after every deployment is processed. It never raises, and failures are swallowed at two levels with different debug logs:
  - An HTTP error status (for example `503`), a transport error, a timeout or an unparseable listing is swallowed inside the probe with the debug log `Could not discover upstream model token limits` on the `LiteLLM` logger ([RDEPLOY-108]). That deployment then gets no discovered limits from this refresh, and the worker-level log below is not written for it.
  - Any other exception for one deployment, such as a row that does not parse or a provider that does not resolve, is swallowed by the worker with the debug log `Could not refresh deployment model info` on the `LiteLLM Router` logger, and the worker moves to the next deployment.

  The model-group-info caches are invalidated at the end.
- [RDEPLOY-106] {confirmed} `litellm/router.py:11394-11410` A deployment is probed only when all of the following hold:
  - its provider, after merging `get_deployment_credentials_with_provider(id)` over its `litellm_params`, resolves to one of `hosted_vllm`, `openai`, `text-completion-openai` or `openai_like`;
  - it has an `api_base` after provider resolution, so an `openai` row with no configured `api_base` is not probed;
  - its model contains no `*`;
  - `use_clientside_credentials` is not set.
- [RDEPLOY-107] {confirmed} `litellm/router.py:11411-11429` The probe headers start with `authorization` set to `Bearer` plus the API key, rendered as in `authorization: Bearer sk-local`, when an API key exists: the configured `api_key`, else the key the provider resolver returns. A `hosted_vllm` row with no `api_key` therefore sends the resolver's placeholder, `authorization: Bearer fake-api-key`. They are then overridden by `extra_headers`, else `headers`, from `litellm_params`, with header names lowercased, so a configured `Authorization` replaces the generated one. The probe uses the router's in-memory cache and the given client, or a shared OpenAI async HTTP client.
- [RDEPLOY-108] {confirmed} `litellm/llms/openai_like/model_info.py:61-93`, `litellm/utils.py:10615-10650` The probe works as follows:
  - It sends one GET to the resolved `api_base` joined with `/v1/models`. A trailing path that overlaps is merged and query parameters are kept: for example `https://h.test/v1` and `https://h.test` both become `https://h.test/v1/models`, and `https://h.test/api?x=1` becomes `https://h.test/api/v1/models?x=1`.
  - The request has a 5-second timeout, does not follow redirects and caps the response at 2 MiB (2·1024·1024 bytes).
  - It returns the limits ([RDEPLOY-211]) of the first model card whose `id` equals the provider-resolved model, which is the model without its provider prefix (`hosted_vllm/org/local-model` matches card `org/local-model`). No matching card yields no limits.
  - The parsed listing is cached in the router's in-memory cache for 300 s (`MODEL_INFO_REFRESH_SECONDS`). On any failure an empty listing is cached for 60 s instead, so a retry within 60 s sends no request and yields no limits. The cache key is `upstream_model_info:` followed by the SHA-256 hex digest of the JSON of the URL and the sorted headers, so deployments that share an endpoint and headers share one fetch.
- [RDEPLOY-211] {confirmed} `litellm/llms/openai_like/model_info.py:22-52` A matching model card becomes discovered limits as follows. A card field counts only when it is a positive integer; booleans, strings such as `"2048"`, `0` and negatives count as absent. The context is `max_model_len`, else `context_length`. The limits are then:
  - `max_tokens` = the context;
  - `max_input_tokens` = the card's `max_input_tokens`, else the context, clipped to the context when both exist;
  - `max_output_tokens` = the card's `max_output_tokens`, else the context, clipped the same way.

  A limit with no value is omitted. Worked example: a card advertising `max_model_len: 2048` for a deployment configured with `model_info.max_input_tokens: 1024` makes `get_configured_token_limits` return `(1024, 2048)`, because the configured input limit wins ([RDEPLOY-110]), and an unconfigured sibling deployment gets `(2048, 2048)`.

| Claim | Card fields | Discovered limits |
|---|---|---|
| [RDEPLOY-211] | `max_model_len: 2048` | `max_tokens` 2048, `max_input_tokens` 2048, `max_output_tokens` 2048 |
| [RDEPLOY-211] | `context_length: 4096`, `max_output_tokens: 8192` | `max_tokens` 4096, `max_input_tokens` 4096, `max_output_tokens` 4096 |
| [RDEPLOY-211] | `max_input_tokens: 100` only | `max_input_tokens` 100 only |
| [RDEPLOY-211] | `max_model_len: 0`, `context_length: 10` | `max_tokens` 10, `max_input_tokens` 10, `max_output_tokens` 10 |
| [RDEPLOY-211] | `max_model_len: "2048"` or `max_model_len: true` | none (the probe result is discarded per [RDEPLOY-109]) |

- [RDEPLOY-109] {confirmed} `litellm/router.py:11430-11438`, `litellm/router.py:1392-1395` Discovered limits are kept in a per-router in-memory cache. Its time-to-live is 600 s (`2 * MODEL_INFO_REFRESH_SECONDS`) and its size is `max(len(model_list), 1)`. Results are discarded in three cases:
  - the probe returned nothing;
  - the deployment has no id;
  - the row stored under that id is no longer the same object that was probed, because it was replaced or deleted during the probe.

  A failed refresh leaves earlier limits in place until they expire.
- [RDEPLOY-110] {confirmed} `litellm/router.py:11440-11449` `get_discovered_model_info(model_id)` returns limits only while the cached entry still belongs to the currently stored row for that id. It returns only the limit keys whose value in the row's configured `model_info` is `None`, so a configured limit always wins. Otherwise it returns an empty read-only mapping.
- [RDEPLOY-111] {confirmed} `litellm/router.py:11430-11438` Discovered limits are never written into `model_info`, `model_list` or `litellm.model_cost`. They are separate for each router even when ids are reused.

### Listing and configured-value accessors
- [RDEPLOY-112] {confirmed} `litellm/router.py:11451-11507` `get_model_listing_info(model_name)` reads every deployment indexed under that exact name. It returns `None` for unknown or wildcard-expanded names and never does pattern matching. Its cost-map keys are, per deployment, the first non-empty value of `model_info.base_model`, `litellm_params.base_model` or `litellm_params.model`, deduplicated in config order.
- [RDEPLOY-113] {confirmed} `litellm/router.py:11475-11517`, `litellm/router.py:11440-11449`, `litellm/litellm_core_utils/core_helpers.py:206-231` The listing's `max_input_tokens` and `max_output_tokens` are each the maximum of the deployments' coerced values ([RDEPLOY-212]), or `None` when no deployment yields one. For each limit, a deployment's candidate is its `model_info` value when that key is present and not `None`, else its discovered value ([RDEPLOY-110]). So a present but malformed configured value (`"128,000"`, `""`, a list, `true`) hides that deployment's discovered value, and the deployment contributes nothing to that limit. For example, `d0` configured `max_input_tokens: "bad"` with a discovered `4096`, and `d1` configured `100`, give `max_input_tokens` `100`. Zero and negative integers survive coercion and take part in the maximum.
- [RDEPLOY-114] {confirmed} `litellm/router.py:11519-11544`, `litellm/router.py:11326-11346`, `litellm/router.py:11440-11449`, `litellm/litellm_core_utils/core_helpers.py:206-231` `get_configured_token_limits(model_name)` behaves as follows:
  - It reads only the first deployment indexed under the exact name, in `model_list` position order ([RDEPLOY-197]). Other deployments of the group are ignored even when their limits are wider.
  - When the name is not in the name index, as for unknown, wildcard-expanded or alias names, it returns `(None, None)`.
  - Each of `max_input_tokens` and `max_output_tokens` is the deployment's `model_info` value when that key is present and not `None`, else the discovered value ([RDEPLOY-110]). The result is then coerced ([RDEPLOY-212]).

  A present but malformed configured value therefore blocks the fallback: `model_info` `{max_input_tokens: "128,000", max_output_tokens: ""}` with discovered `(4096, 1024)` returns `(None, None)`, while the same discovered limits with both keys absent, or set to `null`, return `(4096, 1024)`.
- [RDEPLOY-212] {confirmed} `litellm/litellm_core_utils/core_helpers.py:206-231` Configured and discovered token limits are coerced per value, in this order:
  1. A boolean becomes `None`.
  2. An integer is kept as is, including `0` and negatives.
  3. A float is truncated toward zero, so `1.9` becomes `1`, and `NaN` or an infinity becomes `None`.
  4. A string is parsed as a base-10 integer, so `"2048"` becomes `2048` while `"128,000"`, `""` and `"1.5"` become `None`.
  5. Anything else, such as a list or dict, becomes `None`.
- [RDEPLOY-115] {confirmed} `litellm/router.py:11546-11575` `get_configured_mode(model_name)` returns the first deployment's `model_info.mode` only when it is a non-blank string, else `None`. `get_configured_display_name(model_name)` does the same for `model_info.display_name`. Neither resolves wildcards, aliases or teams, and a non-blank value is returned unstripped.
- [RDEPLOY-116] {confirmed} `litellm/router.py:11577-11583`, `litellm/router_utils/common_utils.py:75-92` `routable_model_group(model_name)` returns the `model_group_alias` target, from either the string form or the `{"model": ...}` form. It returns `model_name` itself when the name is not an alias or its target is not a non-empty string.
- [RDEPLOY-117] {confirmed} `litellm/router.py:11585-11604` The deployments a team can route to for a name are computed in three steps:
  1. Collect the deployments of the alias-resolved group, per [RDEPLOY-163].
  2. Keep those usable by the team. If none is usable, keep all of them; for a caller without a team this means every deployment when teams own all of them.
  3. Drop those with `model_info.blocked is True`.

  The order is `model_list` order.
- [RDEPLOY-118] {confirmed} `litellm/router.py:11606-11619` `get_configured_service_tiers(model_name, team_id)` returns, for each routable deployment ([RDEPLOY-117]), its raw `model_info.service_tiers` value unvalidated, or `None` when unset. It returns an empty tuple for unknown or wildcard-expanded names.
- [RDEPLOY-119] {confirmed} `litellm/router.py:11621-11630` `get_routable_upstream_model(model_name, team_id)` returns `litellm_params.model` of the first routable deployment, or `None`.

### Per-deployment model info
- [RDEPLOY-120] {confirmed} `litellm/router.py:11778-11805` `get_router_model_info(deployment, received_model_name, id)` resolves its input as follows:
  - When `id` names a stored deployment, that deployment replaces the passed one.
  - With neither, it raises `ValueError("Deployment not found")`.
  - `litellm_params` must be a `LiteLLM_Params`, or a dict containing `model`. Anything else raises `ValueError` naming the value's bare class name and the deployment's `model_info.id`, else `unknown`, rendered as in `Deployment missing valid litellm_params. Got: NoneType, deployment_id: unknown`.
- [RDEPLOY-121] {confirmed} `litellm/router.py:11786-11835` The catalog lookup name depends on the provider:
  - For an Azure deployment with `base_model` (from `model_info`, else `litellm_params`), the lookup uses `base_model`.
  - For an Azure deployment without `base_model`, the lookup uses the deployment name. An error-level log is written when the `azure/<name>` catalog entry lacks a positive `max_input_tokens`, `max_tokens` or `input_cost_per_token`. The name is the deployment name after `azure/`, so model `azure/my-deploy` logs `Could not identify azure model 'my-deploy'. Set azure 'base_model' for accurate max tokens, cost tracking, etc.- https://docs.litellm.ai/docs/proxy/cost_tracking#spend-tracking-for-azure-openai-models`.
  - For every other provider, the lookup uses the provider-resolved model and ignores `base_model`.
- [RDEPLOY-122] {inferred} `litellm/router.py:11837-11848` For a non-Azure wildcard model, the lookup model is taken from the proxy-wide pattern match for `received_model_name` that has the same deployment id. Errors in that step are ignored. This is inferred, because the pattern router's model substitution is out of scope; a test shows `gemini/*` resolving to catalog info for `gemini/gemini-2.5-flash`.
- [RDEPLOY-123] {confirmed} `litellm/router.py:11856-11861`, `litellm/router.py:11163-11176` The catalog key is the provider, a `/`, then the lookup model, unless the lookup model already starts with that prefix: for example provider `openai` with model `gpt-4o` renders as `openai/gpt-4o`, and `azure` with base model `azure/gpt-4o` stays `azure/gpt-4o`. For a key absent from `litellm.model_cost`, `litellm.get_model_info` raises `litellm.exceptions.ModelNotMappedError` (a direct `Exception` subclass) with a message rendered as in `This model isn't mapped yet. model=azure/not-real-base, custom_llm_provider=azure. Add it here - https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json.`, and that error propagates to the caller. Registration ([RDEPLOY-081]) writes each registered deployment's backend key into the catalog, so a lookup by that deployment's own provider-qualified model finds the entry even for an unmapped model and returns it without raising. The error is reached through a different key, for example a `base_model` key, the matched model of a wildcard deployment such as `gemini/not-real-xyz` under `gemini/*` ([RDEPLOY-122]), or a deployment that was never registered.
- [RDEPLOY-124] {confirmed} `litellm/router.py:11866-11886` The result is a deep copy of the catalog entry, so the shared cached catalog object is never mutated. Values are overlaid in this precedence order, later wins:
  1. The catalog entry.
  2. A widened `max_input_tokens` from `base_model` ([RDEPLOY-125]).
  3. Discovered limits.
  4. Every non-`None` key of the deployment's own `model_info`.
- [RDEPLOY-125] {confirmed} `litellm/router.py:11875-11881`, `litellm/router.py:1085-1104` A declared `base_model` can only raise `max_input_tokens`, and only when all of the following hold:
  - the route's catalog entry declares `max_input_tokens`;
  - the base model names the same model as the route, comparing the last path segment, with Bedrock ids normalized and an `@` suffix tolerated;
  - the base model's own exact catalog entry is not a generalized fallback and declares a strictly larger value.

  `model_info.base_model` is consulted before an undeclared `litellm_params.base_model`.
- [RDEPLOY-126] {confirmed} `litellm/router.py:11888-11902` `get_model_info(id)` returns the stored `model_list` row itself, the same mutable object rather than a copy, or `None`.
- [RDEPLOY-127] {confirmed} `litellm/router.py:11904-11914` `get_model_group(id)` returns `get_model_list` called with the stored row's `model_name`, for example `get_model_list(model_name="gpt-4o")` for an id whose row is named `gpt-4o`. That list includes alias, routing-group and wildcard rows. An unknown id returns `None`.
- [RDEPLOY-128] {confirmed} `litellm/router.py:11931-11963` `get_deployment_model_info(model_id, model_name)` gathers three sources and swallows every lookup error:
  - *custom*: a deep copy of `litellm.model_cost[model_id]` with discovered limits overlaid, only when the id is a catalog key;
  - *builtin*: `litellm.get_model_info(model_name)`;
  - *base*: when custom carries `base_model`, a deep copy of that model's info, with custom's non-`None` values overlaid on it.

  During the overlay, stringified numbers become numbers.
- [RDEPLOY-129] {confirmed} `litellm/router.py:11965-11985` The result depends on which sources exist:

| Claim | custom present | builtin present | Result |
|---|---|---|---|
| [RDEPLOY-129] | yes | yes | deep copy of builtin overlaid by custom's non-`None` values |
| [RDEPLOY-129] | no | yes | deep copy of builtin |
| [RDEPLOY-129] | yes | no | custom (with base defaults) |
| [RDEPLOY-129] | no | no | `None` |

- [RDEPLOY-130] {confirmed} `litellm/router.py:11986-11993` The result's `input_cost_per_token` and `output_cost_per_token` are forced to `None` when two conditions hold:
  - at least one raw catalog entry exists under the id, the builtin key or the base key;
  - none of them declares either price.

  So an unpriced deployment reports no price instead of a synthesized `0`.

### Model group info (`get_model_group_info`)
- [RDEPLOY-131] {confirmed} `litellm/router.py:12269-12288` When `model_group` is a `model_group_alias` key, the alias is resolved one hop and the result is labeled with the alias name. The alias entry is handled by its shape:
  - A string target is used as is.
  - A dict entry with `hidden: true` returns `None` unless `include_hidden=True`.
  - Another dict entry uses its `model`.
  - Any other value returns `None`.

  The alias check comes before any real group of the same name.
- [RDEPLOY-132] {confirmed} `litellm/router.py:12274-12278` A dict alias entry that lacks the `hidden` key raises `KeyError`, because the key is read directly.
- [RDEPLOY-133] {confirmed} `litellm/router.py:12012-12028`, `litellm/router.py:13340-13357` A group's members come from one of two sources:
  - The deployments named exactly the group, plus routing-group member rows of that name.
  - When there are none, the wildcard deployments matching the name, re-labeled with it.

  The group's own alias entry is not followed again, so in an alias chain `X -> T -> U`, `X` is described by `T`'s deployments. The description is the first string `model_info.description` among the members.
- [RDEPLOY-134] {confirmed} `litellm/router.py:12038-12066` A member's `tpm` is read from the first place it is set: top-level `tpm`, then `litellm_params.tpm`, then `model_info.tpm`. The same order applies to `rpm`, `itpm` and `otpm`. The group totals are the sums over members that set them, and a total stays unset when no member sets it.
- [RDEPLOY-135] {confirmed} `litellm/router.py:12068-12115` A member's model info comes from `get_deployment_model_info(id, litellm_params.model)`. Any error, or a missing id, falls back to a synthesized entry with these fields:
  - `key` = group name;
  - token limits `None`;
  - `input_cost_per_token` and `output_cost_per_token` from `model_info`, converted to float, and `None` when not numeric;
  - `litellm_provider`;
  - `mode` = `model_info.mode`, default `chat`;
  - `supported_openai_params` for the provider, or `[]`;
  - `supports_system_messages` `None`.
- [RDEPLOY-136] {confirmed} `litellm/router.py:12080-12089` A `BadRequestError` from provider resolution is logged at error level with the error's text appended, and the provider is treated as the empty string, so `providers` contains `""`. For example, a stored prompt-management row with model `prometheus/my-prompt` logs a message rendered as `litellm.router.py::get_model_group_info() - litellm.BadRequestError: LLM Provider NOT provided. Pass in the LLM provider you are trying to call. You passed model=prometheus/my-prompt` followed by the resolver's hint text. Other provider-resolution errors propagate.
- [RDEPLOY-137] {confirmed} `litellm/router.py:12117-12127` The first member seeds the group:
  - `model_group` is the user-facing name;
  - `providers` is the member's provider;
  - the description, if any;
  - every field of the member's model info;
  - `supports_fast_mode=True` and `supported_reasoning_efforts=None`.
- [RDEPLOY-138] {confirmed} `litellm/router.py:12128-12201` Each later member is merged into the group:
  - Its provider is added if new.
  - `max_input_tokens`, `max_output_tokens`, `input_cost_per_token` and `output_cost_per_token` take the maximum across members. Costs are converted to float, and unparseable strings are ignored.
  - `supports_parallel_function_calling`, `supports_vision`, `supports_function_calling`, `supports_web_search`, `supports_url_context` and `supports_reasoning` become `True` if any member has `True`.
  - `supported_openai_params` is replaced by the latest non-`None` value.
  - A catalog `tpm` or `rpm` is used only when the member set none. That substitution happens for the second and later members only.
- [RDEPLOY-139] {confirmed} `litellm/router.py:12203-12205` `supports_fast_mode` is true only if every member's provider-resolved model supports Anthropic fast mode according to the exact provider catalog.
- [RDEPLOY-140] {confirmed} `litellm/router.py:12206-12220` `supported_reasoning_efforts` is the intersection of the members' supported effort levels. Once any member's levels are unknown, for example an unmapped model, the group value is `None` and stays `None`.
- [RDEPLOY-141] {confirmed} `litellm/router.py:12241-12259` After merging, the group gets the totals of [RDEPLOY-134] when set. It also gets the last member's `configurable_clientside_auth_params`, when that value is not `None`. When no member matches, the result is `None`.
- [RDEPLOY-142] {confirmed} `litellm/router.py:12017-12028` A row counts as a member when its `model_name` equals the group, or when the proxy-wide pattern router matches the group name. In the second case every candidate row counts.
- [RDEPLOY-143] {confirmed} `litellm/router.py:12409-12419`, `litellm/router.py:13376-13390` `cached_model_group_info(model_group)` returns the memoized `get_model_group_info(model_group)` result, never hidden aliases. Its behavior has four parts:
  - The memo is a class-level least-recently-used cache keyed by `(router, model_group)`. Its size is `DEFAULT_MAX_LRU_CACHE_SIZE`, default `64`, overridable through the env var of that name.
  - It is cleared whenever this module changes `model_list`, after a discovery refresh and after a price replay.
  - It is shared by all `Router` instances, so one router's invalidation clears every router's entries.
  - It holds a strong reference to each cached router.

### Usage and rate-limit headers
- [RDEPLOY-144] {confirmed} `litellm/router.py:12290-12355` `get_model_group_usage(model_group)` returns `(tpm, rpm)` for the current UTC minute. Its steps:
  1. Resolve deployments with `get_model_list(model_name=model_group)`, which covers aliases, routing groups and wildcards.
  2. Build keys of the form `global_router:<id>:<litellm_params.model>:tpm:<HH-MM>`, rendered for example as `global_router:d1:openai/gpt-4o:tpm:14-05` (UTC hour and minute, zero-padded), and the matching `rpm` keys, skipping deployments without id or model.
  3. Batch-read the keys from the router cache.
  4. Sum only integer values. A value is `None` when no integer was found, and `(None, None)` is returned when the batch read returns `None`.
- [RDEPLOY-145] {confirmed} `litellm/router.py:12357-12407`, `litellm/types/router.py:1177-1180` `get_model_group_io_token_usage(model_group)` reads the `itpm` and `otpm` keys of the same shape, rendered for example as `global_router:d1:openai/gpt-4o:itpm:14-05` and `global_router:d1:openai/gpt-4o:otpm:14-05`, and returns their integer sums as `(itpm, otpm)`. With no deployments, or when no integer is found, it returns `None` for that position, so an unknown group yields `(None, None)`.
- [RDEPLOY-146] {confirmed} `litellm/router.py:12421-12455`, `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:72-74`, `litellm/router_utils/pre_call_checks/io_token_rate_limit_check.py:748-767` `get_remaining_model_group_usage(model_group)` reads the limits from the cached group info ([RDEPLOY-143], [RDEPLOY-134]) and returns a dict of integer header values. Keys are added in this order:
  1. When the group has an `itpm` limit: `x-ratelimit-limit-input-tokens` = the limit, `x-ratelimit-remaining-input-tokens` = `max(0, limit − current ITPM)`, and `x-ratelimit-reset-input-tokens` = seconds until the next UTC minute, `max(1, 60 − current second)`. An `otpm` limit adds the three `...-output-tokens` headers the same way. Current usage counts as `0` when unknown.
  2. When the group has a `tpm` limit: `x-ratelimit-remaining-tokens` = limit − current tokens, with unknown usage counted as `0` and the result not clamped, so it can be negative; then `x-ratelimit-limit-tokens` = the limit.
  3. When the group has an `rpm` limit: `x-ratelimit-remaining-requests` and `x-ratelimit-limit-requests` the same way.

  Both header families can be present together. A group with none of the four limits, and an unknown group (cached info `None`), return the empty dict `{}`. For example, a group with `tpm` 5000 and `rpm` 50 that has used 500 tokens and 5 requests this minute returns `{'x-ratelimit-remaining-tokens': 4500, 'x-ratelimit-limit-tokens': 5000, 'x-ratelimit-remaining-requests': 45, 'x-ratelimit-limit-requests': 50}`. A group with `itpm` 2000 used 2500 reports `x-ratelimit-remaining-input-tokens` 0, while `tpm` 5000 used 7000 reports `x-ratelimit-remaining-tokens` -2000.
- [RDEPLOY-147] {confirmed} `litellm/router.py:12457-12485` `set_response_headers(response, model_group, request_kwargs)` returns `None` for a `None` response. A bare async iterator is wrapped in a carrier that iterates the same items. Then, on the response's `additional_headers`, it does the following:
  - It stamps the response model id from the deployment metadata in `request_kwargs`.
  - It sets `x-litellm-model-group` to `model_group`, even when that is `None`.
  - It applies the quality-router decision headers and overwrites with the complexity-router decision headers.
  - When `model_group` is set, it adds the remaining-usage headers.

  For a dict response, the headers live under `response["_hidden_params"]["additional_headers"]`.
- [RDEPLOY-148] {confirmed} `litellm/router.py:12482-12484`, `litellm/router_utils/add_retry_fallback_headers.py:203-209` A remaining-usage header is added only when the response does not already carry that header. A provider-native `x-ratelimit-remaining-tokens` therefore wins over the router's value, while the router's other headers are still added.

### Dead and conditional code
- [RDEPLOY-150] {confirmed} `litellm/router.py:12487-12532` `_build_model_name_index` and `_build_model_id_to_deployment_index_map` have no caller outside tests. The first rebuilds the name and team indexes from a list. The second resets `model_list` and re-appends rows, deriving and writing missing ids into the passed rows.
- [RDEPLOY-151] {confirmed} `litellm/router.py:10703-10710`, `litellm/router.py:10740-10743` Two pieces of registration are commented out and have no effect: the `*` catch-all default-deployment handling and per-deployment client initialization.

### Name, id and team queries
- [RDEPLOY-155] {confirmed} `litellm/router.py:12568-12603` `get_candidate_model_ids_for_route(model, team_id)` resolves the alias first and then takes the first source that yields deployments:
  1. The routing-group members.
  2. The early-resolve path for a name that is not a `model_name`: team route, wildcard pattern (including a provider-qualified retry), team pattern router, default deployment.
  3. The deployments named exactly `model`.

  It returns their ids as strings. It is read-only, does not apply fallbacks, and does not raise for an unknown name; that case yields an empty set.
- [RDEPLOY-156] {confirmed} `litellm/router.py:12596-12603` Id sets are built from `model_info.id` converted to string. Rows without a `model_info` mapping or without an id are skipped.
- [RDEPLOY-157] {confirmed} `litellm/router.py:12679-12690` `has_model_id(candidate_id)` is an exact membership test on the id index.
- [RDEPLOY-158] {confirmed} `litellm/router.py:12692-12755` `resolve_model_name_from_model_id(model_id, custom_llm_provider)` returns `None` for an empty input. Otherwise it tries these steps and the first success wins:
  1. Return the input when it is a known model name.
  2. When it is a deployment id, return that deployment's `model_name`.
  3. Return the `model_name` of the first deployment whose `litellm_params.model` equals the input, or ends with `/<input>` or `:<input>`.
  4. Return the input when the router recognizes it as an alias or routing group.
  5. Return the input when a wildcard route serves it for the given provider.
  6. Otherwise return `None`.
- [RDEPLOY-159] {confirmed} `litellm/router.py:12757-12765` `resolve_served_model_name(model_name, served_model)` returns `served_model` when `model_name` routes to it, else `model_name`. Routing to it means `served_model` is the alias target, or is a member of the target's routing group, or equals the name itself.
- [RDEPLOY-160] {confirmed} `litellm/router.py:12767-12828` `map_team_model(team_model_name, team_id, custom_llm_provider)` handles three cases:
  - With an explicit name, it returns that name when any listed deployment for it is owned by the team, else `None`. The provider is ignored.
  - With no name and no provider, it returns the first team-owned deployment's `team_public_model_name`, else that deployment's `model_name`.
  - With no name, it returns `None` when the team owns nothing. Wildcards are left to routing.
- [RDEPLOY-161] {confirmed} `litellm/router.py:12780-12816` With no name but a provider, `map_team_model` picks the first team-owned deployment whose generic-call provider equals the provider, and returns `None` when there is none. It returns that deployment's public name when every team deployment sharing the public name uses the same provider. Otherwise it returns the deployment's id, to pin it.
- [RDEPLOY-162] {confirmed} `litellm/router.py:12830-12851` `should_include_deployment(model_name, model, team_id)` is true in two cases:
  - The deployment is owned by `team_id` and its `team_public_model_name` equals `model_name`.
  - The deployment's `model_name` equals `model_name` and one of these holds: the caller has no team, the deployment has no team, or the deployment's team is the caller's.
- [RDEPLOY-163] {confirmed} `litellm/router.py:12874-12925` `get_all_deployments(model_name, model_alias, team_id)` tries three paths in order:
  1. With a team, the `(team_id, model_name)` team index. Its included rows are returned alone when any exist.
  2. Otherwise the rows indexed under `model_name` that pass [RDEPLOY-162].
  3. Only when the name is not indexed and a team is given, a full scan with the same predicate.

  The result is in `model_list` order.
- [RDEPLOY-164] {confirmed} `litellm/router.py:12886-12923` With `model_alias`, each returned row is a shallow copy whose `model_name` is the alias. Nested `litellm_params` and `model_info` are shared with the stored row.
- [RDEPLOY-165] {confirmed} `litellm/router.py:12929-12948`, `litellm/router.py:13036-13065` `get_model_names(team_id)` walks `get_model_list()`, which is non-hidden alias rows, then routing-group rows, then every stored row. It emits one name per row, so names repeat for multi-deployment groups:
  - A row with a truthy `model_info.team_id` contributes its `team_public_model_name` only when its team equals `team_id`. Otherwise it contributes nothing.
  - Other rows contribute `model_name`, or `""` when missing.
- [RDEPLOY-166] {confirmed} `litellm/router.py:12950-12969` `get_fully_blocked_model_names()` returns the names from `get_model_list()` (aliases and routing groups included) for which every row has `model_info.blocked is True`. A missing flag counts as unblocked.
- [RDEPLOY-167] {confirmed} `litellm/router.py:12971-12983` `are_all_deployments_blocked(deployments)` is true only for a non-empty list in which every row is blocked. The internal fully-blocked check applies this to `get_model_list(model_name=...)`.
- [RDEPLOY-168] {confirmed} `litellm/router.py:12985-13034` `async_get_fully_unhealthy_model_names()` returns an empty set in two cases: `allowed_fails_policy` is set, or no non-stale unhealthy ids exist in the health-state cache. Otherwise it returns every `model_name` and `team_public_model_name` all of whose rows are unhealthy, reading rows from `get_model_list()`. Names expanded from wildcards are never hidden.
- [RDEPLOY-170] {confirmed} `litellm/router.py:13067-13101` `get_model_list_from_model_alias(model_name)` returns `[]` immediately for a name that is not an alias key. Otherwise it walks the matching alias entry, or every entry when no name is given. Hidden dict entries are skipped only when no name is given. An alias whose target is a callable routing group yields the group's member rows; otherwise it yields the target's deployments. In both cases the rows are relabeled with the alias name.
- [RDEPLOY-171] {confirmed} `litellm/router.py:13103-13134` `get_model_list_from_routing_groups(model_name)` returns the member rows of a callable routing group, labeled with the group name, with the group's priority applied. With no name it returns the rows of all callable groups. That full result is memoized until the model-group-info caches are invalidated.
- [RDEPLOY-172] {confirmed} `litellm/router.py:13136-13145` A member row re-emitted under a routing-group name never carries the member's `model_info.access_groups`. A key holding a member's access group therefore does not gain the whole group.

### Parameter acceptance helpers
- [RDEPLOY-175] {confirmed} `litellm/router.py:13147-13157` `TIER_PARAMS_NEVER_DROPPED` is every litellm-internal parameter name plus `additional_drop_params`, `drop_params`, `messages`, `model`, `extra_headers`, `max_tokens` and `max_completion_tokens`.
- [RDEPLOY-176] {confirmed} `litellm/router.py:13159-13164` A declared parameter allowlist is the string entries of `allowed_openai_params` when that value is a list, tuple, set or frozenset. Any other value yields an empty allowlist.
- [RDEPLOY-177] {confirmed} `litellm/router.py:13166-13177` A deployment accepts a parameter when any of the following holds:
  - it has no `litellm_params`;
  - its own `allowed_openai_params` names the parameter;
  - its model or provider declares an authenticating provider, decided without any provider lookup;
  - it supports the parameter ([RDEPLOY-178]).
- [RDEPLOY-178] {confirmed} `litellm/router.py:13179-13215` A deployment supports a parameter when one of these holds:
  - its provider's supported-parameter list contains it;
  - the list is unknown (`None`);
  - the lookup raises.

  The lookup is made for the provider-resolved model, using `base_model` from `model_info` first, then `litellm_params`. For an authenticating provider, the model is the provider prefix stripped from the model. The group name stands in when the deployment has no model. A lookup error is logged at debug level as `litellm.router.py::_deployment_supports_param: keeping <param> for model=<group>. Got - <error>`.
- [RDEPLOY-179] {inferred} `litellm/router.py:13173-13186` The authenticating providers decided before lookup are `github_copilot` and `chatgpt`, whose resolution would start an interactive OAuth device flow. This is inferred from the docstring of the out-of-range caller at router.py:13244-13246.

### Support for deployment selection
- [RDEPLOY-190] {confirmed} `litellm/router.py:12605-12627` The region filter used by selection returns the deployments unchanged in three cases:
  - the request has no `allowed_model_region`;
  - `enable_pre_call_checks` is false;
  - the request carries no messages or input.

  A non-string `allowed_model_region` returns no deployments. Otherwise it keeps the deployments whose `litellm_params` are allowed in that region.
- [RDEPLOY-191] {confirmed} `litellm/router.py:12629-12677` When every candidate is cooling down, the "no deployment" error lists the cooled deployment ids that region and tag routing would still have sent the request to. These are computed by repeatedly asking tag routing to pick from the remaining region-allowed cooled deployments. Each round adds the picked ids and removes them from the pool. The loop stops when tag routing raises `ValueError` or picks nothing new. Tag routing works on a copy of the metadata bucket, so no tag match is recorded on the request. A request whose metadata bucket exists but is not a mapping yields an empty set.

## Validation rules
Model-list rows are checked in the order shown in the table under "Building one row" ([RDEPLOY-015], [RDEPLOY-016], [RDEPLOY-017], [RDEPLOY-021], [RDEPLOY-022], [RDEPLOY-024]). The first failure wins. Strategy routers are validated at registration ([RDEPLOY-063], [RDEPLOY-065], [RDEPLOY-066], [RDEPLOY-068], [RDEPLOY-069], [RDEPLOY-061]).

What is not validated:
- [RDEPLOY-180] {confirmed} `litellm/router.py:10941-10958`, `litellm/router.py:10571-10585` Duplicate deployment ids are rejected only for PTU reservations ([RDEPLOY-015]). Any other duplicate id is accepted silently: both rows are stored, the id index points at the later one, and lookups by id never see the earlier one.
- [RDEPLOY-181] {confirmed} `litellm/router.py:10960-10965` A row with an empty or missing `model_name` is stored but not added to the name index. It cannot be found by name.
- [RDEPLOY-182] {confirmed} `litellm/router.py:10820-10851`, `litellm/router.py:10970-11025` Runtime add and upsert apply only provider and strategy-router validation ([RDEPLOY-042]). A runtime-added deployment can therefore carry an invalid `tag_regex`, invalid access windows or an environment restriction. These are rejected or ignored only when the same row is loaded through a model list.
- [RDEPLOY-183] {confirmed} `litellm/router.py:12001-12003`, `litellm/router.py:12261-12288` Group-name inputs to the query methods are not normalized: no trimming and no case folding. Unknown names yield `None`, `()`, `[]` or empty sets rather than errors.

## Error handling
| Claim | Condition | Raised / returned | Logged | Swallowed? |
|---|---|---|---|---|
| [RDEPLOY-033] | invalid model-list row, `ignore_invalid_deployments=False` | original exception propagates out of `set_model_list` / construction | none | no |
| [RDEPLOY-033] | invalid model-list row, `ignore_invalid_deployments=True` | row dropped | `Error creating deployment: ...` with traceback | yes; provider failures queued for replay |
| [RDEPLOY-043] | invalid row in `add_deployment` | propagates | none | no |
| [RDEPLOY-049] | failed upsert before the new row is appended, ignore on | `None`, previous row restored | warning, then info `Restored deployment ...` | yes |
| [RDEPLOY-049] | failed upsert after the new row is appended (budget sync, deferred adaptive pass), ignore on | `None`; the failed row stays stored, previous row lost | warning only | yes |
| [RDEPLOY-051] | failed upsert, ignore off | propagates; previous row lost; the failed row stays stored when the failure followed the append | none | no |
| [RDEPLOY-043] | budget sync fails in `add_deployment` | propagates after the row was stored | none | no |
| [RDEPLOY-054] | strategy release fails during delete | removed row returned | exception log | yes |
| [RDEPLOY-055] | any other delete failure | `None` | none | yes |
| [RDEPLOY-085] | malformed row during price replay | row skipped | exception log | yes |
| [RDEPLOY-105] | discovery failure for one deployment | none | debug log | yes |
| [RDEPLOY-128] | catalog lookup errors in `get_deployment_model_info` | partial or `None` result | none | yes |
| [RDEPLOY-123] | unmapped catalog key in `get_router_model_info` | `ModelNotMappedError` propagates | none | no |
| [RDEPLOY-132] | dict alias without `hidden` | `KeyError` | none | no |
| [RDEPLOY-178] | provider lookup error for parameter support | parameter treated as supported | debug log | yes |

- [RDEPLOY-184] {confirmed} `litellm/router.py:9852-9855`, `litellm/router.py:9900-9903`, `litellm/router.py:9937-9940` Every price-inheritance step swallows an unmapped backend model without logging. The inheritance is skipped and the deployment keeps only its own prices.
- [RDEPLOY-185] {confirmed} `litellm/router.py:11011-11013`, `litellm/router.py:10820-10833` Nothing here retries, and none of these operations has a timeout, except the discovery HTTP probe ([RDEPLOY-108]). Failed registrations are retried only by the price-reload replay ([RDEPLOY-085]).

## State and data
- [RDEPLOY-186] {confirmed} `litellm/router.py:10072-10074`, `litellm/router.py:10841-10848` Each `model_list` entry is stored as a plain dict: the `Deployment`'s JSON form with `None` fields omitted. Lookups that return a `Deployment` build a new object from this dict ([RDEPLOY-095]). `get_model_info` returns the dict itself ([RDEPLOY-126]).
- [RDEPLOY-187] {confirmed} `litellm/router.py:1366-1373` The router keeps three indexes over `model_list` positions:
  - the id index (`model_id_to_deployment_index_map`);
  - the name index (`model_name_to_deployment_indices`);
  - the team index, keyed by `(team_id, team_public_model_name)`.

  `team_public_model_names` is maintained alongside. Every add and remove in this module keeps them consistent ([RDEPLOY-057], [RDEPLOY-058]).
- [RDEPLOY-188] {confirmed} `litellm/router.py:11154-11176` This module writes to process-global `litellm.model_cost` under deployment ids and shared backend keys ([RDEPLOY-080], [RDEPLOY-081]). It never deletes those entries. Every registration is marked non-persistent, so it survives a catalog reload only through the live-router replay ([RDEPLOY-085], [RDEPLOY-086]).
- [RDEPLOY-189] {confirmed} `litellm/router.py:12332`, `litellm/router.py:12390` This module only reads the per-minute usage counters in the router cache (in-memory plus optional Redis). It never writes them.
- [RDEPLOY-192] {confirmed} `litellm/router.py:10408-10414`, `litellm/router.py:10481-10483` This module mutates the process-global callback lists by adding and removing adaptive-router post-call hooks ([RDEPLOY-070], [RDEPLOY-073]) and by adding a deployment-affinity check ([RDEPLOY-067]).

## External interactions
- [RDEPLOY-193] {confirmed} `litellm/router.py:10596-10600`, `litellm/router.py:10729-10738`, `litellm/router.py:478-512` Environment and secrets are read at three points:
  - `os.environ/` values are read through `get_secret` once, at model-list load.
  - `dataSources` values are read straight from the process environment at registration.
  - `LITELLM_ENVIRONMENT` is read through the secret manager on every environment-gate evaluation.
- [RDEPLOY-194] {confirmed} `litellm/router.py:12300-12301`, `litellm/router.py:12361-12362` Usage keys use the current UTC wall-clock minute formatted `%H-%M`, so they carry no date and wrap daily.
- External HTTP is limited to the discovery probe ([RDEPLOY-106]..[RDEPLOY-108]). Credentials come from the in-process credential store ([RDEPLOY-102]), and Vertex pass-through registration goes to the proxy's pass-through router ([RDEPLOY-032]).

## Configuration
| Setting | Source | Default | Effect | Claims |
|---|---|---|---|---|
| `ignore_invalid_deployments` | Router constructor | `False` | drop invalid rows/upserts instead of raising | [RDEPLOY-033], [RDEPLOY-049], [RDEPLOY-051] |
| `auto_router_capability_limit` | Router constructor (callable) | `None` = unlimited | ceiling on licensed complexity-router capabilities | [RDEPLOY-076], [RDEPLOY-050] |
| `model_group_alias` | Router constructor / `update_settings` | `{}` | alias resolution in group info, listings, service tiers | [RDEPLOY-116], [RDEPLOY-131], [RDEPLOY-170] |
| `enable_pre_call_checks` | Router constructor | `False` | enables the region filter | [RDEPLOY-190] |
| `allowed_fails_policy` | Router constructor | `None` | when set, unhealthy-name hiding is disabled | [RDEPLOY-168] |
| `LITELLM_ENABLE_PTU_COST_ATTRIBUTION` | env | off | PTU refusal, zeroing scope, capacity warnings | [RDEPLOY-005], [RDEPLOY-015], [RDEPLOY-017] |
| `LITELLM_ENVIRONMENT` | env / secret manager | unset | environment gating of rows with `supported_environments` | [RDEPLOY-014] |
| `DEFAULT_MAX_LRU_CACHE_SIZE` | env | `64` | size of the group-info memo | [RDEPLOY-143] |
| per-row `model_info` / `litellm_params` keys | config | none | `id`, `team_id`, `team_public_model_name`, `blocked`, `base_model`, `service_tiers`, `display_name`, `mode`, `description`, `tpm`/`rpm`/`itpm`/`otpm`, pricing fields, `tag_regex`, `use_in_pass_through`, `max_budget`/`budget_duration` | behaviors above, for example [RDEPLOY-007], [RDEPLOY-098], [RDEPLOY-022], [RDEPLOY-091] |

## Concurrency and ordering
- [RDEPLOY-195] {confirmed} `litellm/router.py:10552-10642`, `litellm/router.py:10820-10851`, `litellm/router.py:10970-11039`, `litellm/router.py:11206-11243` The registry methods `set_model_list`, `add_deployment`, `upsert_deployment` and `delete_deployment` are synchronous and take no lock. Within one event loop they cannot interleave with coroutines, since they contain no awaits. A thread calling them concurrently with request handling could observe a popped-but-not-re-added deployment, or indexes that are mid-repair.
- [RDEPLOY-196] {confirmed} `litellm/router.py:11381-11388`, `litellm/router.py:11431` Discovery runs up to 8 probes concurrently, and other coroutines, including upserts, may run between its awaits. The object-identity check ([RDEPLOY-109]) is what keeps a probe's result from attaching to a replaced row.
- [RDEPLOY-197] {confirmed} `litellm/router.py:11003-11013`, `litellm/router.py:11336-11339` `model_list` order is insertion order, and an upsert moves the edited row to the end. Order matters because every "first deployment" lookup reads the earliest position: `get_deployment_by_model_group_name`, configured mode, display name, token limits, upstream model and adaptive-router cost reading. An edit can therefore change which deployment those lookups describe.
- [RDEPLOY-198] {inferred} `litellm/router.py:12409-12410` The group-info memo is a class-level standard-library LRU cache shared by all routers in the process. Its own operations are thread-safe, but its invalidation is global ([RDEPLOY-143]). This is inferred from standard-library semantics.

## Implementation notes
- Positions in `model_list` are the primary key of all three indexes. Removal repairs them in O(number of deployments) ([RDEPLOY-058]), while lookup by id or name is O(1) plus the group size.
- Strategy registries are `name -> [entry per tags]` lists rather than dicts keyed by `(name, tags)`. Registration and release scan that short list.
- The SHA-256 id derivation ([RDEPLOY-007]) is load-bearing. Ids key cooldowns, budgets, spend rows and cost-map entries, so changing the concatenation would re-key all of them on upgrade.
- The deep copy in `set_model_list` ([RDEPLOY-001]) and the deep copies of catalog entries ([RDEPLOY-028], [RDEPLOY-124], [RDEPLOY-128]) are load-bearing. They keep the caller's config and the process-wide cached catalog from being mutated.

## Open questions and gaps
- RDEPLOY-075: do strategy objects dropped by `set_model_list` hold resources that outlive the reset? Resolve by reading the complexity, auto and quality router implementations.
- [RDEPLOY-199] {gap} `litellm/router.py:10552-10568`, `litellm/router.py:1406` In production, `set_model_list` is only called from the constructor, while tests call it again. Is a second call on a live router a supported operation, given the stale and duplicated wildcard entries and the retained adaptive routers ([RDEPLOY-003], [RDEPLOY-074])?
- [RDEPLOY-200] {gap} `litellm/router.py:10604-10623` Organization-list expansion gives all the expanded deployments one shared id ([RDEPLOY-009]), so cooldowns, budgets and id lookups treat them as a single deployment. Is that intended?
- [RDEPLOY-201] {gap} `litellm/router.py:10635` `model_names` keeps names of rows that were dropped ([RDEPLOY-010]), and the proxy's model-recognition checks read that set. Should a dropped name still be treated as known?
- [RDEPLOY-202] {gap} `litellm/router.py:12274-12278` Should a dict `model_group_alias` entry without `hidden` default to visible instead of raising `KeyError` ([RDEPLOY-132])? The validated alias type may make the key mandatory upstream.
- [RDEPLOY-203] {gap} `litellm/router.py:12198-12201`, `litellm/router.py:12117-12127` For the first member of a group, a catalog `tpm`/`rpm` reaches the group only through the seed copy, while later members contribute it to the totals ([RDEPLOY-138]). Is this asymmetry intended?
- [RDEPLOY-204] {gap} `litellm/router.py:10820-10851` Are runtime-added deployments meant to skip the environment gate, the `tag_regex` check and the access-window check ([RDEPLOY-042], [RDEPLOY-182])? The proxy validates some of these at its write endpoints, but that was not traced.

## Test evidence
| Claim | Test | What it pins |
|---|---|---|
| [RDEPLOY-005] | `tests/unit/test_router_model_cost_isolation.py::test_a_reservation_declared_while_the_feature_is_off_is_warned_about` | PTU-disabled warning |
| [RDEPLOY-006] | `tests/unit/test_router/test_router.py::test_router_keeps_wif_secret_pointers_unresolved` | `os.environ/` expansion except `*_ref` pointers |
| [RDEPLOY-009] | `tests/unit/test_router/test_router.py::test_router_multi_org_list` | one deployment per organization |
| [RDEPLOY-014] | `tests/unit/test_router/test_router.py::test_model_info_is_active_for_environment_matrix`, `tests/unit/test_router/test_router_helper_utils.py::test_deployment_is_active_for_environment` | environment gate |
| [RDEPLOY-015] | `tests/unit/test_router_model_cost_isolation.py::test_two_reservations_cannot_share_one_id`, `tests/unit/test_router_model_cost_isolation.py::test_a_reservation_without_a_declared_id_is_refused`, `tests/unit/test_router_model_cost_isolation.py::test_a_falsy_id_is_still_scanned_for_collisions` | PTU identity rule |
| [RDEPLOY-017] | `tests/unit/test_router_model_cost_isolation.py::test_a_config_ptu_deployment_bills_nothing_per_token`, `tests/unit/test_router_model_cost_isolation.py::test_a_database_backed_deployment_is_left_alone` | PTU zeroing scope |
| [RDEPLOY-021] | `tests/unit/test_router/test_router_helper_utils.py::test_create_deployment` | environment-inactive row returns `None` |
| [RDEPLOY-024] | `tests/unit/test_router/test_router.py::test_add_invalid_provider_to_router`, `tests/unit/test_router/test_router.py::test_router_add_deployment_accepts_explicit_custom_provider_from_custom_provider_map` | provider validation |
| [RDEPLOY-028] | `tests/unit/test_router_model_cost_isolation.py::test_inherit_builtin_base_rates_for_off_peak_fills_missing_rates`, `tests/unit/test_router_model_cost_isolation.py::test_inherit_builtin_base_rates_for_off_peak_leaves_explicit_rates_alone` | off-peak inheritance |
| [RDEPLOY-030] | `tests/unit/test_router_model_cost_isolation.py::test_inherit_builtin_tiered_output_rate_never_stores_a_synthesized_zero` | tiered output inheritance |
| [RDEPLOY-033] | `tests/unit/test_router/test_router.py::test_arouter_ignore_invalid_deployments`, `tests/unit/test_router_model_cost_isolation.py::test_the_proxy_drops_the_deployment_rather_than_failing_to_boot` | ignore-invalid drop |
| [RDEPLOY-040] | `tests/unit/test_router/test_router_helper_utils.py::test_add_deployment` | existing id not re-added |
| [RDEPLOY-044] | `tests/unit/test_router/test_router.py::test_add_invalid_provider_to_router` | pattern router untouched |
| [RDEPLOY-049] | `tests/unit/router_strategy/test_complexity_router.py::TestRouterComplexityDeploymentMethods`, `tests/unit/test_router/test_router.py::test_arouter_ignore_invalid_deployments` | upsert drop and restore |
| [RDEPLOY-050] | `tests/unit/router_strategy/test_complexity_router.py::test_failed_edit_of_a_live_v2_router_rolls_back_without_the_ceiling` | restore bypasses ceiling |
| [RDEPLOY-052] | `tests/unit/test_router/test_router_helper_utils.py::test_upsert_deployment_clears_stale_budget_config` | budget re-sync on upsert |
| [RDEPLOY-058] | `tests/unit/test_router/test_router.py::test_deletion_updates_model_name_indices`, `tests/unit/test_router/test_router.py::test_global_wildcard_pattern_router_evicts_stale_entry_on_upsert_and_delete`, `tests/unit/test_router/test_router.py::test_team_wildcard_credentials_not_usable_after_delete_deployment` | index and pattern repair |
| [RDEPLOY-060] | `tests/unit/test_router/test_router_helper_utils.py::test_is_auto_router_deployment`, `tests/unit/router_strategy/adaptive_router/test_router_dispatch.py::test_auto_router_check_excludes_adaptive_router_prefix` | classification |
| [RDEPLOY-061] | `tests/unit/test_router/test_router_helper_utils.py::test_init_auto_router_deployment_duplicate_model_name`, `tests/unit/router_strategy/adaptive_router/test_router_dispatch.py::test_init_adaptive_router_rejects_duplicate_model_name` | duplicate rejection |
| [RDEPLOY-064] | `tests/unit/test_router/test_router_helper_utils.py::test_init_auto_router_deployment_success` | semantic router arguments |
| [RDEPLOY-066] | `tests/unit/router_strategy/test_complexity_router.py::test_absent_deployment_config_still_requires_explicit_default` | default-model error |
| [RDEPLOY-067] | `tests/unit/test_router/test_router.py::test_complexity_router_registers_affinity_callback_for_deployment_pin` | affinity check registration |
| [RDEPLOY-068] | `tests/unit/router_strategy/test_quality_router.py::TestRouterQualityDeploymentMethods` | quality router registration |
| [RDEPLOY-070] | `tests/unit/router_strategy/adaptive_router/test_router_dispatch.py::test_init_adaptive_router_reads_cost_from_litellm_params`, `tests/unit/router_strategy/adaptive_router/test_router_dispatch.py::test_two_adaptive_routers_can_coexist_on_one_router` | cost source, multiple routers |
| [RDEPLOY-072] | `tests/unit/router_strategy/adaptive_router/test_router_dispatch.py::test_finalize_adaptive_router_if_configured_initializes_and_is_idempotent` | idempotent deferred pass |
| [RDEPLOY-073] | `tests/unit/router_strategy/adaptive_router/test_router_dispatch.py::test_finalize_prunes_stale_adaptive_router_hooks_from_callbacks` | one hook after re-construction |
| [RDEPLOY-076] | `tests/unit/router_strategy/test_complexity_router.py::test_heuristic_v2_limit_is_resolved_on_every_registration`, `tests/unit/router_strategy/test_complexity_router.py::test_auto_router_capability_violation_frees_the_slot_of_the_router_being_edited`, `tests/unit/router_strategy/test_complexity_router.py::test_heuristic_v2_ceiling_raises_without_ignore_invalid_deployments` | capability ceiling |
| [RDEPLOY-077] | `tests/unit/router_strategy/test_complexity_router.py::test_config_deployments_excludes_db_rows` | config rows only |
| [RDEPLOY-081] | `tests/unit/test_router_model_cost_isolation.py::test_backend_cost_map_keys_matches_what_registration_writes`, `tests/unit/test_router_model_cost_isolation.py::test_register_deployment_in_model_cost_writes_both_key_families` | backend keys, filtered shared row |
| [RDEPLOY-082] | `tests/unit/test_router_model_cost_isolation.py::test_strategy_router_alias_pricing_never_enters_model_cost` | alias pricing stripped |
| [RDEPLOY-083] | `tests/unit/test_router_model_cost_isolation.py::test_deployment_model_cost_payload_folds_in_litellm_params_pricing`, `tests/unit/test_router/test_router_helper_utils.py::test_register_deployment_pricing_direct_call` | payload contents |
| [RDEPLOY-085] | `tests/unit/test_router_model_cost_isolation.py::test_replay_model_cost_registrations_survives_a_malformed_deployment`, `tests/unit/test_router_model_cost_isolation.py::test_a_config_deployment_dropped_by_a_stale_cost_map_comes_back_on_reload`, `tests/unit/test_router_model_cost_isolation.py::test_a_config_deployment_dropped_for_a_permanent_reason_is_not_retried_on_reload` | replay and retry |
| [RDEPLOY-086] | `tests/unit/test_router_model_cost_isolation.py::test_deleted_deployments_are_not_replayed_onto_later_reloads`, `tests/unit/test_router_model_cost_isolation.py::test_a_discarded_router_stops_contributing_to_later_reloads` | live-router replay |
| [RDEPLOY-092] | `tests/unit/test_router/test_router_helper_utils.py::test_sync_deployment_budget_config`, `tests/unit/test_router/test_router_helper_utils.py::test_sync_deployment_budget_config_clears_removed_limits` | budget sync |
| [RDEPLOY-097] | `tests/unit/test_router/test_router.py::test_get_deployment_credentials_returns_none_for_blocked_deployment` | blocked credentials hidden |
| [RDEPLOY-099] | `tests/unit/test_router/test_router.py::test_get_credential_deployment_is_the_deployment_credentials_resolve_to`, `tests/unit/test_router/test_router.py::test_get_credential_deployment_skips_a_paused_deployment`, `tests/unit/test_router/test_router.py::test_get_team_public_name_deployment_only_resolves_the_owning_team` | resolution order |
| [RDEPLOY-100] | `tests/unit/test_router/test_router.py::test_get_wildcard_deployment_usable_by_team_prefers_the_team_pattern`, `tests/unit/test_router/test_router.py::test_get_deployment_credentials_with_provider_skips_other_team_wildcard` | wildcard credentials |
| [RDEPLOY-102] | `tests/unit/test_router/test_router.py::test_get_deployment_credentials_with_provider_resolves_credential_name` | credential-name merge |
| [RDEPLOY-103] | `tests/unit/test_router/test_router.py::test_router_get_deployment_credentials_with_provider` | provider derivation |
| [RDEPLOY-105] | `tests/unit/test_router_model_cost_isolation.py::test_discovery_refreshes_other_endpoints_while_one_is_pending` | concurrent probes |
| [RDEPLOY-107] | `tests/unit/test_router_model_cost_isolation.py::test_discovery_preserves_input_overrides_and_survives_outages` | headers, skipped deployments |
| [RDEPLOY-108] | `tests/unit/test_router_model_cost_isolation.py::test_discovered_limits_are_isolated_overridable_and_refreshable` | `/v1/models` path, card id without provider prefix |
| [RDEPLOY-211] | `tests/unit/test_router_model_cost_isolation.py::test_discovery_refreshes_other_endpoints_while_one_is_pending`, `tests/unit/test_router_model_cost_isolation.py::test_discovery_preserves_input_overrides_and_survives_outages` | `max_model_len` 2048 gives `(2048, 2048)`; configured input 1024 with context 4096 gives `(1024, 4096)` |
| [RDEPLOY-109] | `tests/unit/test_router_model_cost_isolation.py::test_discovery_discards_metadata_for_a_replaced_deployment`, `tests/unit/test_router_model_cost_isolation.py::test_discovered_limits_expire_after_the_last_successful_refresh` | identity check, 600 s expiry |
| [RDEPLOY-111] | `tests/unit/test_router_model_cost_isolation.py::test_discovery_is_isolated_across_routers_and_reused_ids` | per-router isolation |
| [RDEPLOY-112] | `tests/unit/test_router/test_router.py::test_get_model_listing_info_prefers_base_model_over_litellm_params_model`, `tests/unit/test_router/test_router.py::test_get_model_listing_info_dedupes_interchangeable_deployments` | cost-map keys |
| [RDEPLOY-113] | `tests/unit/test_router/test_router.py::test_widest_configured_limit_ignores_absent_and_malformed_values` | widest limits |
| [RDEPLOY-114] | `tests/unit/test_router/test_router.py::test_get_configured_token_limits_treats_malformed_values_as_absent`, `tests/unit/test_router/test_router.py::test_get_configured_token_limits_skips_wildcard_pattern_matching` | token-limit coercion |
| [RDEPLOY-115] | `tests/unit/test_router/test_router.py::test_get_configured_mode_treats_malformed_values_as_absent` | mode accessor |
| [RDEPLOY-116] | `tests/unit/test_router/test_router.py::test_routable_model_group_is_the_alias_target_else_the_name_itself` | alias target |
| [RDEPLOY-117] | `tests/unit/test_router/test_router.py::test_upstream_model_and_service_tiers_are_read_off_the_deployments_the_team_can_route_to` | routable set per team |
| [RDEPLOY-118] | `tests/unit/test_router/test_router.py::test_get_configured_service_tiers_reads_only_the_deployments_a_request_can_route_to` | service tiers |
| [RDEPLOY-124] | `tests/unit/test_router/test_router.py::test_get_router_model_info_does_not_wipe_cached_pricing`, `tests/unit/test_router/test_router.py::test_get_router_model_info_keeps_explicit_pricing_overrides` | merge precedence |
| [RDEPLOY-125] | `tests/unit/test_router_model_cost_isolation.py::test_router_capacity_widens_only_for_an_exact_base_model_entry_of_the_same_model`, `tests/unit/test_router_model_cost_isolation.py::test_router_capacity_never_narrows_to_a_smaller_base_model_window` | base-model widening |
| [RDEPLOY-129] | `tests/unit/test_router/test_router.py::test_get_deployment_model_info_base_model_merge_priority` | merge order |
| [RDEPLOY-130] | `tests/unit/test_router/test_router.py::test_model_group_info_cost_none_for_unpriced_deployment_but_zero_when_declared` | unpriced reports `None` |
| [RDEPLOY-131] | `tests/unit/test_router/test_router.py::test_get_model_group_info_include_hidden_resolves_a_hidden_alias`, `tests/unit/test_router/test_router.py::test_get_model_group_info_prices_an_alias_chain_from_the_group_it_routes_to` | alias handling |
| [RDEPLOY-133] | `tests/unit/test_router/test_router.py::test_get_model_list_of_routed_group_falls_back_to_the_wildcard_route_serving_it`, `tests/unit/test_router/test_router.py::test_model_group_info_description_from_model_info` | members and description |
| [RDEPLOY-135] | `tests/unit/test_router/test_router.py::test_model_group_info_cost_from_db_model_info`, `tests/unit/test_router/test_router.py::test_model_group_info_db_fallback_with_stringified_cost_values` | synthesized fallback |
| [RDEPLOY-138] | `tests/unit/test_router/test_router.py::test_model_group_info_with_stringified_cost_values`, `tests/unit/test_router/test_router.py::test_model_group_info_surfaces_supports_parallel_function_calling` | max costs, OR'd flags |
| [RDEPLOY-139] | `tests/unit/test_router/test_router.py::test_model_group_info_fast_mode_requires_every_deployment` | fast mode AND |
| [RDEPLOY-140] | `tests/unit/test_router/test_router.py::test_model_group_info_intersects_supported_reasoning_efforts`, `tests/unit/test_router/test_router.py::test_model_group_info_reasoning_efforts_are_unknown_when_any_deployment_is_off_the_map` | effort intersection |
| [RDEPLOY-143] | `tests/unit/test_router/test_router.py::test_cached_get_model_group_info`, `tests/unit/test_router/test_router.py::test_cached_model_info_lookups_match_uncached_and_reset_on_model_list_change` | memo and invalidation |
| [RDEPLOY-145] | `tests/unit/test_router/test_router_helper_utils.py::test_get_model_group_io_token_usage_sums_across_deployments`, `tests/unit/test_router/test_router_helper_utils.py::test_get_model_group_io_token_usage_no_deployments_returns_none` | ITPM/OTPM sums |
| [RDEPLOY-146] | `tests/unit/test_router/test_router_helper_utils.py::test_get_remaining_model_group_usage_merges_io_and_tpm_headers` | header arithmetic |
| [RDEPLOY-147] | `tests/unit/test_router/test_router_helper_utils.py::test_set_response_headers`, `tests/unit/test_router/test_router_helper_utils.py::test_set_response_headers_wraps_bare_async_generator`, `tests/unit/test_router/test_router_helper_utils.py::test_set_response_headers_dict_anthropic_messages_response` | response shapes |
| [RDEPLOY-148] | `tests/unit/test_router/test_router_helper_utils.py::test_set_response_headers_native_token_header_does_not_suppress_io_headers` | native header wins |
| [RDEPLOY-155] | `tests/unit/test_router/test_router.py::test_get_candidate_model_ids_for_route_covers_model_name_and_pattern` | candidate ids |
| [RDEPLOY-156] | `tests/unit/test_router/test_router.py::test_deployment_ids_stringifies_ids_and_skips_entries_without_a_model_info_id` | id stringification |
| [RDEPLOY-158] | `tests/unit/test_router/test_router_helper_utils.py::test_resolve_model_name_from_model_id`, `tests/unit/test_router/test_router_helper_utils.py::test_resolve_model_name_from_model_id_keeps_a_wildcard_name_only_for_the_ids_provider` | resolution steps |
| [RDEPLOY-161] | `tests/unit/test_router/test_router.py::test_map_team_model_without_model_picks_deployment_serving_the_requested_provider`, `tests/unit/test_router/test_router.py::test_map_team_model_with_explicit_model_ignores_requested_provider` | provider pick |
| [RDEPLOY-163] | `tests/unit/test_router/test_router.py::test_get_all_deployments_with_team_id`, `tests/unit/test_router/test_router.py::test_multiregion_team_deployments_unique_model_names` | team scan path |
| [RDEPLOY-166] | `tests/unit/test_router/test_router.py::test_get_fully_blocked_model_names_keeps_name_when_partial_blocked` | partial block visible |
| [RDEPLOY-168] | `tests/unit/test_router/test_router.py::test_async_get_fully_unhealthy_model_names_includes_team_alias`, `tests/unit/test_router/test_router.py::test_async_get_fully_unhealthy_model_names_noop_with_allowed_fails_policy`, `tests/unit/test_router/test_router.py::test_async_get_fully_unhealthy_model_names_ignores_stale_state` | unhealthy hiding |
| [RDEPLOY-170] | `tests/unit/test_router/test_router.py::test_get_model_list_from_model_alias_should_not_iterate_for_non_alias_lookup` | non-alias fast path |
| [RDEPLOY-150] | `tests/unit/test_router/test_router.py::TestRouterIndexManagement` | only tests call the index builders |

## Suspected defects
Behavior that looks unintended. The normative sections above state what the code does; each claim here says why it looks wrong and who is affected.

- [RDEPLOY-205] {confirmed} `litellm/router.py:10552-10568`, `litellm/router.py:10713-10718` `set_model_list` does not reset `pattern_router`, `adaptive_routers`, `provider_default_deployment_ids` or `deployment_names` ([RDEPLOY-003]). Looks unintended because it resets every other registry and index ([RDEPLOY-002]). Impact: a second call on a live router keeps serving wildcard requests from dropped deployments and duplicates re-listed wildcard entries; today only tests call it twice ([RDEPLOY-199]).
- [RDEPLOY-206] {confirmed} `litellm/router.py:10398-10414` Re-syncing adaptive hooks removes every `AdaptiveRouterPostCallHook` from the global callback lists, including those of other routers, and re-adds only this router's ([RDEPLOY-073]). Looks unintended because each router owns only its own hooks. Impact: constructing another router from a model list (for example a per-request `user_config` router in the proxy) silently stops adaptive-router feedback for every other router in the process.
- [RDEPLOY-207] {confirmed} `litellm/router.py:10820-10851` `add_deployment`, and so `upsert_deployment`, skip the PTU checks, the access-window check, the environment gate, `tag_regex` validation, `os.environ/` expansion and organization-list expansion that `set_model_list` applies ([RDEPLOY-042]). Looks unintended because the same row is accepted or rejected depending on the path that loads it ([RDEPLOY-204], [CFG-185]). Impact: deployments that the proxy adds at runtime can be active in the wrong environment, carry unexpanded `os.environ/` strings, or carry a malformed `access_windows` that fails later at selection ([LIMITS-013]).
- [RDEPLOY-208] {confirmed} `litellm/router.py:10611-10623` An `organization` list expands to one deployment per organization, all sharing one id ([RDEPLOY-009]). Looks unintended because the id is the key for cooldowns, budgets and lookups ([RDEPLOY-200]). Impact: a failure on one organization's deployment cools down all of them, and id lookups find only the last one.
- [RDEPLOY-209] {confirmed} `litellm/router.py:11003-11013`, `litellm/router.py:11038-11039` When `ignore_invalid_deployments` is false and an upsert's re-add fails, the old row has already been removed and is not restored ([RDEPLOY-051]). Looks unintended because the `ignore_invalid_deployments=True` path restores it ([RDEPLOY-050]). Impact: an invalid edit of a model removes the working deployment from routing.
- [RDEPLOY-210] {confirmed} `litellm/router.py:12206-12220` A model group's `supported_reasoning_efforts` becomes `None` (unknown) as soon as any member's levels are unknown ([RDEPLOY-140]). Looks unintended because the shared intersection helper documents that unknown deployments never narrow a group ([CONTRACTS-115], [CONTRACTS-152]). Impact: one unmapped deployment hides the whole group's reasoning-effort levels from clients.
- [RDEPLOY-215] {confirmed} `litellm/router.py:11014-11037`, `litellm/router.py:11048-11049` When an upsert fails after `add_deployment` appended the new row, as in the deferred adaptive pass or the budget sync, the warning says `Dropping it`, yet the failed row stays stored and routable under the id. The restore is skipped because the id is present, so the previously serving deployment is lost ([RDEPLOY-049], [RDEPLOY-051]). Looks unintended because the warning text and the restore helper's docstring both promise that the previous configuration keeps serving. Impact: an invalid edit of an adaptive-router deployment, made through the proxy, which always sets `ignore_invalid_deployments=True` ([CFG-092]),, replaces a working deployment with one that has no registered adaptive router.
- [RDEPLOY-216] {confirmed} `litellm/router.py:2675-2696`, `litellm/litellm_core_utils/logging_callback_manager.py:297-337`, `litellm/router.py:9739-9748` A second `Router` whose pinning complexity router needs a deployment-affinity check keeps the new check only in its own `optional_callbacks`. The global list already holds an equal-keyed check from the first router ([RDEPLOY-214]). Looks unintended because the check carries per-router state (cache, `model_group_affinity_config`, priority test) that the dedup key ignores, while the filter runs only the global list. Impact: the second router's affinity pins are read and written in the first router's cache, under the first router's per-group config and priority test.
