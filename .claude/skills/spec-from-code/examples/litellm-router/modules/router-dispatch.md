---
kind: module
module: router-dispatch
prefix: RDISP
commit: 93b79d2587d186fb7266556a34a22d03f187a3da
status: draft
scope:
  - litellm/router.py:6606-9865
---
# Endpoint dispatch factories and the retry/fallback loop (RDISP)

## Purpose
This module turns plain `litellm.*` SDK functions into routed `Router` endpoints and owns the loop that every async routed call runs through. It decides five things:
- Which wrapper a bound endpoint gets (`factory_function`): sync or async, routed through deployments or called directly, and whether `custom_llm_provider` and `client` survive.
- How a failed attempt is retried within the same model group: the count, which errors are retried, and the backoff.
- How the call then falls back to other targets: order levels, weighted intra-group failover, context-window, content-policy and generic fallback chains.
- What the router records about each outcome: success and failure callbacks, per-minute TPM/RPM counters, cooldown triggering, and retry breadcrumbs.
- How a deployment's stable id is derived from its configuration.

It also implements the file, batch, embedding and vector-store-create entry points that do not use the generic factory.

## Scope and boundaries
In scope: `litellm/router.py` lines 6606-9865, the `Router` methods from `_aanthropic_messages_with_streaming_fallbacks` through `_inherit_builtin_service_tier_pricing`. Everything quoted from outside that range is context. It is stated as `{confirmed}` only where that code was read through or the behavior was executed, and as `{inferred}` otherwise.

Out of scope, by owner:
- **router-setup** (`router.py:1-3315`): `Router.__init__`, the `_initialize_*_endpoints` methods that bind factory wrappers to attribute names, registration of this module's callbacks on the global `litellm.*_callback` lists, and `completion`/`acompletion` (see [RSETUP-111], [RSETUP-049], [RSETUP-157], [RSETUP-186]).
- **router-calls** (`router.py:3316-6605`): `_acompletion` and the other per-endpoint `_a*` workers, `_ageneric_api_call_with_fallbacks` and its per-attempt helper, `_update_kwargs_before_fallbacks`, `_update_kwargs_with_deployment`, the stream-recovery iterators, `_asearch_with_fallbacks` and `_aresponses_with_streaming_fallbacks` (see [RCALL-044], [RCALL-116], [RCALL-058], [RCALL-064], [RCALL-001], [RCALL-112], [RCALL-125]).
- **router-selection** (`router.py:13217-16278`): `get_available_deployment`, `async_get_available_deployment`, `async_get_healthy_deployments`, `_common_checks_available_deployment`, `_filter_blocked_deployments`, `get_model_list` and `_get_client` (see [RSELECT-120], [RSELECT-060], [RSELECT-040], [RSELECT-020], [RSELECT-141], [RSELECT-001], [RSELECT-175]).
- **router-deployments** (`router.py:9866-13216`): `get_deployment`, `get_router_model_info`, `set_response_headers`, `get_deployment_credentials_with_provider`, and the pricing registration that calls the pricing helpers specified here (see [RDEPLOY-095], [RDEPLOY-120], [RDEPLOY-147], [RDEPLOY-101], [RDEPLOY-020]).
- **failure-handling** (`router_utils/`): `run_async_fallback`, fallback-chain resolution, the cooldown handlers, the response-header helpers, retry-policy resolution and exception alerting (see [FAILURE-138], [FAILURE-114], [FAILURE-021], [FAILURE-156], [FAILURE-099], [FAILURE-175]).
- **deployment-limits** and **request-targets**: IO-token limits, PTU-share request kwargs, batch and file utilities, and the common utilities (see [LIMITS-083], [LIMITS-029], [TARGETS-123], [TARGETS-136], [TARGETS-114]).

Inbound callers:
- router-setup binds factory wrappers in `__init__` and registers `deployment_callback_on_success`, `sync_deployment_callback_on_success`, `async_deployment_callback_on_failure` and `deployment_callback_on_failure` as global litellm callbacks (`litellm/router.py:1528-1547`). Its sync `completion` calls `function_with_fallbacks`.
- router-calls: every `a*` endpoint calls `async_function_with_fallbacks`. The stream iterators call `async_function_with_fallbacks_common_utils`, `log_retry`, `should_retry_this_error`, `_anthropic_messages_stream_can_fall_back` and `_refusal_fallback_available`. Workers call `make_call` indirectly, `_deployment_slot` and `_should_raise_content_policy_error`.
- router-selection calls `async_callback_filter_deployments`, `_update_usage` and `_get_first_default_fallback`.
- router-deployments calls `generate_model_id` and the pricing-inheritance helpers.
- failure-handling: `run_async_fallback` calls `async_function_with_fallbacks` and `log_retry`.
- The proxy calls `acreate_file`, `acreate_batch`, `aretrieve_batch`, `alist_batches`, `acancel_batch` and `generate_model_id` (`litellm/proxy/batches_endpoints/endpoints.py`, `litellm/proxy/openai_files_endpoints/files_endpoints.py`, `litellm/proxy/proxy_server.py`).

Outbound calls go to router-selection, router-calls, router-deployments, failure-handling, deployment-limits and request-targets. They also go to the litellm SDK functions, the `CustomLogger` hooks registered in `litellm.callbacks`, and `Router.cache` (a `DualCache`).

One method in the range is dead: `_override_vector_store_methods_for_router` has an empty body ([RDISP-073]).

## Public surface
Endpoints and hooks defined in the range. Kinds: `method` is a public method, `hook` is a method registered as a global litellm callback, and `internal` is an underscore method called by other router modules or by tests.

| Entry point | Kind | Inputs | Outputs | Errors | Claims |
|---|---|---|---|---|---|
| `Router.factory_function(original_function, call_type="assistants")` | method | SDK callable, call type literal | sync or async wrapper | none at bind time | [RDISP-001]-[RDISP-027] |
| factory-bound attributes (table below) | runtime-bound methods | SDK kwargs | SDK result, or `None` for unmatched call types | whatever the routed or direct call raises | [RDISP-002]-[RDISP-027] |
| `Router.embedding(model, input, is_async=False, **kwargs)` | method | group name, text or list | `EmbeddingResponse` | last retry or fallback error | [RDISP-052]-[RDISP-054] |
| `Router.aembedding(model, input, is_async=True, **kwargs)` | async method | as above | `EmbeddingResponse` | as above, plus an alert task | [RDISP-055], [RDISP-056] |
| `Router.acreate_file(model, **kwargs)` | async method | group, `file`, `purpose` | `OpenAIFileObject` with `model_file_id_mapping` | `Exception` messages listed in Error handling | [RDISP-057]-[RDISP-069] |
| `Router.avector_store_create(model, **kwargs)` | async method | group or `None` | vector store object | SDK or selection error | [RDISP-070]-[RDISP-072] |
| `Router.acreate_batch(model, **kwargs)` | async method | group, batch params | `LiteLLMBatch` | last error | [RDISP-074], [RDISP-075] |
| `Router.aretrieve_batch(model=None, **kwargs)` | async method | optional group, `batch_id` | first `LiteLLMBatch` found | first collected error or `Exception` | [RDISP-079]-[RDISP-084] |
| `Router.acancel_batch(model, **kwargs)` | async method | group or deployment id, `batch_id` | `LiteLLMBatch` | last error | [RDISP-076]-[RDISP-078] |
| `Router.alist_batches(model, **kwargs)` | async method | group | merged list dict | `Exception("Router not yet initialized.")` | [RDISP-085]-[RDISP-087] |
| `Router.async_function_with_fallbacks(*args, **kwargs)` | async method | `model`, `original_function`, request kwargs | response with `x-litellm-attempted-fallbacks` | original exception | [RDISP-090]-[RDISP-096] |
| `Router.async_function_with_fallbacks_common_utils(e, disable_fallbacks, fallbacks, context_window_fallbacks, content_policy_fallbacks, model_group, args, kwargs, include_fallback_errors=False)` | async method | failed exception and request | fallback response | original exception (or the walk's error, [RDISP-105]) | [RDISP-100]-[RDISP-119] |
| `Router.function_with_fallbacks(*args, **kwargs)` | method | as async | as async | as async | [RDISP-165] |
| `Router.async_function_with_retries(*args, **kwargs)` | async method | `original_function`, `model`, `num_retries`, ... | response with retry headers | latest error | [RDISP-130]-[RDISP-147] |
| `Router.make_call(original_function, *args, **kwargs)` | async method | callable and kwargs | processed response | callable's error | [RDISP-150] |
| `Router.should_retry_this_error(error, healthy_deployments, all_deployments, context_window_fallbacks, content_policy_fallbacks, regular_fallbacks)` | method | error and context | `True` | re-raises `error` | [RDISP-155]-[RDISP-158] |
| `Router.log_retry(kwargs, e)` | method | request kwargs, exception | same kwargs, mutated | `KeyError` when no metadata bucket | [RDISP-200]-[RDISP-206] |
| `Router.deployment_callback_on_success(kwargs, completion_response, start_time, end_time)` | async hook | logging kwargs | TPM key or `None` | none (swallowed) | [RDISP-170]-[RDISP-174] |
| `Router.sync_deployment_callback_on_success(...)` | hook | logging kwargs | `"<id>:successes"` key or `None` | `KeyError` without `litellm_params` | [RDISP-187] |
| `Router.deployment_callback_on_failure(...)` | hook | logging kwargs with `exception` | `bool` (cooldown applied) | re-raises internal errors | [RDISP-190]-[RDISP-196] |
| `Router.async_deployment_callback_on_failure(...)` | async hook | logging kwargs | `None` | `KeyError` without `litellm_params.metadata` | [RDISP-197] |
| `Router.increment_deployment_usage_for_response(response, request_kwargs)` | async method | response, request kwargs | `None` | none (swallowed) | [RDISP-177]-[RDISP-179] |
| `Router.routing_strategy_pre_call_checks(deployment)` | method | deployment dict | `None` | callback errors | [RDISP-215] |
| `Router.async_routing_strategy_pre_call_checks(deployment, parent_otel_span, logging_obj=None)` | async method | deployment dict | `None` | `RateLimitError` or other callback error | [RDISP-216], [RDISP-217] |
| `Router.async_callback_filter_deployments(model, healthy_deployments, messages, parent_otel_span, request_kwargs=None, logging_obj=None)` | async method | candidate list | filtered list | callback error | [RDISP-219] |
| `Router.async_admit_deployment_turn(model_group, opened_on, request_kwargs)` | async method | deployment snapshot | `None` | `RateLimitError` | [RDISP-220]-[RDISP-224] |
| `Router.generate_model_id(model_group, litellm_params)` | static method | group, params dict | 64-char lowercase hex | none | [RDISP-240]-[RDISP-242] |
| `_generic_api_call_with_fallbacks` | internal | `model`, `original_function`, kwargs | SDK result | SDK or selection error | [RDISP-047]-[RDISP-051] |
| `_dispatch_generic_call_type`, `_aanthropic_messages_with_streaming_fallbacks` | internal | call type, function | result or stream | chain error | [RDISP-044]-[RDISP-046] |
| `_init_vector_store_api_endpoints`, `_init_containers_api_endpoints`, `_init_responses_api_endpoints`, `_init_interactions_api_endpoints`, `_init_managed_agents_api_endpoints`, `_pass_through_assistants_endpoint_factory`, `_pass_through_moderation_endpoint_factory` | internal | per-family kwargs | SDK result | see claims | [RDISP-030]-[RDISP-043] |
| `_maybe_run_weighted_failover` | internal | exception, group | response or `None` | non-API errors | [RDISP-120]-[RDISP-124] |
| `_deployment_ids_to_skip_on_retry(exception, already_skipped)` | internal static | exception | tuple of ids | none | [RDISP-148] |
| `_time_to_sleep_before_retry(e, remaining_retries, num_retries, healthy_deployments, all_deployments)` | internal | error, counts | seconds | none | [RDISP-160]-[RDISP-162] |
| `_handle_mock_testing_fallbacks`, `_handle_mock_testing_rate_limit_error` | internal | kwargs | `None` | mock exceptions | [RDISP-151], [RDISP-152] |
| `_get_healthy_deployments`, `_async_get_healthy_deployments` | internal | group | (healthy, all) | none | [RDISP-210]-[RDISP-213] |
| `_deployment_slot` | internal async context manager | deployment | slot | `RateLimitError` (429) | [RDISP-218] |
| `_has_default_fallbacks`, `_get_first_default_fallback`, `_get_fallback_model_group_for_lookup_groups`, `_has_content_policy_fallback`, `_refusal_fallback_available`, `_anthropic_messages_order_levels`, `_anthropic_messages_stream_can_fall_back`, `_should_raise_content_policy_error`, `_should_raise_anthropic_refusal_error` | internal | group, kwargs | bool, name or list | none | [RDISP-230]-[RDISP-238] |
| `_get_metadata_variable_name_from_kwargs`, `_update_usage` | internal | kwargs or id | bucket name or count | none | [RDISP-207], [RDISP-208] |
| `_json_default_stable_id`, `_inherit_builtin_cache_pricing`, `_cost_map_backend_model`, `_inherit_builtin_service_tier_pricing` | internal static | model info | in-place fill | none | [RDISP-243]-[RDISP-247] |

Runtime-bound endpoint names. Each is assigned `self.<name> = self.factory_function(<sdk fn>, call_type=<ct>)` in router-setup ([RSETUP-111], [RSETUP-112]), so no `def` exists for it. The dispatch column points to the claim that governs the wrapper.

| Bound names | Bound at | call_type | Wrapper | Dispatch claim |
|---|---|---|---|---|
| `acreate_assistants`, `adelete_assistant`, `aget_assistants`, `acreate_thread`, `aget_thread`, `a_add_message`, `aget_messages`, `arun_thread` | `litellm/router.py:2274-2283` | `assistants` (default) | async | [RDISP-008] |
| `amoderation` | `litellm/router.py:2287` | `moderation` | async | [RDISP-009] |
| `aanthropic_messages`, `anthropic_messages` (both async) | `litellm/router.py:2288-2289` | `anthropic_messages` | async | [RDISP-014] |
| `agenerate_content`, `agenerate_content_stream`, `aimage_edit`, `afile_list` (call type `alist_files`), `_arealtime`, `_aresponses_websocket`, `acreate_fine_tuning_job`, `acancel_fine_tuning_job`, `alist_fine_tuning_jobs`, `aretrieve_fine_tuning_job`, `aocr`, `adecisions`, `asystemone`, `avideo_generation`, `avideo_list`, `avideo_status`, `avideo_content`, `avideo_remix`, `avideo_create_character`, `avideo_get_character`, `avideo_edit`, `avideo_extension`, `acreate_skill`, `alist_skills`, `aget_skill`, `adelete_skill` | `litellm/router.py:2290-2327`, `litellm/router.py:2443-2517`, `litellm/router.py:2549-2552` | same as name | async | [RDISP-014] |
| `aadapter_generate_content` | `litellm/router.py:2291-2293` | `aadapter_generate_content` | async, unmatched | [RDISP-023] |
| `aresponses` | `litellm/router.py:2294` | `aresponses` | async | [RDISP-012] |
| `afile_delete`, `afile_content` | `litellm/router.py:2295-2296` | same | async | [RDISP-019] |
| `responses`, `generate_content`, `generate_content_stream`, `ocr`, `search`, `decisions`, `systemone`, `video_generation`, `video_list`, `video_status`, `video_content`, `video_remix`, `create_container`, `list_containers`, `retrieve_container`, `delete_container` | `litellm/router.py:2297`, `litellm/router.py:2444-2506`, `litellm/router.py:2535-2541` | same | sync | [RDISP-002] |
| `aget_responses`, `acancel_responses`, `acompact_responses`, `adelete_responses`, `alist_input_items` | `litellm/router.py:2298-2302` | same | async | [RDISP-017] |
| `acreate_realtime_client_secret`, `arealtime_calls`, `acreate_realtime_transcription_session` | `litellm/router.py:2304-2310` | same | async | [RDISP-013] |
| `allm_passthrough_route` | `litellm/router.py:2328-2330` | same | async | [RDISP-016] |
| `avector_store_search`, `avector_store_retrieve`, `avector_store_list`, `avector_store_update`, `avector_store_delete` | `litellm/router.py:2350-2359` | same | async | [RDISP-018] |
| `vector_store_search`, `vector_store_create`, `vector_store_retrieve`, `vector_store_list`, `vector_store_update`, `vector_store_delete` | `litellm/router.py:2351-2360` | same | sync | [RDISP-003], [RDISP-004] |
| `avector_store_file_create`, `avector_store_file_list`, `avector_store_file_retrieve`, `avector_store_file_content`, `avector_store_file_update`, `avector_store_file_delete` | `litellm/router.py:2397-2431` | same | async | [RDISP-011] |
| `vector_store_file_create`, `vector_store_file_list`, `vector_store_file_retrieve`, `vector_store_file_content`, `vector_store_file_update`, `vector_store_file_delete` | `litellm/router.py:2400-2432` | same | sync | [RDISP-005] |
| `asearch` | `litellm/router.py:2461` | `asearch` | async | [RDISP-010] |
| `video_create_character`, `video_get_character`, `video_edit`, `video_extension` | `litellm/router.py:2510-2516` | same | async, unmatched | [RDISP-024] |
| `acreate_container`, `alist_containers`, `aretrieve_container`, `adelete_container` | `litellm/router.py:2534-2540` | same | async | [RDISP-015] |
| `alist_container_files`, `aupload_container_file`, `aretrieve_container_file`, `adelete_container_file`, `aretrieve_container_file_content` (setattr loop over `litellm/containers/endpoints.json`) | `litellm/router.py:2543-2545` | same | async | [RDISP-015] |
| `list_container_files`, `upload_container_file`, `retrieve_container_file`, `delete_container_file`, `retrieve_container_file_content` (same setattr loop) | `litellm/router.py:2543-2545` | same | async, unmatched | [RDISP-026] |
| `acreate_interaction`, `create_interaction`, `aget_interaction`, `adelete_interaction`, `acancel_interaction` | `litellm/router.py:2565-2571` | same | async | [RDISP-020], [RDISP-027] |
| `get_interaction`, `delete_interaction`, `cancel_interaction` | `litellm/router.py:2568-2572` | same | async, unmatched | [RDISP-025] |
| `acreate_agent`, `alist_agents`, `aget_agent`, `adelete_agent`, `alist_agent_versions` | `litellm/router.py:2587-2595` | same | async | [RDISP-021] |
| `create_agent`, `list_agents`, `get_agent`, `delete_agent`, `list_agent_versions` | `litellm/router.py:2588-2596` | same | sync | [RDISP-006] |

`avector_store_create` is not rebound by the factory, so the class method [RDISP-070] stays in effect.

## Behaviors

### Endpoint factory (`factory_function`)
- [RDISP-001] {confirmed} `litellm/router.py:7471-7474`, `litellm/router.py:7592`, `litellm/router.py:7602`, `litellm/router.py:7628-7630`, `litellm/router.py:7668-7670`, `litellm/router.py:7690-7692`, `litellm/router.py:7711-7714`, `litellm/router.py:7890` `factory_function(original_function, call_type="assistants")` only builds and returns a wrapper around `original_function`; it calls nothing at bind time, and `call_type` alone decides whether the wrapper is synchronous or asynchronous.
- [RDISP-002] {confirmed} `litellm/router.py:7602-7628` For `call_type` in {`responses`, `generate_content`, `generate_content_stream`, `ocr`, `search`, `decisions`, `systemone`, `video_generation`, `video_list`, `video_status`, `video_content`, `video_remix`, `create_container`, `list_containers`, `retrieve_container`, `delete_container`}, the wrapper is synchronous and forwards every keyword except `custom_llm_provider` and `client` to the synchronous generic call ([RDISP-047]), so a caller-supplied `custom_llm_provider` or `client` is silently dropped.
- [RDISP-003] {confirmed} `litellm/router.py:7630-7668` The synchronous vector-store wrappers (`vector_store_search|create|retrieve|list|update|delete`) behave as follows:
  - A non-empty `custom_llm_provider` argument is added to the kwargs unless the kwargs already contain that key.
  - `client` is dropped.
  - When the kwargs contain a truthy `model`, the call goes through the synchronous generic call ([RDISP-047]). Otherwise `original_function` is called directly.
- [RDISP-004] {confirmed} `litellm/router.py:7649-7665` For `vector_store_search` the forwarded kwargs also carry `_direct_vector_store_embedding_executor`, a `RouterVectorStoreEmbeddingExecutor` bound to this router and to the request metadata taken from the kwargs. The model-less direct call also receives the keyword `router` set to this router instance, which overrides any caller-supplied `router` key.
- [RDISP-005] {confirmed} `litellm/router.py:7670-7690` The synchronous vector-store-file wrappers (`vector_store_file_create|list|retrieve|content|update|delete`) call `original_function(custom_llm_provider=..., client=..., **kwargs)` directly. They do no deployment selection, retries or fallbacks.
- [RDISP-006] {confirmed} `litellm/router.py:7692-7711` The synchronous managed-agent wrappers (`create_agent`, `list_agents`, `get_agent`, `delete_agent`, `list_agent_versions`) take `custom_llm_provider` from the argument when the kwargs lack it, default it to `"gemini"` when it is still absent, drop `client`, and call `original_function` directly.
- [RDISP-007] {confirmed} `litellm/router.py:7713-7719`, `litellm/router.py:7877-7890` Every other `call_type` gets an `async` wrapper that dispatches on the first matching branch below ([RDISP-008]-[RDISP-021]). A `call_type` that matches no branch makes the wrapper return `None` without calling `original_function` and without raising.
- [RDISP-008] {confirmed} `litellm/router.py:7719-7725` `assistants` goes to the assistants pass-through ([RDISP-041]), which receives both `custom_llm_provider` and `client`.
- [RDISP-009] {confirmed} `litellm/router.py:7726-7729` `moderation` goes to the moderation pass-through ([RDISP-042], [RDISP-043]). `custom_llm_provider` and `client` are dropped.
- [RDISP-010] {confirmed} `litellm/router.py:7730-7734` `asearch` (and `search`, which is unreachable here because of [RDISP-022]) goes to the search-tool fallback chain owned by router-calls ([RCALL-112], [TARGETS-205]). `custom_llm_provider` and `client` are dropped.
- [RDISP-011] {confirmed} `litellm/router.py:7735-7747` The six async vector-store-file call types go to the vector-store router ([RDISP-030], [RDISP-031]) with `custom_llm_provider`. `client` is dropped.
- [RDISP-012] {confirmed} `litellm/router.py:7748-7752` `aresponses` goes to the Responses API streaming-fallback chain owned by router-calls ([RCALL-125], [RCALL-127]). `custom_llm_provider` and `client` are dropped.
- [RDISP-013] {confirmed} `litellm/router.py:7753-7762` `acreate_realtime_client_secret`, `arealtime_calls` and `acreate_realtime_transcription_session` go to the generic async fallback chain with `client` forwarded and `custom_llm_provider` dropped.
- [RDISP-014] {confirmed} `litellm/router.py:7763-7797` These call types go through [RDISP-044] with both `custom_llm_provider` and `client` dropped: `anthropic_messages`, `_arealtime`, `_aresponses_websocket`, the four fine-tuning types, `alist_files`, `aimage_edit`, `agenerate_content`, `agenerate_content_stream`, `aocr`, `ocr`, `adecisions`, `asystemone`, the nine `avideo_*` types, and the four skill types.
- [RDISP-015] {confirmed} `litellm/router.py:7798-7813` The async container and container-file call types (`acreate_container`, `alist_containers`, `aretrieve_container`, `adelete_container`, `aupload_container_file`, `alist_container_files`, `aretrieve_container_file`, `adelete_container_file`, `aretrieve_container_file_content`) go to the container router ([RDISP-032]-[RDISP-035]) with `custom_llm_provider`. `client` is dropped.
- [RDISP-016] {confirmed} `litellm/router.py:7814-7821` `allm_passthrough_route` puts a truthy `client` into the kwargs and runs the generic async fallback chain with `passthrough_on_no_deployment=True`.
- [RDISP-017] {confirmed} `litellm/router.py:7822-7832` `aget_responses`, `acancel_responses`, `acompact_responses`, `adelete_responses` and `alist_input_items` go to the response-id router ([RDISP-036]). `custom_llm_provider` and `client` are dropped.
- [RDISP-018] {confirmed} `litellm/router.py:7833-7857` The six async vector-store call types go to the vector-store router ([RDISP-030], [RDISP-031]) with `custom_llm_provider` and `call_type`. `avector_store_search` also adds the `_direct_vector_store_embedding_executor` kwarg described in [RDISP-004].
- [RDISP-019] {confirmed} `litellm/router.py:7858-7864` `afile_delete` and `afile_content` run the generic async fallback chain with both `custom_llm_provider` and `client` forwarded.
- [RDISP-020] {confirmed} `litellm/router.py:7865-7876` `acreate_interaction`, `create_interaction`, `aget_interaction`, `adelete_interaction` and `acancel_interaction` go to the interactions router ([RDISP-037]-[RDISP-039]) with `custom_llm_provider`.
- [RDISP-021] {confirmed} `litellm/router.py:7877-7888` `acreate_agent`, `alist_agents`, `aget_agent`, `adelete_agent` and `alist_agent_versions` go to the managed-agents router ([RDISP-040]) with `custom_llm_provider`.
- [RDISP-022] {confirmed} `litellm/router.py:7602-7619`, `litellm/router.py:7730`, `litellm/router.py:7775-7776` The synchronous call-type list is checked before the async branches, so `search` and `ocr` always get the synchronous wrapper even though they also appear in async branches.
- [RDISP-023] {confirmed} `litellm/router.py:2291-2293`, `litellm/router.py:7763-7797`, `litellm/router.py:7877-7890` The bound attribute `aadapter_generate_content` matches no async branch. Awaiting it returns `None` and never calls `litellm.aadapter_generate_content`.
- [RDISP-024] {confirmed} `litellm/router.py:2507-2516`, `litellm/router.py:7602-7619`, `litellm/router.py:7763-7797`, `litellm/router.py:7877-7890` The attributes `video_create_character`, `video_get_character`, `video_edit` and `video_extension` are missing from the synchronous list and match no async branch. Calling them returns an un-awaited coroutine that resolves to `None`, not a video result.
- [RDISP-025] {confirmed} `litellm/router.py:2566-2572`, `litellm/router.py:7865-7876` The attributes `get_interaction`, `delete_interaction` and `cancel_interaction` match no branch, so calling them returns a coroutine that resolves to `None` without calling the SDK.
- [RDISP-026] {confirmed} `litellm/router.py:2543-2545`, `litellm/router.py:7798-7808`, `litellm/containers/endpoints.json` The synchronous container-file names bound by the setattr loop match no branch: `list_container_files`, `upload_container_file`, `retrieve_container_file`, `delete_container_file` and `retrieve_container_file_content`. Calling them returns a coroutine that resolves to `None`.
- [RDISP-027] {gap} `litellm/router.py:2566`, `litellm/router.py:7865-7876`, `litellm/router.py:8034` The synchronous `create_interaction` is wrapped in the async wrapper, which awaits the return value of the synchronous SDK `create`. Does this raise `TypeError` for a non-awaitable result, or does the SDK return an awaitable here?

### Per-family routers used by the factory
- [RDISP-030] {confirmed} `litellm/router.py:7909-7917` The vector-store router copies a non-empty `custom_llm_provider` into the kwargs when the kwargs lack it. When the kwargs carry a truthy `model`, it runs the generic async fallback chain, which retries and falls back.
- [RDISP-031] {confirmed} `litellm/router.py:7919-7927` Without a `model`, the vector-store router calls `original_function` directly. For `avector_store_search` only, it adds the keyword `router` set to this router instance, overriding any caller-supplied `router`. Other vector-store calls get no router kwarg.
- [RDISP-032] {confirmed} `litellm/router.py:7947-7961` When `container_id` is a string, the container router decodes it as a LiteLLM-managed id:
  - It replaces `container_id` with the decoded upstream id when the two differ.
  - It replaces `custom_llm_provider` with the decoded provider only when the current value is exactly `"openai"`.
- [RDISP-033] {confirmed} `litellm/router.py:7962-7975` For a string `container_id`, the routing deployment id comes from the decoded `model_id`. If that is absent, it comes from a non-blank `model_id` kwarg with whitespace stripped. When one is found, `model` is set to it and the generic async chain runs without passthrough, so an id with no matching deployment fails selection. The `model_id` kwarg itself stays in the forwarded kwargs.
- [RDISP-034] {confirmed} `litellm/router.py:7977-7983`, `litellm/router.py:5969-5972` Otherwise a non-blank string `model` runs the generic async chain with `passthrough_on_no_deployment=True`. If deployment selection then raises, the SDK function is called directly with the caller's `model`.
- [RDISP-035] {confirmed} `litellm/router.py:7985` With neither a routable container id nor a `model`, the container router calls `original_function` directly with the global provider credentials.
- [RDISP-036] {confirmed} `litellm/router.py:7997-8005` The response-id router decodes a deployment id from `response_id`. When one is found it sets `model` to it, then always runs the generic async chain. With no decodable id and no `model` kwarg, the call raises `TypeError` for the missing required `model` argument.
- [RDISP-037] {confirmed} `litellm/router.py:8019-8023` The interactions router copies the `custom_llm_provider` argument when the kwargs lack it, and otherwise defaults `custom_llm_provider` to `"gemini"`.
- [RDISP-038] {confirmed} `litellm/router.py:8024-8026` When `agent` is truthy and `model` equals `agent`, the interactions router sets `model` to `None`, so agent-only calls are never looked up as a model group.
- [RDISP-039] {confirmed} `litellm/router.py:8027-8034` A truthy `model` sends interactions through the generic async chain. Otherwise `original_function` is called directly.
- [RDISP-040] {confirmed} `litellm/router.py:8048-8052` The managed-agents router sets the provider like [RDISP-037], with default `"gemini"`, and always calls `original_function` directly. It never routes through deployments.
- [RDISP-041] {confirmed} `litellm/router.py:8062-8070` The assistants pass-through has three outcomes:
  - With `custom_llm_provider` None and `assistants_config` set, it takes the provider from the config and merges the config's `litellm_params` over the caller kwargs, so the config wins.
  - With both unset, it raises a plain `Exception`. The message is `'custom_llm_provider' must be set. Either via:`, a newline, `` `Router(assistants_config={'custom_llm_provider': ..})` `` with one leading and one trailing space, a newline, `or`, a newline, then `` `router.arun_thread(custom_llm_provider=..)` `` with one leading space. The backticks are part of the text.
  - Otherwise it calls the SDK directly, with no retries or fallbacks.
- [RDISP-042] {confirmed} `litellm/router.py:7451-7455` Moderation first stamps a trace id and writes `model_group` (the request's `model`, or `""` when absent) into the `metadata` bucket.
- [RDISP-043] {confirmed} `litellm/router.py:7456-7469` When `model` names a group that has deployments, moderation selects one deployment, binds it, and merges that deployment's `litellm_params` over the kwargs, so deployment values such as `model` and `api_key` win. Otherwise it calls the SDK with the caller's kwargs. Moderation has no retries, fallbacks or call counters.

### Anthropic messages and generic dispatch
- [RDISP-044] {confirmed} `litellm/router.py:6651-6668` Shared dispatch sends `anthropic_messages` to the Anthropic streaming-fallback chain ([RDISP-045]) and every other call type to the plain generic async fallback chain.
- [RDISP-045] {confirmed} `litellm/router.py:6606-6621` The Anthropic messages chain is the generic async fallback chain with a per-attempt function, so every attempt, retry and fallback hop runs through [RDISP-046].
- [RDISP-046] {confirmed} `litellm/router.py:6623-6649` Each Anthropic-messages attempt runs as follows:
  1. It removes the mid-stream fallback controls from the kwargs and snapshots the hop kwargs.
  2. It runs one generic attempt.
  3. It copies any pre-routing selection and the routed deployment back into the snapshot.
  4. If `stream` is truthy and the result is async-iterable, it returns the result wrapped in the Anthropic messages stream-recovery iterator (router-calls, [RCALL-128]) built from that snapshot. Otherwise it returns the result unchanged.

### Synchronous generic call (`_generic_api_call_with_fallbacks`)
- [RDISP-047] {confirmed} `litellm/router.py:6680-6690` The synchronous generic call stamps `litellm_trace_id` (a new UUID4 when absent) and writes `model_group`/`model_group_alias` into the `litellm_metadata` bucket.
- [RDISP-048] {confirmed} `litellm/router.py:6691-6703` It selects one deployment with the synchronous selector. Inputs are `messages`, `input`, a popped `specific_deployment` and the full kwargs as request kwargs. It binds the deployment under function name `generic_api_call`, splitting stream timeouts only when the SDK function is named `anthropic_messages`, `aresponses` or `responses`.
- [RDISP-049] {confirmed} `litellm/router.py:6705-6714` After selection it increments the `total_calls` counter keyed by the deployment's `litellm_params.model` string (for example the key `openai/gpt-4o`). It replaces every substring occurrence of the requested group name inside a truthy `endpoint` kwarg with the deployment's model, and sets `model` to the deployment's model.
- [RDISP-050] {confirmed} `litellm/router.py:6716-6728` It runs the synchronous routing-strategy pre-call checks ([RDISP-215]), then calls the SDK function. The arguments, later entries winning, are the deployment's `litellm_params`, then `custom_llm_provider` (passed even when it resolves to `None`), then `caching` set to the router's `cache_responses` value, then the caller's kwargs.
- [RDISP-051] {confirmed} `litellm/router.py:6730-6737` On success it increments `success_calls` and logs at INFO the SDK function's name and the deployment model followed by a green ` 200 OK`, rendered for example as `responses(model=openai/gpt-4o)\x1b[32m 200 OK\x1b[0m`. On any exception it increments the `fail_calls` counter keyed by the requested group name and re-raises. Despite its name, this path has no retries, no fallbacks, no exception alert and no retry-skip stamping.

### Embeddings
- [RDISP-052] {confirmed} `litellm/router.py:6739-6754` `embedding(model, input, ...)` sets `model`, `input` and the synchronous worker as `original_function`, stamps `model_group` into the `metadata` bucket, and runs the retry and fallback loop through `function_with_fallbacks` ([RDISP-165]). `is_async` is ignored and errors are re-raised unchanged, with no alert.
- [RDISP-053] {confirmed} `litellm/router.py:6756-6798` The synchronous embedding worker selects one deployment by group and `input`, binds it, and fetches the cached sync client. It passes no client when the request carries an `api_key` different from the cached client's key. It then increments `total_calls`, runs the synchronous pre-call checks ([RDISP-215]), and calls `litellm.embedding` with deployment params, `input`, `caching`, `client` and the caller's kwargs, the caller's kwargs winning.
- [RDISP-054] {confirmed} `litellm/router.py:6799-6804`, `litellm/router.py:6865-6870` When an embedding worker fails, it increments the `fail_calls` counter keyed by the deployment's model string (only if a deployment had been selected), stamps the bound deployment id onto the exception as `retry_skip_deployment_id` when the kwargs carry a non-empty string `model_info.id`, and re-raises.
- [RDISP-055] {confirmed} `litellm/router.py:6806-6829` `aembedding` runs the async worker through `async_function_with_fallbacks`. On failure it schedules a fire-and-forget exception-alert task and re-raises the error.
- [RDISP-056] {confirmed} `litellm/router.py:6831-6864` The async embedding worker selects one deployment, binds it, and uses the cached async OpenAI-compatible client. It increments `total_calls` and calls `litellm.aembedding` inside the deployment slot ([RDISP-218]), so the parallel-request limit and the async pre-call checks apply. Any caller-supplied `client` in kwargs still overrides because kwargs are spread last.

### Files (`acreate_file`)
- [RDISP-057] {confirmed} `litellm/router.py:6873-6894` `acreate_file(model, **kwargs)` runs `_acreate_file` through `async_function_with_fallbacks`, writing `model_group` into the `metadata` bucket. On failure it schedules an exception-alert task and re-raises.
- [RDISP-058] {confirmed} `litellm/router.py:6905-6912` File creation fetches every healthy deployment of the group, using the placeholder message `files-api-fake-text` and a popped `specific_deployment`. It does not pick a single deployment.
- [RDISP-059] {confirmed} `litellm/router.py:6989-6997` The file is uploaded to every healthy deployment concurrently, one task per deployment, or one task when selection returned a single deployment. Tasks are gathered without `return_exceptions`, so the first failing upload's exception propagates.
- [RDISP-060] {confirmed} `litellm/router.py:6914-6930` Each upload works on a deep copy of the request kwargs, binds its deployment under function name `acreate_file`, uses the cached async client, and increments the `total_calls` counter keyed by the deployment's model string.
- [RDISP-061] {confirmed} `litellm/router.py:6933-6940`, `litellm/router.py:7066-7072`, `litellm/router.py:7161-7167`, `litellm/router.py:7366-7372` File upload, batch create, batch cancel and vector-store create resolve the SDK's `custom_llm_provider` per deployment, and the same rule is meant wherever this spec says "resolves the provider":
  - The deployment's own non-empty `litellm_params.custom_llm_provider` is used when set.
  - Otherwise the provider that the SDK's `get_llm_provider` infers from the deployment's `litellm_params.model` is used. For example `gpt-4o-mini` and `openai/gpt-4o-mini` both give `openai`, and `azure/my-dep` gives `azure`.
  - A caller-supplied `custom_llm_provider` kwarg still overrides the resolved value, because the caller's kwargs are spread last.
  - The `model` handed to the SDK is the deployment's `litellm_params.model` exactly as configured, never the group name and never prefix-stripped (`openai/gpt-4o-mini` stays `openai/gpt-4o-mini`). Only file upload computes the prefix-stripped name, and uses it solely for the JSONL rewrite ([RDISP-063]) and `target_model_names` ([RDISP-064]).
- [RDISP-062] {confirmed} `litellm/router.py:6942-6946` A missing or falsy `file` or `purpose` raises `Exception("file and file_purpose are required for create_file")`. This happens per deployment, after `total_calls` was already incremented.
- [RDISP-063] {confirmed} `litellm/router.py:6948-6959` When `purpose == "batch"` and `passthrough` is not `True`, the uploaded JSONL has its per-row model replaced by the stripped deployment model. Blank lines are kept only when the provider resolved from the deployment ([RDISP-061]) is `vertex_ai`. A caller `custom_llm_provider` kwarg does not change the stripped model or this rule.
- [RDISP-064] {confirmed} `litellm/router.py:6933-6940`, `litellm/router.py:6960-6966`, `litellm/router.py:6974-6982` When the provider resolved from the deployment ([RDISP-061]) is `litellm_proxy`, the upload's `extra_body` is rebuilt from the request's own `extra_body` only, with `target_model_names` set to the stripped deployment model. The SDK receives it as a read-only mapping (a `MappingProxyType`, not a `dict`). The cases:
  - A caller `extra_body={"foo": 1, "target_model_names": "zzz"}` is sent as `{"foo": 1, "target_model_names": "gpt-4.1-batch"}` for a `litellm_proxy/gpt-4.1-batch` deployment, so a caller-supplied `target_model_names` is overwritten.
  - A deployment-configured `litellm_params.extra_body` is not merged in. The rebuilt `extra_body` replaces it, because the request side is spread after the deployment params. For example, deployment `{"model": "litellm_proxy/gpt-4.1-batch", "extra_body": {"deploy_key": 1}}` sends `extra_body={"target_model_names": "gpt-4.1-batch"}`, and `deploy_key` is lost.
  - The `litellm_proxy` check looks only at the deployment-resolved provider, including an explicit deployment `custom_llm_provider: "litellm_proxy"`. A caller `custom_llm_provider="litellm_proxy"` kwarg on a non-proxy deployment still reaches the SDK ([RDISP-061]), but the SDK gets no `target_model_names` and no `extra_body`.
  - For any other provider nothing is injected. A deployment `extra_body` reaches the SDK unchanged when the caller sends none. A caller `extra_body` replaces it whole, with no key merge.
- [RDISP-065] {confirmed} `litellm/router.py:6967-6970` When the deployment's `litellm_params` contain `gcs_bucket_name`, it is copied into the upload's `litellm_metadata` bucket, which is created if absent.
- [RDISP-066] {confirmed} `litellm/router.py:6971-6986` Each upload calls `litellm.acreate_file` inside the deployment slot. The arguments are deployment params, the resolved provider, `caching` and `client`, with the kwargs copy winning. A successful upload increments `success_calls`.
- [RDISP-067] {confirmed} `litellm/router.py:6999-7009` With zero uploads, `Exception("No healthy deployments found.")` is raised. Otherwise the first deployment's response is returned, with hidden param `model_file_id_mapping` set to a dict from each deployment's `model_info.id` to the file id its upload returned, skipping deployments without an id. For example, two deployments give `{"dep-1": "file-abc", "dep-2": "file-xyz"}`.
- [RDISP-068] {confirmed} `litellm/router.py:7010-7016` When file creation fails, it logs at exception level with the group and the full kwargs, increments the `fail_calls` counter keyed by the requested group name, and re-raises without stamping a retry-skip id.
- [RDISP-069] {inferred} `litellm/router_utils/fallback_event_handlers.py:652-664`, `litellm/router_utils/fallback_event_handlers.py:723-756`, `litellm/router_utils/fallback_event_handlers.py:805-829` The fallback walk (failure-handling, [FAILURE-137], [FAILURE-142]) never moves a provider-scoped resource to a different model group. The rule is applied in the walk, not here:
  - `_acreate_file` uploads are always kept to their own group.
  - Handlers named `_acreate_batch`, `_acancel_batch`, `acreate_fine_tuning_job`, `acancel_fine_tuning_job`, `aretrieve_fine_tuning_job`, `afile_content` or `afile_delete` are kept to their own group when the kwargs carry a truthy `input_file_id`, `training_file`, `batch_id`, `file_id` or `fine_tuning_job_id`.

### Vector store create
- [RDISP-070] {confirmed} `litellm/router.py:7034-7041` `avector_store_create(model=None, ...)` with `model` `None` builds a factory wrapper for call type `avector_store_create` and calls it. That wrapper calls the SDK `acreate` directly, without injecting a `router` kwarg ([RDISP-031]).
- [RDISP-071] {confirmed} `litellm/router.py:7043-7088` With a `model`, `avector_store_create` selects one deployment (placeholder `vector-store-api-fake-text`), binds it under `avector_store_create`, and resolves the provider ([RDISP-061]). It increments `total_calls` and calls the SDK `acreate` inside the deployment slot. There are no retries and no fallbacks.
- [RDISP-072] {confirmed} `litellm/router.py:7089-7095` When `avector_store_create` fails, it logs at exception level, increments the `fail_calls` counter keyed by the requested `model` when one was given, and re-raises with no alert.
- [RDISP-073] {confirmed} `litellm/router.py:7097-7106` `_override_vector_store_methods_for_router` has an empty body. Calling it during setup changes nothing.

### Batches
- [RDISP-074] {confirmed} `litellm/router.py:7108-7134` `acreate_batch(model, **kwargs)` writes `model_group` into the `litellm_metadata` bucket and runs `_acreate_batch` through `async_function_with_fallbacks`. On failure it schedules an alert task and re-raises.
- [RDISP-075] {confirmed} `litellm/router.py:7136-7191` The batch-create worker selects one deployment (placeholder `files-api-fake-text`), binds it under `_acreate_batch`, and uses the cached async client. It then works as follows:
  - It increments `total_calls`, resolves the provider ([RDISP-061]) and calls `litellm.acreate_batch` inside the deployment slot.
  - The call's arguments, later entries winning, are the deployment's `litellm_params`, the resolved `custom_llm_provider`, `caching`, `client`, then the caller's kwargs.
  - For example, a deployment `{"model": "gpt-4o-mini", "api_key": "k"}` with no `custom_llm_provider` gives `model="gpt-4o-mini"`, `custom_llm_provider="openai"` and `api_key="k"`.
  - On failure it logs with kwargs, increments the `fail_calls` counter keyed by the requested group name, stamps the retry-skip id ([RDISP-054]) and re-raises.
- [RDISP-076] {confirmed} `litellm/router.py:7303-7332` `acancel_batch(model, **kwargs)` follows the same entry pattern: `litellm_metadata` bucket, `async_function_with_fallbacks`, and an alert on failure. The `model` may be a deployment id decoded by the caller.
- [RDISP-077] {confirmed} `litellm/router.py:7341-7356` The batch-cancel worker selects one deployment (placeholder `batch-api-fake-text`), looks up stored credentials by the selected deployment's id (or by the requested name when the id is missing), merges them over the deployment's `litellm_params`, and removes `litellm_credential_name`.
- [RDISP-078] {confirmed} `litellm/router.py:7357-7396` The batch-cancel worker then binds the deployment, increments `total_calls`, resolves the provider and calls `litellm.acancel_batch` inside the deployment slot. Its error handling matches [RDISP-075].
- [RDISP-079] {confirmed} `litellm/router.py:7203-7220` `aretrieve_batch(model=None, **kwargs)` queries different deployments depending on `model`:
  - With `model`, it queries every healthy deployment of that group (placeholder `retrieve-api-fake-text`).
  - Without `model`, it queries every deployment in the router's whole model list, across all groups.
  - A `None` list raises `Exception("Router not yet initialized.")`.
- [RDISP-080] {confirmed} `litellm/router.py:7262-7275` `aretrieve_batch` queries a non-empty list concurrently, queries a single selected deployment alone, and raises `Exception("No healthy deployments found.")` for an empty list.
- [RDISP-081] {confirmed} `litellm/router.py:7224-7254` Each retrieve probe works on a deep copy of kwargs. It binds the deployment under `aretrieve_batch` and stamps `model_group` (the requested group, else that deployment's own group) into `litellm_metadata` when not already set. It drops any caller `custom_llm_provider` and calls `litellm.aretrieve_batch` with the deployment's provider, or the one inferred from its model. No `caching` or `client` is passed.
- [RDISP-082] {confirmed} `litellm/router.py:7255-7260` A failing retrieve probe prints its traceback to stderr, records the exception, and yields `None`. One deployment's failure never aborts the others.
- [RDISP-083] {confirmed} `litellm/router.py:7277-7291` `aretrieve_batch` returns the first `LiteLLMBatch` result in deployment-list order. With none, it raises the first recorded probe exception, or `Exception("Unable to find batch in any model. Received errors - []")` when nothing was recorded.
- [RDISP-084] {confirmed} `litellm/router.py:7193-7301` `aretrieve_batch` has no retry or fallback loop and no call counters, and on any raised error schedules an exception-alert task before re-raising.
- [RDISP-085] {confirmed} `litellm/router.py:7407-7409` `alist_batches(model, **kwargs)` lists the group's deployments with no health or cooldown filtering, and raises `Exception("Router not yet initialized.")` when the list is `None`.
- [RDISP-086] {confirmed} `litellm/router.py:7411-7419` `alist_batches` calls `litellm.alist_batches` concurrently on every deployment with the deployment params overridden by the caller kwargs. Any per-deployment exception is silently replaced by `None`.
- [RDISP-087] {confirmed} `litellm/router.py:7421-7441` `alist_batches` returns `{"object": "list", "data": [...], "first_id": ..., "last_id": ..., "has_more": ...}`, built like this:
  - `data` concatenates every successful result's items in deployment order, without de-duplication.
  - `first_id` comes from the first successful result that has one, and `last_id` from the last successful result.
  - `has_more` is `True` if any result reported it.
  - The call raises no alert and keeps no counters.

### Fallback entry (`async_function_with_fallbacks`)
- [RDISP-090] {confirmed} `litellm/router.py:8439-8444` When the name of `original_generic_function` (else `original_function`) maps to a context-compaction surface, `async_function_with_fallbacks` initializes `_context_compaction_state` in the kwargs before anything else.
- [RDISP-091] {confirmed} `litellm/router.py:8445`, `litellm/router_utils/fallback_event_handlers.py:321-336` Every entry, including each fallback hop, deletes `pre_routing_selected_model` from both the `metadata` and `litellm_metadata` buckets. This discards caller-supplied values and the previous hop's tier, so only a selection made while routing this hop is used for fallback lookup.
- [RDISP-092] {confirmed} `litellm/router.py:8446-8461`, `litellm/router_utils/batch_utils.py:171-191` On a top-level call (no `AttemptedFallbackTargets` carried in `attempted_targets`), it resets the fallback stamps in place:
  1. The route bucket is chosen from the function name: `litellm_metadata` when the name contains `batch`, `generic_api_call`, `_acreate_batch`, `file` or `_ageneric_api_call_with_fallbacks`, otherwise `metadata`.
  2. In the other (sibling) bucket, `attempted_fallbacks` and `original_model_group` are removed.
  3. In the route bucket, `attempted_fallbacks = 0` and `original_model_group = <model>` are written, overwriting client-supplied values.
- [RDISP-093] {confirmed} `litellm/router.py:8462-8467` It pops `disable_fallbacks` (default `False`) and records the verdict in the request's metadata bucket for downstream stream recovery. `fallbacks`, `context_window_fallbacks` and `content_policy_fallbacks` come from the request when the key is present, even when explicitly `None`, and from the router's settings otherwise.
- [RDISP-094] {confirmed} `litellm/router.py:8469-8483` It pops `mock_timeout` and forwards it to the retry loop only when it is not `None`. The mock fallback triggers ([RDISP-151]) are evaluated first, inside the same try block.
- [RDISP-095] {confirmed} `litellm/router.py:8484-8490` A response that succeeds without a fallback gets `x-litellm-attempted-fallbacks: 0` added to its hidden params' `additional_headers`. The response must be a pydantic model, a dict, or an object with `_hidden_params`.
- [RDISP-096] {confirmed} `litellm/router.py:8491-8502` Any exception from the retry loop, including mock triggers, is handed to the fallback dispatcher ([RDISP-100]-[RDISP-116]) together with the resolved fallback lists and whether `include_fallback_errors` was exactly `True`.

### Fallback dispatcher (`async_function_with_fallbacks_common_utils`)
- [RDISP-100] {confirmed} `litellm/router.py:8166-8167` When DEBUG logging is enabled for the router logger, the dispatcher logs the current traceback after secret redaction.
- [RDISP-101] {confirmed} `litellm/router.py:8180-8189`, `litellm/router_utils/fallback_event_handlers.py:255-262` The dispatcher re-raises the original exception immediately, with no fallback and no message suffix, when any of these hold:
  - `disable_fallbacks is True`.
  - The kwargs have no `model`.
  - The error is a guardrail intervention.
  - `fallback_on_unsupported_params` is false and the error is an `UnsupportedParamsError`, or a 400 `BadRequestError` with a non-empty `llm_provider` that is neither a context-window nor a content-policy error.
- [RDISP-102] {confirmed} `litellm/router.py:8191-8203` The kwargs for every fallback walk contain the router, `original_exception`, all request kwargs, and the shared `attempted_targets` set (reused from the request or newly created). `max_fallbacks` defaults to the router's `max_fallbacks`, `fallback_depth` defaults to `0`, and `include_fallback_errors` is forced to `True` when flagged.
- [RDISP-103] {confirmed} `litellm/router.py:8205-8221` Order levels are the sorted distinct non-`None` `order` values of the deployments that are both:
  - In the pre-routing-selected tier, or in the requested group when no tier was selected.
  - Visible to the team in `metadata.user_api_key_team_id`.
- [RDISP-104] {confirmed} `litellm/router.py:8222-8259` When there are two or more order levels and the error is not context-window or content-policy, the dispatcher builds a combined chain and, if it is non-empty, walks it and returns the result before any other fallback path runs. The chain is:
  1. One entry `{"model": <group>, "_target_order": o}` for each level `o` greater than the current `_target_order` (or than the lowest level when unset).
  2. Then the external chain: a non-standard list passed through as-is, or otherwise the specific chain for the lookup groups, else the `"*"` chain.
- [RDISP-105] {inferred} `litellm/router.py:8255-8259`, `litellm/router_utils/fallback_event_handlers.py:884-900` A failed order-level walk is not caught by the dispatcher. The caller sees the walk's last failure, not the original exception, and no outcome suffix is appended. This is inferred from the walk raising its most recent error and is pinned by a test.
- [RDISP-106] {confirmed} `litellm/router.py:8261-8272` When `enable_weighted_failover` is true, the error is not context-window or content-policy, and no order walk returned, the dispatcher tries weighted intra-group failover ([RDISP-120]-[RDISP-124]) and returns any non-`None` response.
- [RDISP-107] {confirmed} `litellm/router.py:8277-8293`, `litellm/router_utils/fallback_event_handlers.py:959-983` A non-standard `fallbacks` value is walked directly as the chain. Non-standard means a non-empty list of model-name strings, or a list of dicts in which some LiteLLM parameter key has a non-list value.
- [RDISP-108] {confirmed} `litellm/router.py:8295-8317`, `litellm/router.py:8402-8431` A `ContextWindowExceededError` with `context_window_fallbacks` not `None` is decided by that list alone; the generic `fallbacks` chain is never consulted for it:
  - The chain is resolved from `context_window_fallbacks` over the lookup groups ([RDISP-117]): an exact or provider-prefix key match first, then that list's own `"*"` entry.
  - When a chain resolves, it is walked and the walk's response is returned.
  - When none resolves, the original exception is raised at once. [RDISP-114] catches that re-raise and logs the ERROR line. No fallback target was recorded, so with exposure on the message ends with `No fallback was attempted.` ([RDISP-115]).
  - For example, take a router with `fallbacks=[{"p": ["b"]}]` and a context-window failure of group `p`. With `context_window_fallbacks=[{"other": ["big"]}]` the error is raised and `b` is never tried. With `context_window_fallbacks=[{"p": ["big"]}]` the request is served by `big` with `x-litellm-attempted-fallbacks: 1`. With no `context_window_fallbacks`, [RDISP-109] applies and `b` serves it.
- [RDISP-109] {confirmed} `litellm/router.py:8319-8327` A `ContextWindowExceededError` whose `context_window_fallbacks` is `None` logs at INFO and then continues to the generic chain ([RDISP-111]). Before continuing, when `litellm.expose_router_debug_in_errors` is true, it appends a hint to `e.message`:
  - The hint is a newline, then `model=<group>. context_window_fallbacks=<cw>. fallbacks=<fb>.`, then two newlines, then `Set 'context_window_fallback' - https://docs.litellm.ai/docs/routing#fallbacks`.
  - `<group>` is the requested group. `<cw>` and `<fb>` are the two lists after `mask_sensitive_structure`, rendered with Python `str()`, so `None` prints as `None` and a list prints as its repr.
  - For example, group `p` with `fallbacks=[{"p": ["b"]}]` appends `\nmodel=p. context_window_fallbacks=None. fallbacks=[{'p': ['b']}].\n\nSet 'context_window_fallback' - https://docs.litellm.ai/docs/routing#fallbacks`, where `\n` is a newline.
  - The hint stays on the exception even when a later fallback succeeds, but the caller sees it only if the original error is finally raised.
- [RDISP-110] {confirmed} `litellm/router.py:8328-8359` A `ContentPolicyViolationError` follows the rules of [RDISP-108] and [RDISP-109] with `content_policy_fallbacks` in place of `context_window_fallbacks`. A non-`None` list alone decides, and a miss raises the original error without trying generic `fallbacks`. Its hint differs only in the key name and the docs pointer, rendered for example as `\nmodel=g. content_policy_fallback=None. fallbacks=None.\n\nSet 'content_policy_fallback' - https://docs.litellm.ai/docs/routing#fallbacks` (singular `content_policy_fallback=`).
- [RDISP-111] {confirmed} `litellm/router.py:8360-8371`, `litellm/router_utils/fallback_event_handlers.py:566-578` When `fallbacks` is not `None` and there are lookup groups, the generic chain is the first lookup group's specifically keyed chain. The `"*"` chain is used only when no lookup group has a specific chain.
- [RDISP-112] {confirmed} `litellm/router.py:8373-8387`, `litellm/router_utils/common_utils.py:136-148` When `fallbacks` is not `None` but no generic chain resolves for any lookup group, the dispatcher logs at INFO and raises the original exception, first appending the "no fallback group" text:
  - The INFO line is rendered as `No fallback model group found for lookup_groups=a. Fallbacks=[{'x': ['y']}]`. The groups are joined with ` -> ` and the list is masked, then printed with Python `str()`.
  - The text is appended only when the expose flag is on, the exception has a `message`, and this is not a nested hop (a nested hop has an integer `fallback_depth` > 0).
  - The text is two newlines, then `LiteLLM: model group '<groups>' failed with the error above and no fallback model group was found for it, so the request was not retried on another model.`, then a keys sentence, then ` Add a fallbacks entry for that model group (Router fallbacks or proxy router_settings.fallbacks) to retry on another model.`
  - `<groups>` is the lookup groups ([RDISP-117]) joined with ` -> `. The keys sentence is ` Fallbacks are configured for: ` plus every entry's keys, de-duplicated in first-seen order and joined with `, `, then `.`. When the list has no keys (a per-request `fallbacks=[]`) it is ` No fallbacks are configured.` instead.
  - Rendered example: group `a` failing with `InternalServerError("boom")` under `fallbacks=[{"x": ["y"]}, {"z": ["w"]}, {"x": ["q"]}]` raises the message `litellm.InternalServerError: boom\n\nLiteLLM: model group 'a' failed with the error above and no fallback model group was found for it, so the request was not retried on another model. Fallbacks are configured for: x, z. Add a fallbacks entry for that model group (Router fallbacks or proxy router_settings.fallbacks) to retry on another model.`
  - When this text was appended, the outcome text of [RDISP-115] is not added.
- [RDISP-113] {confirmed} `litellm/router.py:8389-8401` When a generic chain resolves, it is walked and the walk's response is returned.
- [RDISP-114] {confirmed} `litellm/router.py:8402-8415`, `litellm/router_utils/common_utils.py:120-133` Any exception inside the main fallback block is caught: a failed walk of a chain, and also the deliberate re-raises of [RDISP-108], [RDISP-110] and [RDISP-112]. The dispatcher then records a failure detail and logs one ERROR line:
  - The detail is `str()` of the caught exception after secret redaction. Beyond `ROUTER_FALLBACK_ERROR_DETAIL_MAX_CHARS` (2000 characters) it is cut to its first 2000 characters followed by `... [truncated N characters]`, where N is the number of characters dropped.
  - The ERROR record spans three lines, rendered for example as `litellm.router.py::async_function_with_fallbacks() - Error occurred while trying to do fallbacks - litellm.ContextWindowExceededError: litellm.BadRequestError: too long`, then `Debug Information:`, then `Cooldown Deployments=[]` (the cooldown debug list).
  - When nothing is walked and nothing is raised inside the block ([RDISP-116]), no ERROR line is written.
- [RDISP-115] {confirmed} `litellm/router.py:8417-8431`, `litellm/router_utils/common_utils.py:151-209` Every path that reaches the end raises the original exception, never a fallback's error. Outcome text is first appended to its `message` when the expose flag is on, this is not a nested hop, the [RDISP-112] text was not appended, and the exception has a `message`. The text is rendered as follows:
  - It always starts with two newlines and `LiteLLM: model group '<group>' failed with the error above.`, where `<group>` is the requested group.
  - When no chain was handed to an order-level, non-standard, dedicated or generic walk, it continues ` No fallback was attempted.` That covers no configured chain, a failed weighted-failover walk ([RDISP-116]), and the deliberate re-raises of [RDISP-108] and [RDISP-110].
  - Otherwise it continues with a space and these sentences, joined by spaces. `Fallback to <targets> also failed: <detail>` appears when the [RDISP-114] detail is non-empty and some chain entry was not skipped. `Fallback to <targets> was skipped because the caller is not authorized to call it.` appears for targets skipped as not authorized. `Fallback to <targets> was skipped because the caller is over budget for it.` appears for targets skipped as over budget. The last two say `them` instead of `it` for several targets.
  - When none of those sentences applies, as with an empty detail, it continues ` Fallback model group(s) configured: <targets>.` listing the whole chain.
  - Each `<targets>` list is rendered entry by entry after `mask_sensitive_structure`, with `str()`, joined with `, `. A dict entry prints as its repr with credentials masked, for example `{'model': 'b', 'api_key': 'sk-s*************'}`. In the `also failed` sentence the list holds the chain entries that were not skipped. In a skip sentence it holds that reason's skipped target names, de-duplicated. In the `configured` sentence it holds the whole chain.
  - Rendered examples: `litellm.InternalServerError: boom\n\nLiteLLM: model group 'a' failed with the error above. Fallback to b also failed: litellm.InternalServerError: boom`, and with no fallbacks `litellm.RateLimitError: This is a mock exception for model=g, to trigger a rate limit error.\n\nLiteLLM: model group 'g' failed with the error above. No fallback was attempted.`
- [RDISP-116] {confirmed} `litellm/router_utils/fallback_event_handlers.py:969-970`, `litellm/router.py:8278-8280`, `litellm/router.py:8360`, `litellm/router.py:8417-8431`, `litellm/router.py:8134-8149` When no order walk ([RDISP-104]) or weighted failover ([RDISP-106]) has returned a response, `fallbacks` is `None`, and no context-window or content-policy chain applies, no further chain is walked. The original exception is raised with the ` No fallback was attempted.` outcome text when exposure is on. That text appears even after a weighted-failover walk ran and failed, because that walk works on its own copy of the walk kwargs. For example, a `simple-shuffle` group `g` with two deployments that both raise `InternalServerError("boom")`, `enable_weighted_failover=True` and `num_retries=0` makes 2 provider calls and raises `litellm.InternalServerError: boom\n\nLiteLLM: model group 'g' failed with the error above. No fallback was attempted.`
- [RDISP-117] {inferred} `litellm/router_utils/fallback_event_handlers.py:537-553` Lookup groups are tried in this order, de-duplicated, keeping the first occurrence:
  1. The pre-routing-selected tier.
  2. The routed group recorded in the metadata bucket.
  3. The requested group.
  4. The `original_model_group` recorded in the bucket.
- [RDISP-118] {inferred} `litellm/router_utils/fallback_event_handlers.py:757-900` The fallback walk (failure-handling, [FAILURE-138]-[FAILURE-152]) works as follows:
  - It raises the original exception when `fallback_depth >= max_fallbacks`.
  - It skips the failed group and targets already attempted.
  - It calls `log_retry` and re-enters `async_function_with_fallbacks` for each target with `fallback_depth + 1`.
  - It stamps `x-litellm-attempted-fallbacks` with that depth (and `x-litellm-fallback-errors` when requested) on success.
  - Otherwise it raises the last target's error.
- [RDISP-119] {confirmed} `litellm/router.py:8191-8203`, `litellm/router.py:8462` Because the walk kwargs copy the raw request kwargs, a non-`True` value of `include_fallback_errors` still reaches the fallback walk unchanged. The `x-litellm-fallback-errors` header then follows that value's truthiness. For example, `1` and a non-empty string produce the header, while `""`, `[]` and `False` do not.

### Weighted intra-group failover
- [RDISP-120] {confirmed} `litellm/router.py:8084-8090` Weighted failover returns `None` (does nothing) unless the group's routing strategy is `simple-shuffle` and the exception carries a non-empty `failed_deployment_id`.
- [RDISP-121] {confirmed} `litellm/router.py:8092-8100` Weighted failover stores its state in the `litellm_metadata` bucket when that key exists, otherwise in `metadata`. It creates the bucket as `{}` if absent and gives up when the bucket is not a dict. The excluded set is the previous `_failover_excluded_ids` plus the failed id.
- [RDISP-122] {confirmed} `litellm/router.py:8102-8115` The remaining candidates are the group's deployment ids minus currently cooled-down ids minus excluded ids. When none remain, weighted failover returns `None` without walking.
- [RDISP-123] {confirmed} `litellm/router.py:8117-8140` Weighted failover writes the excluded ids back into the bucket as `_failover_excluded_ids` (a list in unspecified order). It then walks a one-entry chain naming the same group with the excluded ids, rendered for example as `{"model": "g", "_excluded_deployment_ids": ["dep-1"]}`, using a copy of the walk kwargs, so the caller's shared kwargs never receive `_excluded_deployment_ids`.
- [RDISP-124] {confirmed} `litellm/router.py:8141-8149` An `openai.APIError` (all litellm provider errors), `RouterRateLimitError` or `RouterRateLimitErrorBasic` from the failover walk makes it return `None`, deferring to the regular fallback chain. Any other exception type propagates to the caller.

### Retry loop (`async_function_with_retries`)
- [RDISP-130] {confirmed} `litellm/router.py:8570-8578` The retry loop pops these from the kwargs, so they never reach the SDK call:
  - `original_function` (required: a missing key raises `KeyError`).
  - `fallbacks`, `context_window_fallbacks` and `content_policy_fallbacks`, each defaulting to the router's value.
  - `model_group_retry_policy`, where a per-request value overrides the router's.
- [RDISP-131] {confirmed} `litellm/router.py:8579-8584` The retry count is the popped request `num_retries`. When that is absent or `None`, the router's `num_retries` is used, and `0` when that is also `None`. A `None` therefore never reaches a numeric comparison.
- [RDISP-132] {confirmed} `litellm/router.py:8586-8591` The retry metadata dict is the value of `litellm_metadata` when that key is present, else of `metadata`. A falsy value is replaced by a detached empty dict whose writes are lost. When the dict's `model_group` is a string, `model_group_size` is set to the number of deployments in that group.
- [RDISP-133] {confirmed} `litellm/router.py:8596-8598` Before the first attempt the metadata dict gets `attempted_retries` set to `0` and `max_retries` set to the retry count resolved by [RDISP-131], before any deployment or policy override.
- [RDISP-134] {confirmed} `litellm/router.py:8599-8604` The first attempt runs the mock rate-limit trigger ([RDISP-152]), then `make_call`. On success the response gets `x-litellm-attempted-retries: 0` and no `x-litellm-max-retries` header.
- [RDISP-135] {confirmed} `litellm/router.py:8606-8607` A guardrail-intervention error on the first attempt is re-raised at once, with no retry.
- [RDISP-136] {confirmed} `litellm/router.py:8610-8617` When the request did not set `num_retries` and the first error carries an integer `num_retries` attribute (stamped from the deployment's `litellm_params.num_retries`), that value becomes the retry count. Precedence is request, then deployment, then router, then `0`.
- [RDISP-137] {confirmed} `litellm/router.py:8621-8631` After the first failure, the loop computes healthy and all deployments for the current `model`, passing the request kwargs reduced to their PTU-share-relevant form.
- [RDISP-138] {confirmed} `litellm/router.py:8633-8650` A retry policy is consulted when the request's `num_retries` is not explicitly `0` and either `retry_policy` or a model-group retry policy is configured. A non-`None` count from it replaces the retry count and disables the `should_retry_this_error` gate for the whole request, so even a 400 or 404 is retried that many times. An explicit request `num_retries=0` therefore also disables retry policies, while a router-level `num_retries=0` or a deployment-level count does not (example in [RDISP-147]).
- [RDISP-139] {inferred} `litellm/router_utils/get_retry_from_policy.py:35-66`, `litellm/router.py:8577`, `litellm/router.py:8636-8650` The policy is the group's entry in the effective model-group retry map, else the router's `retry_policy`. The effective map is the request's `model_group_retry_policy` when the request carries that key, which replaces the router's map (so a group the request's map omits falls to `retry_policy`, not to the router's map), else the router's map; a dict entry is converted to a `RetryPolicy`. The count is `NotFoundErrorRetries` when the error's `status_code` is `404` and that field is set, then the first non-`None` per-class field walking the exception class's MRO (Authentication, Timeout, RateLimit, ContentPolicyViolation, BadRequest, ServiceUnavailable, InternalServer), else `DefaultRetries`; a `None` result means no policy count applies.
- [RDISP-140] {confirmed} `litellm/router.py:8652-8662` Without an applicable retry policy, `should_retry_this_error` ([RDISP-155]) runs on the first error and raises that error immediately when retrying is not allowed.
- [RDISP-141] {confirmed} `litellm/router.py:8663-8676` After the overrides, `max_retries` in the metadata is updated. When the retry count is `0`, the first error is re-raised as-is. Otherwise the failure is recorded with `log_retry` ([RDISP-200]) and the retry-skip list is extended ([RDISP-148]).
- [RDISP-142] {confirmed} `litellm/router.py:8678-8688` Before the first retry the loop sleeps `_time_to_sleep_before_retry` ([RDISP-160]) seconds, computed from the first error with `remaining_retries == num_retries`.
- [RDISP-143] {confirmed} `litellm/router.py:8690-8705` Up to `num_retries` retries follow. Before each, the metadata gets `attempted_retries = i + 1` and `max_retries`. An awaitable result is awaited, and the first success returns with `x-litellm-attempted-retries: i + 1` and `x-litellm-max-retries: num_retries`.
- [RDISP-144] {confirmed} `litellm/router.py:8707-8729` A failed retry becomes the tracked error, is recorded with `log_retry`, and refreshes the healthy-deployment list for the current `model` (an empty list when `model` is `None`). The all-deployments list is not refreshed.
- [RDISP-145] {confirmed} `litellm/router.py:8731-8746` Without an applicable retry policy, each failed retry is re-checked with `should_retry_this_error`. When that check declines, the latest error is raised at once, without the `num_retries`/`max_retries` attributes of [RDISP-147].
- [RDISP-146] {confirmed} `litellm/router.py:8748-8761` After each failed retry the skip list is extended and the loop sleeps the computed backoff with `remaining_retries = num_retries - i - 1`. This includes the final retry, so an exhausted request still waits once more before raising.
- [RDISP-147] {confirmed} `litellm/router.py:8763-8773`, `litellm/exceptions.py:1051-1073`, `litellm/exceptions.py:252-258` When all retries are exhausted, the latest error is raised, not the first. If its exact type is in `litellm.LITELLM_EXCEPTION_TYPES`, it first gets `max_retries` and `num_retries` set:
  - `LITELLM_EXCEPTION_TYPES` lists these `litellm` classes: `AuthenticationError`, `NotFoundError`, `BadRequestError`, `UnprocessableEntityError`, `UnsupportedParamsError`, `Timeout`, `PermissionDeniedError`, `RateLimitError`, `ContextWindowExceededError`, `PaymentRequiredError`, `RejectedRequestError`, `ContentPolicyViolationError`, `InternalServerError`, `ServiceUnavailableError`, `BadGatewayError`, `APIError`, `APIConnectionError`, `APIResponseValidationError`, `OpenAIError` and `JSONSchemaValidationError`.
  - The match is on the exact class, so subclasses such as `CallerCredentialAuthenticationError`, `CallerCredentialRateLimitError`, `ImageFetchError` and `MidStreamFallbackError`, and non-litellm exceptions, get neither attribute.
  - `max_retries` becomes the final retry count, and `num_retries` becomes the number of retries attempted, which equals it once the loop ran to the end.
  - The litellm exception classes that define their own `str()`, such as `BadRequestError`, render these after the whole message, including any outcome text of [RDISP-115]. They add ` LiteLLM Retried: N times` when `num_retries` is truthy, then `, LiteLLM Max Retries: M` when `max_retries` is truthy.
  - Rendered example: a one-deployment group under router `num_retries=0` and `retry_policy=RetryPolicy(BadRequestErrorRetries=2)` calls a provider that always raises `BadRequestError("bad")`. It makes 3 provider calls and raises with `num_retries == 2`, `max_retries == 2` and the string `litellm.BadRequestError: bad\n\nLiteLLM: model group 'g' failed with the error above. No fallback was attempted. LiteLLM Retried: 2 times, LiteLLM Max Retries: 2`. With no retry policy the same group makes 1 call, because the 400 fails the eligibility gate ([RDISP-155], check 3).
- [RDISP-148] {confirmed} `litellm/router.py:8551-8566` The retry-skip list is built as follows:
  - The failed deployment id is the exception's `retry_skip_deployment_id`, else its `failed_deployment_id`.
  - The id is added only when it is non-empty, `status_code` is an `int`, and `litellm.should_retry(status_code)` is false. For example, 400, 401, 403 and 404 add the id, while 408, 409, 429 and 5xx do not.
  - The result is the sorted, de-duplicated tuple of that id plus the string members of an already-skipped tuple. Non-tuple prior values are ignored, and `()` is returned when no id is added.
- [RDISP-149] {confirmed} `litellm/router.py:8669-8674`, `litellm/router.py:8748-8753`, `litellm/router.py:8483`, `litellm/router.py:14520-14531`, `litellm/router.py:15721-15730`, `litellm/router.py:634-635` The loop stores the skip tuple ([RDISP-148]) as `_retry_skipped_deployment_ids` in its own kwargs. Healthy-deployment selection (router-selection, [RSELECT-053]) applies it on every attempt as follows:
  - Selection pops the key from the attempt's own copy of the kwargs, so the key never reaches the SDK call. The loop's tuple is not popped: it persists and grows across the retries of one request.
  - Selection removes the skipped ids from the candidates unless that would leave none. In that case it uses the whole unfiltered candidate list, which re-admits every deployment skipped earlier, not only the last remaining one.
  - For example, take group `g` with deployments `A` and `B`, `retry_policy=RetryPolicy(BadRequestErrorRetries=3)`, and both deployments always answering 400. Attempt 2 always goes to the deployment attempt 1 did not use. Once both ids are skipped, attempts 3 and 4 choose from both again, giving sequences such as `A,B,A,A` or `B,A,B,A`.
  - A caller-supplied tuple of id strings is applied from the first attempt, before anything has failed, and later failures are added to it. For example, `_retry_skipped_deployment_ids=("A",)` sends attempt 1 to `B`. A list or any other non-tuple value is ignored, and non-string items of a tuple are dropped.
  - The tuple the loop builds lives only in the loop's copy of the kwargs, so fallback hops ([RDISP-118]) start without the retry-skipped ids. A caller-supplied tuple, which is part of the request kwargs, is carried into every hop.
- [RDISP-150] {confirmed} `litellm/router.py:8775-8787` `make_call` calls `original_function(*args, **kwargs)`, awaits the result when it is awaitable, records deployment usage for it ([RDISP-177]), passes it through `set_response_headers` (router-deployments, [RDEPLOY-147]) for the requested `model`, and returns it.
- [RDISP-151] {confirmed} `litellm/router.py:8504-8549`, `litellm/types/router.py:1238-1255` The keys `mock_testing_fallbacks`, `mock_testing_context_fallbacks` and `mock_testing_content_policy_fallbacks` are always popped from the kwargs, and string values are converted with `str_to_bool`. The first one exactly `True`, in that order, raises with `llm_provider=""`. Each message is `This is a mock exception for model=<group>, to trigger a fallback.` followed by one list, where `<group>` is the request's `model`. The list is the value resolved by [RDISP-093], rendered with Python `str()`, so `None` prints as `None` and a list as its repr. The exception classes add their own prefixes. Rendered for group `g` with nothing configured:
  - `mock_testing_fallbacks` raises `InternalServerError`; the lead sentence is followed by one space and `Fallbacks=` plus the list. Its message is `litellm.InternalServerError: This is a mock exception for model=g, to trigger a fallback. Fallbacks=None`.
  - `mock_testing_context_fallbacks` raises `ContextWindowExceededError`. After the lead sentence come one space and 20 more spaces (a source line continuation), then `Context_Window_Fallbacks=None`. The prefix is `litellm.ContextWindowExceededError: litellm.BadRequestError: `.
  - `mock_testing_content_policy_fallbacks` raises `ContentPolicyViolationError` with the same 21-space gap, then `Context_Policy_Fallbacks=None` (spelled `Context_`, not `Content_`). The prefix is `litellm.BadRequestError: litellm.ContentPolicyViolationError: `.
  - The dispatcher then handles these like real errors. With nothing configured the caller sees the message plus [RDISP-115]'s ` No fallback was attempted.` text. The context-window and content-policy mocks also carry the [RDISP-109] or [RDISP-110] hint before that text.
- [RDISP-152] {confirmed} `litellm/router.py:8789-8813` `mock_testing_rate_limit_error` is popped on the first attempt, so retries do not see it. When it is exactly `True`, a `RateLimitError` is raised with `llm_provider=""`, rendered for group `g` as `litellm.RateLimitError: This is a mock exception for model=g, to trigger a rate limit error.`, with the request's `model` in place of `g`. It then goes through the retry gate and the fallback dispatcher like any other first-attempt error, and later attempts call the real provider. The error's `num_retries` is the deployment's `litellm_params.num_retries` when the group has exactly one deployment, else `None`.
- [RDISP-153] {confirmed} `litellm/router.py:8579`, `litellm/router.py:8602`, `litellm/router.py:8696` The request's `num_retries` is popped before the worker runs, so this module never forwards it to the SDK call. Preventing the provider client from retrying on top of the router loop is left to deployment binding (router-calls, [RCALL-064], which merges the `max_retries` `0` default of [RSETUP-043]), and the tests pin exactly `1 + router retries` upstream requests.

### Retry eligibility (`should_retry_this_error`)
- [RDISP-155] {confirmed} `litellm/router.py:8832-8877` Checks run in this order and the first failing check re-raises `error`. If none fails, the result is `True`:
  1. The error is a `ContextWindowExceededError` and `context_window_fallbacks` is not `None`.
  2. The error is a `ContentPolicyViolationError` and `content_policy_fallbacks` is not `None`.
  3. `status_code` is present, `litellm.should_retry(status_code)` is false, and the status is not 401 or 403.
  4. The error is a `NotFoundError`.
  5. The error is an `openai.RateLimitError`, there are 0 healthy deployments, and `regular_fallbacks` is non-empty.
  6. The error is an `openai.AuthenticationError` or `PermissionDeniedError` and the group has at most 1 deployment in total.
  7. There are 0 healthy deployments.
- [RDISP-156] {confirmed} `litellm/utils.py:7502-7528` `litellm.should_retry(status)` is true only for 408, 409, 429 and every status >= 500. Every other status is non-retryable, including 400, 401, 403, 404 and 422 and any status below 400.
- [RDISP-157] {confirmed} `litellm/router.py:8832-8838` A `healthy_deployments` or `all_deployments` value that is `None` or not a list counts as 0 deployments.
- [RDISP-158] {confirmed} `litellm/router.py:8849-8851`, `litellm/router.py:8864-8870` 401 and 403 errors are retried only when the group has more than one deployment in total, so a single-deployment group never retries an authentication or permission error.

### Backoff (`_time_to_sleep_before_retry`)
- [RDISP-160] {confirmed} `litellm/router.py:8926-8930` The backoff is `0` seconds when the group does not have exactly 1 deployment and at least one healthy deployment remains.
- [RDISP-161] {confirmed} `litellm/router.py:8932-8953` Otherwise the delay comes from `litellm.calculate_retry_after` with `min_timeout` set to the router's `retry_after` (default `0`). It uses the response headers of the exception: `e.litellm_response_headers` when present, else `e.response.headers`.
- [RDISP-162] {confirmed} `litellm/utils.py:7534-7591`, `litellm/utils.py:73-75`, `litellm/constants.py:566-568`, `litellm/litellm_core_utils/env_utils.py:26-34` The calculated delay, in seconds, is chosen as follows. `jitter` is `JITTER * random()`, a value in [0, `JITTER`) with default `JITTER` 0.75 s:
  - The `retry-after` header is read as integer seconds. Failing that it is read as an HTTP date, giving the whole seconds from wall-clock now until that date, truncated toward zero. Lookup is case-insensitive for `httpx.Headers` and exact-case `retry-after` for a plain dict.
  - A value in the range (0, 60] seconds is returned as the value plus jitter. This path ignores both `min_timeout` and `MAX_RETRY_DELAY`, so `retry-after: 30` waits 30 s plus jitter, and `retry-after: 5` under `min_timeout` 20 waits 5 s plus jitter.
  - A missing, unparsable, non-integer (such as `1.5`), zero, negative or over-60 value falls to the exponential path. So does an absent header set.
  - The exponential path computes `INITIAL_RETRY_DELAY * 2^(max_retries - remaining_retries)`, raises it to `min_timeout` if lower, then caps it at `MAX_RETRY_DELAY`, and adds jitter. The cap is applied after the floor, so a `min_timeout` above the cap yields the cap.
  - With the defaults (`INITIAL_RETRY_DELAY` 0.5 s, `MAX_RETRY_DELAY` 8.0 s) and `max_retries` 3, the base delay is 0.5 s at `remaining_retries` 3, 1.0 s at 2 and 4.0 s at 0. With `max_retries` 5 and `remaining_retries` 0 it is 8.0 s, not 16.
  - The three constants are floats read from the environment once, when `litellm` is imported. A blank or unparsable value keeps the default, and an unparsable one is warned about once.
- [RDISP-165] {confirmed} `litellm/router.py:8879-8885`, `litellm/litellm_core_utils/asyncify.py:107-128` `function_with_fallbacks` runs `async_function_with_fallbacks` to completion synchronously. It uses a new event loop in the calling thread, or, when an event loop is already running there, a new loop inside a single worker thread while the caller blocks.

### Success and usage callbacks
- [RDISP-170] {confirmed} `litellm/router.py:8967-8971` `deployment_callback_on_success` does nothing (returns `None`) for `call_type` `_arealtime` and for the batch-retrieve call types `aretrieve_batch` and `retrieve_batch`. Batch polls therefore never feed per-minute counters.
- [RDISP-171] {confirmed} `litellm/router.py:8972-8983` `deployment_callback_on_success` also returns `None` without counting when any of these hold:
  - `standard_logging_object` is missing. The `ValueError` this raises is swallowed.
  - `litellm_params.metadata` is `None`.
  - `model_group` or `model_info.id` is missing.
  - The id no longer names a registered deployment.
- [RDISP-172] {confirmed} `litellm/router.py:8985-8989`, `litellm/router_utils/router_callbacks/track_deployment_metrics.py:45-59` For every counted success, the in-memory key made of the deployment id (as a string) plus `:successes`, for example `dep-1:successes`, is incremented by 1 with a 60 s TTL, regardless of whether TPM/RPM limits are configured.
- [RDISP-173] {confirmed} `litellm/router.py:8991-9001` The success callback then adds usage for the deployment:
  - Tokens are `standard_logging_object.total_tokens` minus any tokens already counted when the response was produced ([RDISP-178]), floored at 0.
  - The RPM increment is 1 only if nothing was counted earlier, and 0 otherwise.
  - The callback returns the TPM key, or `None` when nothing was written.
- [RDISP-174] {confirmed} `litellm/router.py:9003-9006` Any exception inside `deployment_callback_on_success` is logged at DEBUG and swallowed.
- [RDISP-177] {confirmed} `litellm/router.py:9013-9023` `increment_deployment_usage_for_response` does nothing when the response is `None`, as for session wrappers. It also does nothing when no metadata bucket (`metadata` or `litellm_metadata`) contains `model_info`, when the request `model` is not a string, or when `model_info.id` is missing.
- [RDISP-178] {confirmed} `litellm/router.py:9024-9035`, `litellm/router_utils/add_retry_fallback_headers.py:191-200` `increment_deployment_usage_for_response` writes the counted token count into the metadata bucket under the router's counted-tokens key, then adds those tokens and 1 request to the deployment's counters. The token count is the response's `usage.total_tokens`, else `input_tokens + output_tokens`, else 0.
- [RDISP-179] {confirmed} `litellm/router.py:9036-9042` If that increment fails, the counted-tokens key is removed again so the logging callback counts the full usage later. All errors are logged at DEBUG and swallowed.
- [RDISP-181] {confirmed} `litellm/router.py:9056-9080` Usage counting writes nothing and returns `None` in any of these cases:
  - The deployment id is unknown.
  - None of `tpm`/`rpm` is set on the deployment, its `litellm_params` or its model info, and it has no input/output-token limits.
  - Both the token count is <= 0 and the RPM increment is <= 0.
- [RDISP-182] {confirmed} `litellm/router.py:9082-9092` Counter keys are `global_router:{id}:{model}:tpm:{HH-MM}` and `global_router:{id}:{model}:rpm:{HH-MM}`:
  - `HH-MM` is the current UTC minute.
  - `{model}` is the deployment name from the request metadata, rendered as the literal `None` when absent.
  - Both increments carry a 60 s TTL.
- [RDISP-183] {confirmed} `litellm/router.py:9093-9102` Both increments go in one pipeline call to the router cache, which is in-memory plus optional Redis. When Redis is configured and returns post-increment values, the local in-memory copies are overwritten with those integer values and a 60 s TTL. The TPM key is returned.
- [RDISP-187] {confirmed} `litellm/router.py:9104-9139` `sync_deployment_callback_on_success` handles each case as follows:
  - Batch retrieves return `None`.
  - Otherwise it reads `kwargs["litellm_params"]` without a guard, so a missing key raises `KeyError`.
  - It returns `None` when the metadata is `None` or `model_group`/`model_info.id` is missing.
  - Otherwise it converts an integer id to a string, increments `<id>:successes`, and returns that key.

### Failure callbacks
- [RDISP-190] {confirmed} `litellm/router.py:9157-9204` `deployment_callback_on_failure` returns `False` (no cooldown, no failure count) in these cases, checked in order:
  1. The exception came from advisor orchestration.
  2. It is a provider 404 from a background-response poll.
  3. It is a 408 caused by a caller-set timeout.
  4. It is an OAuth authentication failure scoped to the caller on the deployment named by `model_info.id`.
- [RDISP-191] {confirmed} `litellm/router.py:9206-9231` The cooldown time is the first of these that applies:
  1. A `cooldown_time` >= 0 found first in the request's `model_info`, then in `litellm_params`.
  2. A `retry-after` value >= 0 from the exception's response headers.
  3. The router's `cooldown_time`, which defaults to `DEFAULT_COOLDOWN_TIME_SECONDS`, 5 s.
- [RDISP-192] {confirmed} `litellm/router.py:9233-9236` A `model_info` dict without an `id` returns `False`.
- [RDISP-193] {confirmed} `litellm/router.py:9237-9256` With an id, the failure callback increments the in-memory key made of the id plus `:fails`, for example `dep-1:fails` (60 s TTL). It then asks the cooldown handler (failure-handling, [FAILURE-021]) whether to cool the deployment down, passing the status, the exception, the id, the cooldown time, the request's `model_group` and the full kwargs, and returns the handler's boolean.
- [RDISP-194] {confirmed} `litellm/router.py:9257-9261` When `model_info` is not a dict, the failure callback logs at DEBUG and returns `False`.
- [RDISP-195] {confirmed} `litellm/router.py:9263-9264` Unlike the success callbacks, `deployment_callback_on_failure` re-raises every internal exception.
- [RDISP-196] {inferred} `litellm/router.py:1528-1547` The four callbacks are registered once per router on the process-global litellm callback lists, so they fire for every litellm call made while the router exists, not only for routed calls. They do nothing for calls without router metadata.
- [RDISP-197] {confirmed} `litellm/router.py:9266-9297` `async_deployment_callback_on_failure` behaves as follows:
  - It skips batch retrieves.
  - Otherwise it reads `kwargs["litellm_params"]["metadata"]` unguarded.
  - It returns when `model_group` or the deployment id is missing.
  - Otherwise it increments the RPM key ([RDISP-182]) by 1 (60 s TTL) in the router cache, so failed requests count toward RPM even when no limits are configured.

### Retry breadcrumbs (`log_retry`)
- [RDISP-200] {confirmed} `litellm/router.py:9320-9321` `log_retry` writes to `litellm_metadata` when that key exists in the kwargs (whatever its value), else to `metadata`. When neither key exists it raises `KeyError`, and when the chosen key holds a non-mapping such as `None` it raises `AttributeError`.
- [RDISP-201] {confirmed} `litellm/router.py:9322-9332` Each call builds one flat record with exactly five keys. Each value comes from the source below and is recorded as `None` when that source has the wrong type:
  - `model_group`: the kwargs' `model`, when it is a `str`.
  - `deployment_id`: the bucket's `model_info.id`, when `model_info` is a mapping and the id is a `str`.
  - `exception_type`: the exception's class name, for example `RateLimitError`.
  - `exception_string`: `str(e)`, not redacted, for example `litellm.RateLimitError: m5`.
  - `attempted_retries`: the bucket's `attempted_retries`, when its type is exactly `int` (a `bool` is recorded as `None`). The retry loop sets it to `0` before the first attempt and to `i + 1` before retry `i` ([RDISP-133], [RDISP-143]), so a record carries the number of the attempt that failed.
- [RDISP-202] {confirmed} `litellm/router.py:9333-9339`, `litellm/router.py:1017` The bucket's `previous_models` becomes a tuple of at most `RETRY_BREADCRUMB_LIMIT` (4) records: the last 3 earlier records plus the new one. Earlier values that are not lists or tuples are discarded.
- [RDISP-203] {confirmed} `litellm/router.py:9340-9341` `request_retry_count` becomes the previous value plus 1. A previous value that is missing, not exactly an `int`, or negative counts as 0, so a planted negative count cannot raise the cap. For example, a request with router `num_retries=5` against a single deployment that always raises `RateLimitError`, carrying a planted `request_retry_count` of `-100`, makes 6 calls. It ends with `request_retry_count` `6` and `previous_models` holding the 4 records whose `attempted_retries` are 2, 3, 4 and 5.
- [RDISP-204] {inferred} `litellm/router.py:9356` `request_retry_count` counts every failed attempt of the request across all fallback hops. The SDK's `litellm.num_retries_per_request` cap reads it and fails further attempts with `Max retries per request hit!` (inferred from tests; the cap is enforced outside this module).
- [RDISP-205] {confirmed} `litellm/router.py:9342-9354` When the bucket's `routing_decision.router_model_name` is a string, `log_retry` emits the trace event `litellm.routing.retry`. Its attributes are `litellm.routing.router_model_name`, `litellm.retry.count`, `error.type`, and, when available, `litellm.deployment.model_group` and `litellm.deployment.id`.
- [RDISP-206] {confirmed} `litellm/router.py:9355-9357` `log_retry` mutates the existing bucket in place and returns the same kwargs object. It never copies request kwargs, messages or credentials into the record.

### Healthy-deployment lookups and small helpers
- [RDISP-207] {confirmed} `litellm/router.py:9299-9311`, `litellm/litellm_core_utils/core_helpers.py:341-355` `_get_metadata_variable_name_from_kwargs` returns `litellm_metadata` when that key is present in the kwargs (any value), and `metadata` otherwise.
- [RDISP-208] {confirmed} `litellm/router.py:9359-9376` `_update_usage(deployment_id)` keeps an in-memory, local-only request counter keyed by the bare deployment id. A missing value is set to 1 with a 60 s TTL, and an existing value is incremented and rewritten without a TTL argument. It returns the new count, with no locking between the read and the write.
- [RDISP-210] {confirmed} `litellm/router.py:9538-9556` `_async_get_healthy_deployments` takes the candidate list from the shared availability checks with the request kwargs. When those checks resolve to a single specific deployment, it returns a pair of an empty list and that deployment's dict (not a list). Any exception from those checks is swallowed and treated as an empty candidate list.
- [RDISP-211] {confirmed} `litellm/router.py:9558-9567` From the candidates, `_async_get_healthy_deployments` removes ids in cooldown (async cooldown read) and then blocked deployments, and returns `(healthy, all)`.
- [RDISP-212] {confirmed} `litellm/router.py:9518-9536` The synchronous `_get_healthy_deployments` passes no request kwargs. It returns a bare `[]`, not a tuple, when a specific deployment resolves, and `(healthy, all)` otherwise.
- [RDISP-213] {confirmed} `litellm/router.py:9524-9527`, `litellm/router.py:9553-9556` Because selection errors are swallowed, an unknown model group yields no healthy deployments. The retry gate ([RDISP-155], check 7) then re-raises the original error instead of a selection error.
- [RDISP-214] {inferred} `litellm/router.py:9553-9554`, `litellm/router.py:8621-8662`, `litellm/router.py:8874-8875` A request whose `model` resolves to one specific deployment (for example a deployment id) sees zero healthy deployments in the retry gate. Without an applicable retry policy it is therefore never retried and goes straight to the fallback dispatcher. This is inferred because the dict-versus-list result comes from availability checks owned by router-selection ([RSELECT-020], [RSELECT-042]).

### Pre-call checks, slots and admission
- [RDISP-215] {confirmed} `litellm/router.py:9569-9583` `routing_strategy_pre_call_checks(deployment)` calls `pre_call_check(deployment)` on every `CustomLogger` in `litellm.callbacks`, in list order. The first exception propagates unchanged.
- [RDISP-216] {confirmed} `litellm/router.py:9602-9623` In `async_routing_strategy_pre_call_checks`, a `litellm.RateLimitError` from a callback's `async_pre_call_check` does three things before re-raising:
  - It schedules the logging object's failure handlers when one is given.
  - It puts that deployment id into cooldown for the router's `cooldown_time` with the error's status.
  - It re-raises the error.
- [RDISP-217] {confirmed} `litellm/router.py:9624-9634` Any other exception from a callback's `async_pre_call_check` schedules the failure handlers (when a logging object is given) and is re-raised without a cooldown. The first failing callback stops the remaining callbacks.
- [RDISP-218] {confirmed} `litellm/router.py:9701-9716` `_deployment_slot` holds the deployment's `max_parallel_requests` slot, when it has one, around the provider call. It runs the async pre-call checks inside the slot and releases the slot on exit or error. Entering a full slot raises `RateLimitError` (429) naming the deployment id, as pinned by a test.
- [RDISP-219] {confirmed} `litellm/router.py:9718-9760` `async_callback_filter_deployments` chains the candidate list through each `CustomLogger.async_filter_deployments` in `litellm.callbacks` order, each receiving the previous output. A callback exception schedules the failure handlers (when a logging object is given) and is re-raised. The final list is returned.
- [RDISP-220] {confirmed} `litellm/router.py:9636-9647` `async_admit_deployment_turn` admits each turn of a long-lived Responses websocket. It first re-reads the deployment from the live registry by `model_info.id` (non-`None` fields only), so limits changed after the socket opened apply. It falls back to the snapshot taken when the socket opened.
- [RDISP-221] {confirmed} `litellm/router.py:9648-9663` When a deployment budget limiter exists and rejects the deployment with `ValueError`, the turn raises `litellm.RateLimitError` with category `LITELLM_RATE_LIMIT`, `llm_provider=""` and the limiter's message.
- [RDISP-222] {confirmed} `litellm/router.py:9669-9677` For routing strategies other than `simple-shuffle` that have a selector, the turn is also run through the selector over just this deployment. `litellm_logging_obj` is removed from the routing kwargs first.
- [RDISP-223] {confirmed} `litellm/router.py:9678-9699` When the selector picks nothing, the turn raises `litellm.RateLimitError` (category `LITELLM_RATE_LIMIT`) carrying the router's no-deployments message. Otherwise the selector's own pre-call check runs.
- [RDISP-224] {confirmed} `litellm/router.py:9664-9667` Finally the turn runs the async pre-call checks on a copy of the deployment without its input/output-token limits, so turns never reserve OTPM/ITPM capacity.

### Fallback-availability predicates
These answer "could the dispatcher still route this failure somewhere?" for callers that must decide whether to convert a response into an error or to hold back stream frames.
- [RDISP-230] {confirmed} `litellm/router.py:9378-9385`, `litellm/router.py:1473-1478` `_has_default_fallbacks` is true only when the router-level `fallbacks` (never the per-request value) contain a dict with key `"*"`. Constructor `default_fallbacks`, or `litellm.default_fallbacks`, is appended to the router's `fallbacks` as such an entry.
- [RDISP-231] {confirmed} `litellm/router.py:8897-8908` `_get_first_default_fallback` returns the first element of the first `"*"` entry whose value is a non-empty list. It returns `None` when router `fallbacks` is `None`, has no `"*"` entry, or that entry is empty.
- [RDISP-232] {confirmed} `litellm/router.py:8887-8895` `_get_fallback_model_group_for_lookup_groups` returns only the resolved chain (specific key first, then `"*"`) and discards the generic index.
- [RDISP-233] {confirmed} `litellm/router.py:9387-9410` `_has_content_policy_fallback(model_group, kwargs)` uses the request's `content_policy_fallbacks` when that key is present, else the router's value:
  - When that list is not `None`, it is true only if the chain resolved over the lookup groups still has a target this request has not attempted. Router default fallbacks are not consulted in that case.
  - When the list is `None`, it is true only when router default fallbacks exist.
- [RDISP-234] {confirmed} `litellm/router.py:9412-9433` `_refusal_fallback_available` evaluates in order, stopping at the first that applies:
  1. Fallbacks are disabled for the request: false.
  2. A content-policy list is configured: the result of [RDISP-233].
  3. Router default fallbacks exist: true.
  4. Request or router `fallbacks` is `None`: false.
  5. Otherwise: whether the generic chain resolved over the lookup groups has an unattempted target.
- [RDISP-235] {confirmed} `litellm/router.py:9435-9451` `_anthropic_messages_order_levels` returns the sorted distinct non-`None` deployment `order` values that the dispatcher would use. It reads the pre-routing tier if selected, else the requested group, filtered by `metadata.user_api_key_team_id`.
- [RDISP-236] {confirmed} `litellm/router.py:9453-9483` `_anthropic_messages_stream_can_fall_back` evaluates in order, stopping at the first that applies:
  1. Fallbacks are disabled for the request: false.
  2. Weighted failover is enabled: true.
  3. There are two or more order levels and one is higher than the current `_target_order` (or than the lowest level when unset): true.
  4. A content-policy list exists and [RDISP-233] holds: true.
  5. Request or router `fallbacks` is empty or `None`: false.
  6. `fallbacks` is in non-standard format: true.
  7. Otherwise: whether the resolved generic chain has an unattempted target.
- [RDISP-237] {confirmed} `litellm/router.py:9485-9497` `_should_raise_content_policy_error` is false when the response has choices and the first choice's `finish_reason` is not `content_filter`. Otherwise, including when there are no choices, it returns [RDISP-233], so a filtered response is turned into an error only when a content-policy or default fallback could serve it.
- [RDISP-238] {confirmed} `litellm/router.py:9499-9516` `_should_raise_anthropic_refusal_error` is true only when all of these hold, so a refusal with nothing configured is returned to the client unchanged:
  - The SDK function is named `anthropic_messages`.
  - The response is a safeguard refusal carrying `stop_details`.
  - The refusal-fallback check [RDISP-234] holds.
- [RDISP-239] {inferred} `litellm/router_utils/fallback_event_handlers.py:243-252` A chain "has an unattempted target" when it is not `None` and either:
  - the request carries no attempted-target set, or
  - some entry has no attempt key or an attempt key not yet recorded.

### Deployment ids and pricing inheritance
- [RDISP-240] {confirmed} `litellm/router.py:9770-9800` `generate_model_id(model_group, litellm_params)` returns the lowercase hex SHA-256 of the UTF-8 encoding of a string built from:
  - the group name,
  - then, for each `litellm_params` key and value in insertion order, the key and the value rendered as the raw string (for `str`), JSON (for `dict`), or `str(x)` otherwise,
  - with no separators.
  - `str(x)` gives Python's rendering: `10` renders `10`, `True` renders `True`, `None` renders `None`, and a list renders as its repr such as `['a', 1]`.
  - JSON is Python's `json.dumps` with default settings: keys in insertion order (not sorted), separators `, ` and `: `, and non-ASCII characters escaped. For example `{"b": 1, "a": [1, "é"]}` renders as `{"b": 1, "a": [1, "é"]}`. Nested non-serializable objects follow [RDISP-243].
  - Worked example: `generate_model_id("g", {"model": "gpt-4", "rpm": 10})` hashes the string `gmodelgpt-4rpm10` and returns `f76357655de89c1e1407eb07be8724755b0d7f4cc8460e0b2bd206819f0fd91a`.
- [RDISP-241] {confirmed} `litellm/router.py:9781-9797` Because parts are joined without separators and in insertion order, the same params in a different key order produce a different id. Distinct params whose concatenations coincide (for example `{"ab": "c"}` and `{"a": "bc"}`) produce the same id.
- [RDISP-242] {confirmed} `litellm/router.py:9790-9795` Only values that are dicts get restart-stable rendering. A non-dict, non-string value such as an arbitrary object, or a list containing one, is rendered with `str()`, which can embed a memory address and make the id differ across restarts.
- [RDISP-243] {confirmed} `litellm/router.py:9762-9768`, `litellm/router.py:9784-9795` Inside a dict-valued param, any non-JSON-serializable value at any depth is rendered as a JSON string naming its class's module and qualified name. For example an instance of class `Foo` defined in `__main__` renders as `"__main__.Foo"`, so equivalent instances give the same id across restarts. Nested dict keys get no such treatment:
  - A key that is not `str`, `int`, `float`, `bool` or `None`, such as a tuple or an object, makes `generate_model_id` raise `TypeError` (`keys must be str, int, float, bool or None, not tuple`).
  - `int`, `float`, `bool` and `None` keys are rendered as JSON strings: `1` becomes `"1"` and `None` becomes `"null"`.
  - Top-level `litellm_params` keys are not JSON-encoded; a non-`str` top-level key is rendered with `str()`.
- [RDISP-244] {confirmed} `litellm/router.py:9802-9829` `_inherit_builtin_cache_pricing(model_info, backend_model, custom_llm_provider)` fills, in place, each of these fields that is missing or `None` from the backend model's built-in cost-map entry: `cache_creation_input_token_cost`, `cache_creation_input_token_cost_above_1hr`, `cache_creation_input_token_cost_above_200k_tokens`, `cache_read_input_token_cost` and `cache_read_input_token_cost_above_200k_tokens`. User-set values always win, and the call is a no-op when all five are set or the backend model is unknown.
- [RDISP-245] {confirmed} `litellm/router.py:9831-9839` `_cost_map_backend_model(deployment)` returns the first non-empty string among `model_info.base_model` and `litellm_params.base_model`, else `litellm_params.model`.
- [RDISP-246] {confirmed} `litellm/router.py:9841-9864` `_inherit_builtin_service_tier_pricing` copies into `model_info` (deep copies) every backend cost-map field ending in a service-tier suffix that is missing or `None` on the deployment and non-`None` in the backend. It does nothing in any of these cases:
  - The deployment has PTU terms and PTU cost attribution is enabled.
  - The deployment sets neither `input_cost_per_token` nor `output_cost_per_token`.
  - The backend model is unknown.
  - The backend cost-map entry is not a dict.
- [RDISP-247] {inferred} `litellm/router.py:10026-10035`, `litellm/router.py:11097-11104`, `litellm/litellm_core_utils/llm_cost_calc/utils.py:70-81` The pricing helpers are called by deployment pricing registration (router-deployments, [RDEPLOY-020]), with the backend model from [RDISP-245]. The service-tier suffixes are `_flex`, `_balanced`, `_priority` and `_ultrafast`.

## Validation rules
This module validates very little; most inputs pass through to the SDK call or to resolvers owned by other modules.
- [RDISP-250] {confirmed} `litellm/router.py:8462-8467`, `litellm/router.py:8570-8577` Per-request `fallbacks`, `context_window_fallbacks`, `content_policy_fallbacks` and `model_group_retry_policy` are not shape-checked here. They go straight to the chain resolvers, and an explicit `None` overrides the router default.
- [RDISP-251] {confirmed} `litellm/router.py:8579-8584`, `litellm/router.py:8667`, `litellm/router.py:8690` The request `num_retries` is not type-coerced. Only `None` is replaced by a default, and a non-integer value such as the string `"2"` fails the comparison or loop with `TypeError` once the first attempt has failed.
- [RDISP-252] {confirmed} `litellm/router.py:6942-6946` The only input check in file creation is that `file` and `purpose` are truthy ([RDISP-062]). The file's content and JSONL validity are not checked here.
- [RDISP-253] {confirmed} `litellm/router.py:6695`, `litellm/router.py:8463`, `litellm/router.py:8469`, `litellm/router.py:8520`, `litellm/router.py:8571-8579`, `litellm/router.py:8796` Unknown keyword arguments are forwarded unchanged to the SDK call. Only the router-control keys are removed along the way: `specific_deployment`, `disable_fallbacks`, `mock_timeout`, the four `mock_testing_*` flags, `original_function`, the three fallback lists, `model_group_retry_policy` and `num_retries`.
- [RDISP-254] {confirmed} `litellm/router.py:6670`, `litellm/router.py:7896-7917`, `litellm/router.py:7997-8005` The generic sync and async chains require a `model` argument. Missing it raises `TypeError` before any routing, while the vector-store, container and interactions routers avoid that by calling the SDK directly when no `model` is present.
- [RDISP-258] {confirmed} `litellm/router.py:8191-8201`, `litellm/router.py:8224-8228` Caller-supplied `max_fallbacks`, `fallback_depth` and `_target_order` kwargs are trusted as-is. A request can therefore raise or lower its own fallback depth limit, or start the order walk at a chosen level.

## Error handling
| Claim | Condition | Raised or returned | Logged | Retried / fallback | Swallowed |
|---|---|---|---|---|---|
| [RDISP-101] | `disable_fallbacks`, no `model`, guardrail, or unsupported-params 400 | original exception, unchanged | debug traceback | no | no |
| [RDISP-155] | non-retryable status (not 401/403), `NotFoundError`, no healthy deployments, and so on | the error itself | none | no retry; fallback dispatcher still runs | no |
| [RDISP-147] | retries exhausted | latest error, with `num_retries`/`max_retries` set for exact litellm types | INFO per attempt (worker) | fallback dispatcher next | no |
| [RDISP-145] | a retry hits a non-retryable error | that latest error, without retry attributes | none | fallback dispatcher next | no |
| [RDISP-115] | all fallback paths exhausted or none configured | original exception, with outcome suffix when exposure is on | ERROR line with cooldown info whenever the main fallback block raised ([RDISP-114]), including a dedicated or generic chain that did not resolve; none when nothing was configured | n/a | fallback errors folded into the message |
| [RDISP-108] | context-window (or content-policy, [RDISP-110]) error, dedicated list set but no chain for the group | original exception, suffix `No fallback was attempted.`; generic `fallbacks` not tried | ERROR line | no | no |
| [RDISP-105] | an order-level walk fails | last walk error, no suffix | per-hop logs | n/a | no |
| [RDISP-124] | weighted failover walk fails with an API or router rate-limit error | `None`, continue to regular chain | none | yes | yes |
| [RDISP-062] | file or purpose missing | `Exception("file and file_purpose are required for create_file")` | exception log with kwargs | retried by loop if eligible | no |
| [RDISP-067] | no uploads made | `Exception("No healthy deployments found.")` | exception log | loop | no |
| [RDISP-079] | model list `None` (retrieve or list batches) | `Exception("Router not yet initialized.")` | none | no | no |
| [RDISP-083] | no deployment returned a batch | first probe error, or `Exception("Unable to find batch in any model. Received errors - []")` | stderr traceback per probe | no | per-probe errors collected |
| [RDISP-086] | a deployment's list call fails | treated as `None` | none | no | yes |
| [RDISP-041] | assistants call without provider or config | `Exception("'custom_llm_provider' must be set. ...")` | none | no | no |
| [RDISP-221] | budget limiter rejects a websocket turn | `litellm.RateLimitError` (`LITELLM_RATE_LIMIT`) | none | no | no |
| [RDISP-216] | async pre-call check raises `RateLimitError` | same error; deployment cooled down | failure handlers scheduled | caller's loop | no |
| [RDISP-174] | success-callback internals fail | nothing | DEBUG | n/a | yes |
| [RDISP-195] | failure-callback internals fail | re-raised | none | n/a | no |
| [RDISP-055] | `aembedding`, `acreate_file`, `acreate_batch`, `aretrieve_batch` or `acancel_batch` fails | re-raised after scheduling an alert task | alert (failure-handling, [FAILURE-175]) | n/a | no |

- [RDISP-255] {confirmed} `litellm/router.py:6826-6829`, `litellm/router.py:6886-6894`, `litellm/router.py:7126-7134`, `litellm/router.py:7293-7301`, `litellm/router.py:7324-7332` These entry points schedule the exception alert with `asyncio.create_task` and do not await it before re-raising: `aembedding`, `acreate_file`, `acreate_batch`, `aretrieve_batch` and `acancel_batch`. `embedding`, `alist_batches`, `avector_store_create` and the synchronous generic call schedule no alert.
- [RDISP-256] {confirmed} `litellm/router.py:8402-8415`, `litellm/router.py:8166-8167` The ERROR line written after a failed fallback attempt contains only the redacted, truncated failure detail and cooldown info, not a traceback. The full traceback is emitted only at DEBUG.
- [RDISP-257] {confirmed} `litellm/router.py:8320-8327`, `litellm/router.py:8352-8359`, `litellm/router.py:8374-8379` Fallback configuration embedded in hints and logs is passed through `mask_sensitive_structure`, so inline credentials in dict-form fallbacks are masked even when debug exposure is on.

## State and data
- [RDISP-260] {confirmed} `litellm/router.py:6708`, `litellm/router.py:6736`, `litellm/router.py:6782`, `litellm/router.py:6801-6802`, `litellm/router.py:7015`, `litellm/router.py:7189` The in-process counters `total_calls`, `success_calls` and `fail_calls` are keyed inconsistently:
  - `total_calls` and `success_calls` use the deployment's model string.
  - `fail_calls` uses the requested group name on the generic, file, batch and vector-store paths, and the deployment model on the embedding paths.
  - None of them is reset by this module.
- [RDISP-261] {confirmed} `litellm/router.py:8446-8464`, `litellm/router.py:8586-8598`, `litellm/router.py:8124`, `litellm/router.py:9026`, `litellm/router.py:9355-9356` The router writes these keys in place into the caller's metadata dict (`metadata` or `litellm_metadata`), so a proxy holding the same dict observes them:
  - `attempted_fallbacks` and `original_model_group`.
  - `_disable_fallbacks`.
  - `attempted_retries`, `max_retries` and `model_group_size`.
  - `previous_models` and `request_retry_count`.
  - `_failover_excluded_ids` and the counted-tokens key.
- [RDISP-262] {confirmed} `litellm/router.py:8986-8989`, `litellm/router.py:9237-9240`, `litellm/router.py:9082-9101`, `litellm/router.py:9286-9297`, `litellm/router.py:9366-9374` Cache keys written by this module:
  - `<id>:successes` and `<id>:fails`: in-memory only, 60 s TTL.
  - `global_router:<id>:<name>:tpm:<HH-MM>` and `global_router:<id>:<name>:rpm:<HH-MM>`: in-memory plus Redis when configured, 60 s TTL.
  - The bare `<id>` request counter: in-memory only, 60 s TTL set on creation.
- [RDISP-263] {confirmed} `litellm/router.py:7002-7008` File creation records which provider file id belongs to which deployment only in the returned object's hidden params (`model_file_id_mapping`). Nothing is persisted by the router.

## External interactions
- [RDISP-265] {confirmed} `litellm/router.py:6787-6795`, `litellm/router.py:6852-6860`, `litellm/router.py:6974-6982`, `litellm/router.py:7170-7178`, `litellm/router.py:7248-7254`, `litellm/router.py:7414` SDK calls made here (`litellm.embedding`, `aembedding`, `acreate_file`, `acreate_batch`, `aretrieve_batch`, `acancel_batch`, `alist_batches`) get no timeout from this module. Timeouts come only from bound deployment params or caller kwargs, and this module has no overall deadline across retries and fallbacks.
- [RDISP-266] {confirmed} `litellm/router.py:9082`, `litellm/router.py:9286-9287`, `litellm/router.py:8688`, `litellm/router.py:8761` Counter minutes use the UTC wall clock (`HH-MM`, so keys repeat daily). Backoff waits use `asyncio.sleep` on the event loop.
- [RDISP-267] {inferred} `litellm/utils.py:7576-7577` Backoff jitter is drawn from the process-global `random.random()` with no seed control.
- [RDISP-268] {confirmed} `litellm/router.py:7256-7258` `aretrieve_batch` prints each failing probe's traceback straight to stderr, outside the logging system.
- [RDISP-269] {confirmed} `litellm/router_utils/fallback_event_handlers.py:850`, `litellm/router_utils/fallback_event_handlers.py:871`, `litellm/router.py:4373`, `tests/unit/test_router/test_router_fallbacks.py:597-603` For a successful fallback, three INFO log lines appear in this order, as pinned by a log-sequence test. Rendered for a fallback from `gpt-3.5-turbo` to group `azure/gpt-3.5-turbo` they are `Falling back to model_group = azure/gpt-3.5-turbo`, then `litellm.acompletion(model=azure/gpt-4.1-mini)\x1b[32m 200 OK\x1b[0m`, then `Successful fallback b/w models.`. The first names the masked fallback target, and the second names the serving deployment's model.

## Configuration
| Claim | Setting | Source | Default | Effect here |
|---|---|---|---|---|
| [RDISP-131] | `num_retries` | request kwarg, deployment `litellm_params`, router | router value, else `0` | retry count |
| [RDISP-138] | `retry_policy`, `model_group_retry_policy` | router or request | `None` | per-error retry count; bypasses the eligibility gate |
| [RDISP-161] | `retry_after` | router | `0` | minimum backoff seconds |
| [RDISP-162] | `INITIAL_RETRY_DELAY`, `MAX_RETRY_DELAY`, `JITTER` | env | `0.5`, `8.0`, `0.75` | backoff shape |
| [RDISP-093] | `fallbacks`, `context_window_fallbacks`, `content_policy_fallbacks` | request or router | router values | fallback chains |
| [RDISP-271] | `max_fallbacks` | request or router | `litellm.max_fallbacks`, else `ROUTER_MAX_FALLBACKS` (`5`) | walk depth |
| [RDISP-106] | `enable_weighted_failover` | router | `False` | intra-group failover |
| [RDISP-101] | `fallback_on_unsupported_params` | router | `True` | whether unsupported-param 400s may fall back |
| [RDISP-191] | `cooldown_time` | deployment, header, router | `DEFAULT_COOLDOWN_TIME_SECONDS` (`5`) | cooldown seconds |
| [RDISP-050] | `cache_responses` | router | `False` | `caching` kwarg passed to SDK calls |
| [RDISP-041] | `assistants_config` | router | `None` | assistants provider and params |
| [RDISP-272] | `litellm.expose_router_debug_in_errors` | module global | `True` | debug hints and outcome text in exception messages |
| [RDISP-093] | `disable_fallbacks`, `include_fallback_errors` | request | `False` | no fallback; fallback-errors header |

- [RDISP-271] {inferred} `litellm/router.py:1446-1451`, `litellm/constants.py:53`, `litellm/router.py:1421`, `litellm/constants.py:151` The constructor defaults for `max_fallbacks` and `cooldown_time` are set in router-setup: `max_fallbacks` precedence is in [RSETUP-032], and the `cooldown_time` default (also used when `0` is passed) is in [RSETUP-027].
- [RDISP-272] {confirmed} `litellm/__init__.py:208`, `litellm/router.py:8326-8327`, `litellm/router.py:8380-8385`, `litellm/router.py:8418-8429` With `litellm.expose_router_debug_in_errors` (default `True`) set to false, no fallback hint, no "no fallback model group" text and no outcome text is appended, so the raised message carries only the provider error.
- [RDISP-273] {confirmed} `litellm/router.py:8465-8467`, `litellm/router.py:8572-8584`, `litellm/router.py:8199` Router-level settings are read on every call, not cached at construction, so runtime changes to the router's attributes affect the next call.

## Concurrency and ordering
- [RDISP-280] {confirmed} `litellm/router.py:6989-6997`, `litellm/router.py:7268-7271`, `litellm/router.py:7419` File uploads, batch-retrieve probes and batch listing start one concurrent task per deployment, with no concurrency bound.
- [RDISP-281] {inferred} `litellm/router.py:6997` Because uploads are gathered without `return_exceptions`, the first failure is raised while the other uploads keep running unobserved, so files may be created on some deployments with no mapping returned (standard `asyncio.gather` semantics).
- [RDISP-282] {confirmed} `litellm/router.py:8690-8761`, `litellm/router.py:8245-8293`, `litellm/router_utils/fallback_event_handlers.py:820-870` Retries of one request run strictly sequentially, and fallback targets are tried one at a time in chain order. Order-level entries go before external fallbacks, and weighted failover goes before non-standard, context-window, content-policy and generic chains.
- [RDISP-283] {confirmed} `litellm/router.py:9359-9376`, `litellm/router.py:6708`, `litellm/router.py:6730` `_update_usage` and the `total_calls`/`success_calls`/`fail_calls` counters are read-modify-write without locks. Only the Redis-backed TPM/RPM pipeline increments are atomic across processes.
- [RDISP-284] {confirmed} `litellm/router.py:8879-8885`, `litellm/litellm_core_utils/asyncify.py:117-128` `function_with_fallbacks` blocks its calling thread. When that thread already runs an event loop, the routed call runs on a separate loop in a helper thread.
- [RDISP-285] {confirmed} `litellm/router.py:8453-8461`, `litellm/router.py:9355-9356` Metadata writes mutate the caller's dicts in place, so a caller reusing one metadata dict across concurrent requests sees their stamps interleave.
- [RDISP-286] {confirmed} `litellm/router.py:8690-8705`, `litellm/router.py:6873-6894`, `litellm/router.py:7108-7134` Retries and fallback hops re-send the whole operation with no idempotency key, including non-idempotent ones. A retried `acreate_file` re-uploads to every healthy deployment, and a retried `acreate_batch` may create a second batch.
- [RDISP-287] {inferred} `litellm/router.py:95`, `litellm/router.py:8433`, `litellm/router.py:8568` `async_function_with_fallbacks` and `async_function_with_retries` are each wrapped by the Datadog tracer decorator, so each invocation, including every fallback hop, is a trace span when that tracer is active.

## Implementation notes
- The async wrapper returned by `factory_function` is one long `if/elif` chain keyed on `call_type`; the synchronous lists are tuples checked first. This structure is why unlisted call types return `None` ([RDISP-023]-[RDISP-026]) rather than raising.
- `include_fallback_errors` is normalized with `is True` in the entry point but the raw value also travels inside the walk kwargs; the walk's keyword parameter receives the raw value, which is why truthiness wins ([RDISP-119]).
- The success path records usage twice in two halves: once at response time (`increment_deployment_usage_for_response`) and once in the logging callback, which subtracts what was already counted ([RDISP-173], [RDISP-178]). The counted-tokens key in the request metadata is the hand-off between the two.
- `generate_model_id` is load-bearing: deployment ids appear in cooldown keys, usage keys, response hidden params (`model_id`) and the proxy's stored model ids, so its exact concatenation and hash ([RDISP-240]) are normative.

## Open questions and gaps
- Gap [RDISP-027]: does the sync `create_interaction` raise `TypeError` inside the async wrapper? Calling `Router().create_interaction(...)` once would settle it.
- [RDISP-290] {gap} `litellm/router.py:2291-2293`, `litellm/router.py:2507-2516`, `litellm/router.py:2543-2545`, `litellm/router.py:2566-2572` Are the bound names that match no dispatch branch ([RDISP-023]-[RDISP-026]) intentional, or should they raise or route? A caller of `router.aadapter_generate_content` or `router.video_edit` currently gets `None` or an un-awaited coroutine.
- [RDISP-291] {gap} `litellm/router.py:6989-6997` When one upload of a multi-deployment file creation fails, what happens to files already created on the other deployments? They are not cleaned up or reported, and it is unknown whether the proxy's managed-files layer compensates.
- [RDISP-292] {gap} `litellm/router.py:8462`, `litellm/router.py:8191-8203` Should `include_fallback_errors` follow the strict `is True` check that the entry point computes, or the truthiness that actually decides the header ([RDISP-119])? The two disagree for values such as `1`, and it is unknown which is intended.
- [RDISP-293] {gap} `litellm/router.py:9518-9536` Is the synchronous `_get_healthy_deployments` still used anywhere besides tests? It returns a bare `[]` instead of a `(healthy, all)` tuple when a specific deployment resolves, which a tuple-unpacking caller cannot handle.
- [RDISP-294] {gap} `litellm/router.py:8255-8259` Is it intended that a failed order-level walk raises the last level's error without the outcome suffix ([RDISP-105])? Every other dispatcher path raises the original error with that suffix.
- [RDISP-295] {gap} `litellm/router.py:8754-8761` Is the backoff sleep after the final failed retry ([RDISP-146]) intended? It delays every exhausted request by one more backoff interval before fallbacks start.

## Test evidence
| Claim | Test | What it pins |
|---|---|---|
| [RDISP-001] | `tests/unit/test_router/test_router.py::test_factory_function_anthropic_messages_uses_streaming_fallback_dispatch` | the factory wrapper is callable and dispatches anthropic_messages to the streaming chain |
| [RDISP-003], [RDISP-004] | `tests/unit/test_router/test_router.py::test_sync_vector_store_wrapper_injects_router_embedding_executor`, `::test_sync_vector_store_wrapper_preserves_model_routing`, `::test_vector_store_search_injects_router` | executor and router injection; model routing |
| [RDISP-003] | `tests/unit/test_router/test_router_vector_store_endpoints.py::test_vector_store_list_forwards_pagination_params_to_provider`, `::test_vector_store_update_forwards_expires_after_to_provider` | model-less sync vector store calls go straight to the provider |
| [RDISP-031] | `tests/unit/test_router/test_router_vector_store_endpoints.py::test_avector_store_update_sends_name_and_metadata_to_provider` | model-less async vector store calls are direct |
| [RDISP-044] | `tests/unit/test_router/test_router.py::test_dispatch_generic_call_type_routes_anthropic_messages_through_streaming_fallbacks`, `::test_dispatch_generic_call_type_other_call_types_use_generic_fallback` | shared dispatch split |
| [RDISP-047], [RDISP-048] | `tests/unit/test_router/test_router_helper_utils.py::test_sync_generic_api_call_preserves_requested_model_group_in_logs`, `::test_sync_generic_api_call_uses_request_kwargs_for_deployment_selection` | `litellm_metadata.model_group`, deployment model, request-kwarg selection |
| [RDISP-043] | `tests/unit/test_router/test_router.py` (amoderation with `moderation-model`) | moderation routes to the deployment's model |
| [RDISP-052], [RDISP-055] | `tests/unit/test_router/test_router_fallbacks.py::test_embedding_fallback_routes_after_primary_error` | embeddings fall back across groups in both modes |
| [RDISP-059], [RDISP-069] | `tests/unit/test_router/test_router.py::test_async_router_acreate_file_does_not_fall_back_across_model_groups` | no cross-group file fallback |
| [RDISP-064] | `tests/unit/test_router/test_router.py::test_async_router_acreate_file_forwards_target_model_names_to_litellm_proxy`, `::test_async_router_acreate_file_does_not_inject_target_model_names_for_other_providers` | `target_model_names` for `litellm_proxy` only; no `extra_body` for other providers |
| [RDISP-063] | `tests/unit/test_router/test_router.py::test_async_router_acreate_file_keeps_blank_lines_only_for_vertex`, `::test_async_router_acreate_file_passthrough_keeps_the_file_and_forwards_the_flag` | JSONL rewrite rules |
| [RDISP-070] | `tests/unit/test_router/test_router.py::test_avector_store_create_does_not_inject_router` | no `router` kwarg on create |
| [RDISP-077], [RDISP-069] | `tests/unit/test_router/test_router.py::test_async_router_acancel_batch_does_not_fall_back_across_model_groups` | cancel stays with the owning deployment |
| [RDISP-081] | `tests/unit/test_router/test_router.py::test_arouter_aretrieve_batch`, `::test_arouter_aretrieve_batch_without_model_stamps_model_group`, `::test_arouter_aretrieve_batch_with_model_stamps_requested_model_group` | deployment credentials and model_group stamping |
| [RDISP-170] | `tests/unit/test_router/test_router.py::test_arouter_aretrieve_batch_does_not_consume_deployment_rate_limits`, `::test_sync_deployment_callback_on_success_skips_batch_retrieves` | batch retrieves never feed counters |
| [RDISP-092] | `tests/unit/test_router/test_router.py::test_async_function_with_fallbacks_stamps_zero_attempted_fallbacks`, `::test_async_function_with_fallbacks_stamps_route_bucket_not_litellm_metadata`, `::test_async_function_with_fallbacks_overrides_client_supplied_stamp_values` | in-place stamps in the route bucket only |
| [RDISP-095], [RDISP-118] | `tests/unit/test_router/test_router_fallbacks.py::test_router_attempted_fallbacks_in_response`, `tests/integration/sdk/test_router_cooldown_fallback_sdk.py::test_fallback_response_reports_the_attempted_fallback` | `x-litellm-attempted-fallbacks` 0 and 1 |
| [RDISP-101] | `tests/unit/test_router/test_router.py::test_async_function_with_fallbacks_common_utils`, `tests/unit/test_router/test_router_fallbacks.py::test_disable_fallbacks_stops_after_primary_error` | immediate re-raise |
| [RDISP-104], [RDISP-105] | `tests/unit/test_router_order_fallback.py::test_router_order_fallback_on_failure`, `::test_router_order_fallback_three_levels`, `::test_router_order_fallback_then_external_fallback`, `::test_router_order_fallback_with_non_standard_fallbacks`, `::test_router_order_fallback_retries_keep_target_order` | order levels first, then external; last error raised |
| [RDISP-107] | `tests/unit/test_router/test_router_fallbacks.py::test_client_side_fallbacks_list` | per-request list of names |
| [RDISP-110], [RDISP-237] | `tests/unit/test_router/test_router_fallbacks.py::test_router_content_policy_fallbacks`, `tests/unit/test_router/test_router_helper_utils.py::test_should_raise_content_policy_error` | content-policy chain and default fallbacks |
| [RDISP-109], [RDISP-112], [RDISP-115], [RDISP-272] | `tests/unit/test_router_exception_redaction.py` (all tests) | hint and outcome text gated by the expose flag; credentials masked |
| [RDISP-114] | `tests/unit/test_router/test_router.py::test_fallback_failure_detail_from_upstream_is_bounded`, `::test_fallback_traceback_stays_available_at_debug_level`, `::test_cyclic_fallback_graph_does_not_amplify_one_request` | bounded detail; traceback only at DEBUG |
| [RDISP-118] | `tests/unit/test_router/test_router_fallbacks.py::test_default_and_model_fallbacks_do_not_repeat_failed_models`, `::test_unknown_default_fallback_raises_after_primary_failure`, `::test_default_fallback_serves_after_primary_error` | no repeated targets; default chain |
| [RDISP-119] | `tests/integration/sdk/test_router_include_fallback_errors_wire.py::test_a_non_boolean_flag_stays_off_the_wire_and_the_errors_header_follows_its_truthiness` | truthiness decides the errors header |
| [RDISP-120]-[RDISP-124] | `tests/unit/test_router_weighted_failover.py` (router tests) | simple-shuffle only, exclusions persisted, cooldown-aware, falls through to external |
| [RDISP-131] | `tests/unit/test_router_per_deployment_num_retries.py::TestNumRetriesNoneGuard` | `None` falls back to the router value, then 0 |
| [RDISP-136], [RDISP-138] | `tests/unit/test_router_per_deployment_num_retries.py::TestRequestNumRetriesBeatsGlobal`, `::TestRequestNumRetriesBeatsDeployment` | precedence; explicit 0 disables the policy |
| [RDISP-138] | `tests/unit/test_router/test_router_retries.py::test_dynamic_router_retry_policy`, `::test_authentication_errors_are_not_retried` | policy counts |
| [RDISP-145], [RDISP-147] | `tests/unit/test_router_retry_non_retryable_errors.py` (all tests) | latest error raised; non-retryable breaks the loop |
| [RDISP-147] | `tests/unit/test_router/test_router_retries.py::test_router_retry_num_retries_tracking`, `::test_router_retry_num_retries_single_retry` | `num_retries`/`max_retries` attributes and message |
| [RDISP-146], [RDISP-161] | `tests/unit/test_router_retry_backoff_headers.py::test_retry_backoff_uses_current_exception_headers` | backoff computed 1 + N times from the current error |
| [RDISP-148] | `tests/unit/test_router/test_router.py::test_router_deployment_ids_to_skip_on_retry`, `::test_router_retry_skip_stamp_feeds_deployment_ids_to_skip_on_retry` | skip-list rules |
| [RDISP-149] | `tests/unit/test_router/test_router.py::test_router_healthy_deployments_keep_the_last_candidate_a_retry_skipped`, `::test_router_retry_policy_400_keeps_upstream_error_when_a_client_forges_the_skip_list` | a skip set covering every candidate re-admits all of them; the key is popped; non-tuple values are ignored |
| [RDISP-151], [RDISP-152] | `tests/unit/test_router/test_router_helper_utils.py::test_handle_mock_testing_fallbacks`, `::test_handle_mock_testing_rate_limit_error`, `::test_mock_router_testing_params_str_to_bool_conversion` | mock triggers |
| [RDISP-155], [RDISP-158] | `tests/unit/test_router/test_router_retries.py::test_retry_rate_limit_error_with_healthy_deployments`, `::test_no_retry_for_bad_request_error_400`, `::test_no_retry_for_unprocessable_entity_error_422`, `::test_no_retry_for_not_found_error_404`, `::test_no_retry_when_no_healthy_deployments`, `tests/unit/test_router/test_router.py::test_permission_denied_error_is_not_retried_against_a_single_deployment` | eligibility order |
| [RDISP-160] | `tests/unit/test_router/test_router_retries.py::test_timeout_for_rate_limit_error_with_healthy_deployments`, `::test_timeout_for_rate_limit_error_with_no_healthy_deployments` | 0 versus computed backoff |
| [RDISP-172], [RDISP-173] | `tests/unit/test_router/test_router_helper_utils.py::test_deployment_callback_on_success`, `::test_deployment_callback_on_success_adds_only_uncounted_tokens`, `::test_deployment_callback_on_success_tracks_tpm_for_io_deployment` | TPM key and delta counting |
| [RDISP-177]-[RDISP-183] | `tests/unit/test_router/test_router_helper_utils.py::test_increment_deployment_usage_for_response_skips_session_wrappers`, `::test_increment_deployment_usage_writes_only_positive_deltas_for_limited_deployments` | no-op rules |
| [RDISP-191] | `tests/unit/test_router/test_router_helper_utils.py::test_deployment_callback_respects_cooldown_time` | deployment `cooldown_time` 0 wins |
| [RDISP-193] | `tests/integration/sdk/test_router_cooldown_fallback_sdk.py::test_cooldown_skips_only_the_failed_duplicate_model_deployment` | a failing deployment is cooled down and skipped next time |
| [RDISP-200]-[RDISP-205] | `tests/unit/test_router/test_router_helper_utils.py::test_log_retry`, `tests/unit/test_router/test_router.py::test_retry_records_keep_only_the_last_four_attempts`, `::test_num_retries_per_request_counts_retries_across_fallback_hops`, `::test_retry_records_never_carry_a_forwarded_credential` | flat records, cap of 4, request-wide count |
| [RDISP-207] | `tests/unit/test_router/test_router_helper_utils.py::test_get_metadata_variable_name_from_kwargs` | bucket choice |
| [RDISP-208] | `tests/unit/test_router/test_router_helper_utils.py::test_update_usage` | counter 1 then 2 |
| [RDISP-216], [RDISP-217] | `tests/unit/test_router/test_router_helper_utils.py::test_routing_strategy_pre_call_checks` | re-raise behaviour |
| [RDISP-218] | `tests/unit/test_router/test_router.py::test_router_deployment_slot_rejects_while_held_and_frees_slot_on_exit` | slot overflow 429 |
| [RDISP-219] | `tests/unit/test_router/test_router_helper_utils.py::test_async_callback_filter_deployments` | pass-through with no filters |
| [RDISP-220]-[RDISP-224] | `tests/unit/test_router/test_router_helper_utils.py::test_responses_websocket_turn_is_refused_once_its_deployment_crosses_budget`, `::test_responses_websocket_turn_is_checked_against_limits_changed_after_the_socket_opened`, `::test_responses_websocket_turns_do_not_reserve_deployment_otpm` | turn admission |
| [RDISP-230], [RDISP-231] | `tests/unit/test_router/test_router_helper_utils.py::test_has_default_fallbacks`, `::test_get_first_default_fallback` | default-fallback helpers |
| [RDISP-234] | `tests/unit/test_router/test_router.py::test_refusal_on_the_last_fallback_hop_is_returned_instead_of_raised` | attempted targets exhaust availability |
| [RDISP-236] | `tests/unit/test_router/test_router.py::test_anthropic_messages_stream_can_fall_back_direct_call`, `::test_anthropic_messages_stream_can_fall_back_order_levels`, `::test_anthropic_messages_stream_can_fall_back_order_target` | predicate order |
| [RDISP-240] | `tests/unit/test_router/test_router.py::test_consistent_model_id` | deterministic id |
| [RDISP-243] | `tests/unit/router_strategy/test_router_routing_plugins.py::test_json_default_stable_id_is_stable_across_instances`, `::testgenerate_model_id_is_stable_when_litellm_params_contain_a_plugin_instance` | class-name rendering of nested objects |
| [RDISP-269] | `tests/unit/test_router/test_router_fallbacks.py::test_async_fallbacks` | the three INFO lines of a successful fallback, in order |
| [RDISP-165] | `tests/unit/test_router/test_router_helper_utils.py::test_router_function_with_fallbacks`, `tests/integration/sdk/test_router_include_fallback_errors_wire.py::test_sync_matches_the_async_twin` | sync wrapper parity |

## Suspected defects
Behavior that looks unintended. The normative sections above state what the code does; each claim here says why it looks wrong and who is affected.

- [RDISP-296] {confirmed} `litellm/router.py:2291-2293`, `litellm/router.py:2507-2516`, `litellm/router.py:2543-2545`, `litellm/router.py:2566-2572`, `litellm/router.py:7763-7808`, `litellm/router.py:7865-7890` Thirteen factory-bound names match no dispatch branch: `aadapter_generate_content`, the sync-named `video_create_character`, `video_get_character`, `video_edit`, `video_extension`, `get_interaction`, `delete_interaction`, `cancel_interaction` and the five sync container-file names return `None`, or a coroutine that resolves to `None`, without calling their SDK function ([RDISP-023]-[RDISP-026]). Looks unintended because each name is bound to a real SDK function that is never reached, and the sync-named ones hand a coroutine back from a sync API ([RDISP-290]). Impact: callers get `None` (or an un-awaited coroutine) instead of a result or an error, so the failure is silent; the same names are listed in [RSETUP-120], [RSETUP-125] and [IF-361].
- [RDISP-297] {confirmed} `litellm/router.py:8748-8761` After the final failed retry the loop still sleeps one backoff interval before raising ([RDISP-146]). Looks unintended because no attempt follows that sleep ([RDISP-295]). Impact: every request that exhausts its retries waits one more backoff interval before fallbacks start or the error reaches the caller.
- [RDISP-298] {inferred} `litellm/router.py:8255-8259`, `litellm/router_utils/fallback_event_handlers.py:884-900` When an order-level fallback walk fails, the caller sees the walk's last error without the outcome suffix ([RDISP-105]). Looks unintended because every other dispatcher path raises the original error with that suffix ([RDISP-115], [RDISP-294]). Impact: callers of groups with `order` levels get a different error object and message than callers of other groups, and the original failure is hidden.
- [RDISP-299] {inferred} `litellm/router.py:6989-6997` A multi-deployment `acreate_file` raises on the first failed upload while the other uploads keep running unobserved ([RDISP-281]). Looks unintended because files created on the other deployments are neither returned nor cleaned up ([RDISP-291]). Impact: orphaned provider files that no id mapping refers to.
- [RDISP-300] {confirmed} `litellm/router.py:9518-9536` The sync `_get_healthy_deployments` returns a bare `[]` when a specific deployment resolves and a `(healthy, all)` tuple otherwise ([RDISP-212]). Looks unintended because the async twin always returns a tuple ([RDISP-210]) and a tuple-unpacking caller cannot handle `[]` ([RDISP-293]). Impact: a sync caller that unpacks the result raises `ValueError` for deployment-id requests.
- [RDISP-301] {confirmed} `litellm/router.py:8191-8201`, `litellm/router.py:8224-8228` Request kwargs `max_fallbacks`, `fallback_depth` and `_target_order` are trusted as given ([RDISP-258]). Looks unintended because they are internal bookkeeping of the fallback walk ([FAILURE-149]), not documented request settings. Impact: a caller whose kwargs reach the router unfiltered can raise its own fallback cap or start the order walk at a chosen level.
- [RDISP-302] {confirmed} `litellm/router.py:8535-8548` The context-window and content-policy mock messages contain 21 spaces before their list, and the content-policy one labels its list `Context_Policy_Fallbacks=` ([RDISP-151]). Looks unintended because the spaces come from a backslash line continuation inside an f-string, and the label names the wrong setting (`content_policy_fallbacks`). The `InternalServerError` sibling has neither quirk. Impact: tests or log filters that match these messages must reproduce the whitespace and the misspelled label.
- [RDISP-303] {confirmed} `litellm/router.py:6960-6966`, `litellm/router.py:6974-6982` For a deployment whose resolved provider is `litellm_proxy`, `acreate_file` discards the deployment's own `litellm_params.extra_body` ([RDISP-064]). Looks unintended because the injection is written as a merge that preserves an existing `extra_body`, yet it reads only the request's `extra_body`, and the request side then overrides the deployment's value wholesale. Other providers keep a deployment `extra_body` when the caller sends none. Impact: operators who configure `extra_body` on a `litellm_proxy` deployment lose it on file uploads, and the upstream proxy receives only `target_model_names`.
