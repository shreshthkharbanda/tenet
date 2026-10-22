---
module: router-dispatch
---
# A failed request retries in its model group, then tries any listed backup groups

@plain
Apps send AI requests through the router by naming a model group [RDISP-092]. Several provider setups, called deployments, can serve one model group [RDISP-058]. When a request fails with an error worth retrying and retries are allowed, this part tries the same group again, sometimes after a short wait [RDISP-141][RDISP-143][RDISP-155][RDISP-160]. If that does not work, it can send the request to a backup group that the operator listed [RDISP-096][RDISP-111][RDISP-113]. It also counts successes and failures per deployment, and it can bench a failing deployment for a few seconds [RDISP-172][RDISP-191][RDISP-193]. When this part goes wrong, customers wait through extra pauses, get errors a backup could have served, or get nothing back from some features [RDISP-297][RDISP-108][RDISP-296].

@minute
An async routed call usually enters the fallback entry, `async_function_with_fallbacks`, which runs the retry loop and hands any final error to the fallback dispatcher [RDISP-092][RDISP-096]. The loop retries the same model group up to the retry count, while the eligibility check or a retry policy allows it [RDISP-131][RDISP-138][RDISP-155]. For most errors, a group with two or more order levels walks its higher levels and then its fallback chain, returning that walk's result or last error [RDISP-104][RDISP-105]. Otherwise the dispatcher tries weighted failover if enabled and the group uses simple-shuffle, except on too-long prompts and blocked content [RDISP-106][RDISP-120]. Then it walks one fallback chain, raising the original error when nothing answers [RDISP-111][RDISP-115]. Callbacks count usage and ask for cooldowns, and `factory_function` builds most non-chat endpoints [RDISP-172][RDISP-193][SYS-004].

## Words you'll see
| Term | Means | In the code | Claims |
| --- | --- | --- | --- |
| model group | the model name a request asks for; one group can hold several deployments | `model`, `model_group` | RDISP-042, RDISP-058, RDISP-092 |
| deployment | one configured provider setup inside a model group, with its own settings and id | `litellm_params`, `model_info.id` | RDISP-054, RDISP-240 |
| backup group | another model group the operator lists to try when this one fails | `fallbacks` | RDISP-093, RDISP-111 |
| cooldown | a short pause during which the router sends a deployment no traffic, also called benching; its length is the cooldown time | `cooldown_time` | RDISP-191, RDISP-193 |
| fallback entry | the outer step that runs the retry loop and passes a final error to the dispatcher; on a top-level call it first resets the fallback stamps | `async_function_with_fallbacks` | RDISP-092, RDISP-096 |
| retry loop | the part that calls the same model group again after a failure | `async_function_with_retries` | RDISP-130, RDISP-143 |
| retry count | how many extra attempts the loop may make after the first one | `num_retries`, `max_retries` | RDISP-131, RDISP-136, RDISP-147 |
| retry policy | an operator's table of retry counts per error type; when it gives a count, that count replaces the retry count and the eligibility check | `retry_policy`, `model_group_retry_policy` | RDISP-138 |
| eligibility check | the ordered tests that decide whether an error deserves another attempt | `should_retry_this_error` | RDISP-155 |
| fallback dispatcher | the part that takes the final error and decides where else to send the request | `async_function_with_fallbacks_common_utils` | RDISP-100, RDISP-101 |
| fallback chain | the ordered list of backup groups tried for a group; a catch-all entry covers groups without their own | `fallbacks`, `context_window_fallbacks`, `content_policy_fallbacks` | RDISP-093, RDISP-111 |
| order level | a priority tier among one group's deployments | `order`, `_target_order` | RDISP-103, RDISP-104 |
| weighted failover | an opt-in extra try on the same group's other deployments, for weighted shuffle routing only | `enable_weighted_failover` | RDISP-106, RDISP-120 |
| endpoint factory | the builder that wraps a library function as a router endpoint; the endpoint's call type, the kind of operation, decides how it runs and routes | `factory_function`, `call_type` | RDISP-001, SYS-004 |
| provider and client arguments | an optional provider name and a ready-made connection that a caller can pass | `custom_llm_provider`, `client` | RDISP-002 |
| guardrail block | an error a safety check raises on purpose; the router passes it to the caller with no retry or backup | `is_guardrail_intervention` | RDISP-101, RDISP-135 |
| too-long prompts | errors saying the request does not fit the model's context window | `ContextWindowExceededError` | RDISP-108, RDISP-155 |
| blocked content | errors saying the provider refused the request under its content policy | `ContentPolicyViolationError` | RDISP-110, RDISP-155 |
| backoff | the wait before the next attempt, shaped by a header, a floor, a cap and random jitter | `_time_to_sleep_before_retry`, `retry_after`, `retry-after` | RDISP-160, RDISP-161, RDISP-162 |
| skip list | deployments that refused this request with a non-retryable status, avoided on later retries | `_retry_skipped_deployment_ids` | RDISP-148, RDISP-149 |
| unsupported-parameter switch | whether unsupported-parameter errors and provider 400 errors other than too-long prompts and blocked content may fall back | `fallback_on_unsupported_params` | RDISP-101 |
| lookup groups | the group names the dispatcher looks up in the backup lists: a pre-picked tier, the routed group, the requested group, then the original group | `lookup_groups` | RDISP-112, RDISP-117 |
| attempt headers | response headers that report how many retries and fallback hops a reply took | `x-litellm-attempted-retries`, `x-litellm-max-retries`, `x-litellm-attempted-fallbacks` | RDISP-095, RDISP-134, RDISP-143 |
| outcome text | the explanation of what fallback did that the dispatcher appends to the final error's message, while debug exposure is on and outside a nested hop | `expose_router_debug_in_errors` | RDISP-115, RDISP-272 |
| success callback | the logging step after each successful provider call that counts the deployment's successes and usage | `deployment_callback_on_success`, `<id>:successes` | RDISP-172, RDISP-173 |
| failure callback | the logging step after each failed provider call that counts the failure and asks whether to cool the deployment down | `deployment_callback_on_failure`, `<id>:fails` | RDISP-190, RDISP-193 |
| deployment id | a deployment's stable id; when none is configured, the router hashes one from the group name and the settings | `generate_model_id` | RDEPLOY-007, RDISP-240 |
| file and batch entries | hand-written endpoints for uploads and batch jobs that skip the factory | `acreate_file`, `acreate_batch`, `acancel_batch`, `aretrieve_batch`, `alist_batches` | RDISP-057, RDISP-074, RDISP-076, RDISP-079, RDISP-085 |

## At a glance
| When | Then | Claims |
| --- | --- | --- |
| A call succeeds on its first attempt | `x-litellm-attempted-retries` and `x-litellm-attempted-fallbacks` are 0 | RDISP-134, RDISP-095 |
| No retry policy applies, the status is 408, 409, 429 or 500 and above, and a healthy deployment and a retry remain | The loop retries, at once unless the group has exactly one deployment | RDISP-155, RDISP-156, RDISP-160 |
| The error is 400, 404 or 422 and no retry policy applies | No retry; the dispatcher runs next | RDISP-155, RDISP-156, RDISP-096 |
| A retry policy has a count for the error and the request did not set `num_retries` to 0 | That count becomes the retry count and bypasses the eligibility check, so even a 400 retries | RDISP-138 |
| `fallbacks` is unset, no order walk ran, weighted failover returned no reply, and no dedicated list applies | The original error, with outcome text saying no fallback was attempted when exposure is on | RDISP-104, RDISP-105, RDISP-115, RDISP-116 |
| `fallbacks` is set but has no entry for any of the lookup groups and no catch-all | The original error; with exposure on, outside a nested hop, for an error with a message, a note that no backup group was found replaces the outcome text | RDISP-111, RDISP-112 |
| A failure callback sees a deployment id and no skip case | It adds 1 to `<id>:fails` and asks for a cooldown, 5 s by default | RDISP-190, RDISP-191, RDISP-193 |

## The endpoint factory picks how each endpoint routes from its call type
Most endpoints other than chat come from a builder when the router starts [SYS-004][RDISP-001]. Depending on the endpoint's call type, a call then retries and falls back like chat, makes one call to one deployment, or skips the router and calls the provider directly [RDISP-044][RDISP-051][RDISP-043][RDISP-005][RDISP-040]. Some names match no route and hand the caller an empty result with no error [RDISP-296].

Synchronous wrappers cover the main list, such as "responses" and "ocr", plus vector-store, vector-store-file and managed-agent calls [RDISP-002][RDISP-003][RDISP-005][RDISP-006]. The main one makes one call to one deployment, with no retries, fallbacks or alert, and silently drops a caller's `custom_llm_provider` and `client` [RDISP-002][RDISP-048][RDISP-051].

Every other call type gets an asynchronous wrapper that runs its first matching branch, and most branches end in the generic async fallback chain [RDISP-007][RDISP-030][RDISP-044]. Some families skip routing instead [RDISP-031][RDISP-040]:
- vector-store and interactions calls without a model, and container calls with neither a model nor a routable container id, call the provider directly [RDISP-003][RDISP-031][RDISP-035][RDISP-039];
- synchronous vector-store-file calls, managed agents and assistants always call the provider directly [RDISP-005][RDISP-006][RDISP-040][RDISP-041].

Of the bound names that match no branch, the synchronous-looking ones hand back an un-awaited coroutine [RDISP-007][RDISP-296][RDISP-024].

## The retry loop retries the same group while the error qualifies
After a failed attempt, the router decides whether to try the same group again and how often [RDISP-131][RDISP-155]. An operator's retry policy can set that count per error type; otherwise a few checks rule out errors another try will not fix [RDISP-138][RDISP-155].

The retry count comes from the request's `num_retries`, then the failing deployment, then the router, then 0 [RDISP-131][RDISP-136].

After the first failure, the loop consults a retry policy when one exists and the request did not set `num_retries` to 0 [RDISP-138]. Its count replaces the retry count and turns off the eligibility check for the whole request [RDISP-138]. Without such a count, the eligibility check re-raises the error at the first test that holds [RDISP-155]:
- a context-window or content-policy error while that error's own fallback list is set [RDISP-155];
- a non-retryable status other than 401 and 403, where only 408, 409, 429 and 500 or above are retryable [RDISP-155][RDISP-156];
- a not-found error [RDISP-155];
- a rate-limit error with no healthy deployment left while generic fallbacks exist [RDISP-155];
- a 401 or 403 in a group with at most 1 deployment [RDISP-155][RDISP-158];
- no healthy deployment left at all [RDISP-155].

A count of 0 re-raises the first error unchanged [RDISP-141]. A request that names one specific deployment, such as by its id, sees no healthy deployments here, so without a policy it never retries [RDISP-214].

@figure flow id=retry-loop title="How the retry loop decides to try again or hand over"
| node first | First attempt | RDISP-134 |
| node policy | Retry policy applies? | RDISP-138 |
| node gate | Error worth retrying? | RDISP-155 |
| node left | Retries left? | RDISP-141, RDISP-143 |
| node wait | Wait the backoff | RDISP-142, RDISP-146 |
| node retry | Try the group again | RDISP-143 |
| node done | Return the reply | RDISP-134, RDISP-143 |
| node dispatch | Hand error to dispatcher | RDISP-096, RDISP-147 |
| first > done | succeeds | RDISP-134 |
| first > policy | fails | RDISP-138 |
| policy > left | yes, use its count | RDISP-138 |
| policy > gate | no | RDISP-140 |
| gate > dispatch | no | RDISP-140, RDISP-155 |
| gate > left | yes | RDISP-155 |
| left > wait | some left | RDISP-142 |
| left > dispatch | none left | RDISP-141, RDISP-147 |
| wait > retry | wait ends | RDISP-143 |
| retry > done | succeeds | RDISP-143 |
| retry > gate | fails, no policy | RDISP-145 |
| retry > left | fails, policy applies | RDISP-144, RDISP-145 |

@steps retry-loop
| first | First attempt | The loop calls the group once, and a success returns with zero retries recorded; a guardrail block skips retries entirely [RDISP-134][RDISP-135]. |
| policy | A policy can override | A configured policy count replaces the retry count and skips the check, unless the request set its own retry count to zero [RDISP-138]. |
| gate | The eligibility check | Without a policy, retries stop on a status not worth retrying, a not-found error, a too-long prompt or blocked content with its own backup list, or no healthy deployment left [RDISP-155]. A sign-in or permission refusal stops them only in a group with one deployment [RDISP-158]. |
| wait | The wait | The wait is zero when the group has several deployments and a healthy one remains [RDISP-160]. |
| left>dispatch | Out of retries | The loop raises the latest error, and the fallback dispatcher takes over [RDISP-147][RDISP-096]. |

## Each retry waits a backoff and skips deployments that refused
Between tries the router waits only when the group has a single deployment or no healthy one left [RDISP-160]. That pause grows with each try, unless the provider says how long to wait [RDISP-162]. Later tries also avoid deployments that rejected the request outright [RDISP-148][RDISP-149].

When the backoff is not 0 s, a `retry-after` value of 1 to 60 whole seconds wins [RDISP-160][RDISP-162]. Failing that, the delay starts at 0.5 s by default, doubles per retry used, rises to the router's `retry_after` floor, and caps at 8.0 s [RDISP-161][RDISP-162]. Either way it adds random jitter, below 0.75 s by default [RDISP-162].

When the loop runs to the end, it also sleeps after the final failed retry, then raises the latest error, not the first [RDISP-146][RDISP-147][RDISP-297].

A non-retryable status, such as 400, 401, 403 or 404, puts the failed deployment on the skip list [RDISP-148]. Later retries avoid it unless that would leave no candidate, in which case the whole candidate list returns [RDISP-149].

In the example, group a's one deployment always answers 500, a server error, the router sets 3 retries, and a falls back to b, without jitter [RDISP-131][RDISP-162][RDISP-113]. With default settings that lone deployment does not cool down after a few failures [FAILURE-044].

@figure timeline id=lone-retry title="Example: a lone deployment fails four times, then group b answers"
| lane a | Group a's one deployment |
| lane b | Backup group b |
| lane caller | The caller |
| 0s | a | first call: server error 500 | waits 0.5 s | RDISP-156, RDISP-142, RDISP-162 |
| 0.5s | a | retry 1: server error 500 | waits 1.0 s | RDISP-143, RDISP-146, RDISP-162 |
| 1.5s | a | retry 2: server error 500 | waits 2 s | RDISP-146, RDISP-162 |
| 3.5s | a | retry 3: server error 500 | waits 4.0 s anyway | RDISP-146, RDISP-162, RDISP-297 |
| 7.5s | b | dispatcher sends the request here | serves the reply | RDISP-111, RDISP-113 |
| 7.5s | caller | gets group b's reply | one fallback hop recorded | RDISP-118 |

## The fallback dispatcher tries order levels, failover, then one chain
When the retry loop gives up, the dispatcher looks for somewhere else to send the request [RDISP-096]. For most errors, a group with two or more priority tiers walks its higher tiers, then its backup list, and stops there [RDISP-104][RDISP-105]. Otherwise one backup list follows an opt-in extra try on the group's other deployments, which too-long prompts and blocked content skip [RDISP-106][RDISP-111].

The dispatcher re-raises unchanged when fallbacks are disabled, no model group is named, or a guardrail intervened [RDISP-101]. With `fallback_on_unsupported_params` off, an unsupported-parameter error or a provider 400 that is not context-window or content-policy also stops here [RDISP-101].

The order walk needs two or more distinct `order` values and an error that is not context-window or content-policy [RDISP-103][RDISP-104]. A failed walk raises its last error, with no outcome text [RDISP-105].

Weighted failover runs next, only when `enable_weighted_failover` is on, the group uses simple-shuffle, no order walk returned, and the error names the failed deployment and is not context-window or content-policy [RDISP-106][RDISP-120]. It retries the group without the failed and cooled-down deployments; provider errors and router rate-limit errors from it fall through to the chains, other errors reach the caller [RDISP-122][RDISP-124].

Then the dispatcher picks one chain [RDISP-107][RDISP-108][RDISP-111]:
- it walks a non-standard `fallbacks` value, such as a list of model names, as given [RDISP-107];
- a context-window or content-policy error whose own list is set uses that list alone, and a miss raises the original error [RDISP-108][RDISP-110];
- with that list unset, the error goes on to the generic chain [RDISP-109];
- the generic chain is the specific entry of the first of the lookup groups that has one, else the `"*"` catch-all entry [RDISP-111][RDISP-117].

A walk tries targets one at a time, skips those already tried, stops at the depth limit, and marks a successful hop's reply with `x-litellm-attempted-fallbacks` set to its depth [RDISP-118]. When `fallbacks` is set but no chain resolves, the dispatcher raises the original error with, when exposure is on, a note that no backup group was found [RDISP-112]. Otherwise it raises the original error, never a fallback's, with outcome text when exposure is on [RDISP-115][RDISP-272].

@figure flow id=dispatcher title="How the dispatcher chooses where a failed request goes next"
| node err | Final error arrives | RDISP-096 |
| node stop | Stop at once? | RDISP-101 |
| node order | Several order levels? | RDISP-103, RDISP-104 |
| node owalk | Walk higher levels first | RDISP-104 |
| node wf | Weighted failover answers? | RDISP-106, RDISP-120 |
| node ded | Dedicated list for error? | RDISP-108, RDISP-110 |
| node gen | Generic chain found? | RDISP-111, RDISP-112 |
| node walk | Walk the chain | RDISP-113, RDISP-118 |
| node reply | Return the backup reply | RDISP-113, RDISP-118 |
| node orig | Raise the original error | RDISP-115 |
| node last | Raise the last error | RDISP-105 |
| err > stop | checks first | RDISP-101 |
| stop > orig | yes | RDISP-101 |
| stop > order | no | RDISP-103 |
| order > owalk | yes | RDISP-104 |
| owalk > reply | a target answers | RDISP-104 |
| owalk > last | every target fails | RDISP-105 |
| order > wf | no | RDISP-106 |
| wf > reply | yes | RDISP-106, RDISP-123 |
| wf > ded | no | RDISP-122, RDISP-124 |
| ded > walk | yes, chain found | RDISP-108, RDISP-110 |
| ded > orig | yes, no chain | RDISP-108, RDISP-110 |
| ded > gen | no | RDISP-109, RDISP-111 |
| gen > walk | yes | RDISP-111, RDISP-113 |
| gen > orig | no | RDISP-112, RDISP-116 |
| walk > reply | a target answers | RDISP-113 |
| walk > orig | every target fails | RDISP-114, RDISP-115 |

@steps dispatcher
| stop | Immediate stop | Disabled fallbacks, a missing group name, a guardrail block, or a bad request the operator does not let fall back ends the request here [RDISP-101]. |
| order | Order levels | This path runs only for groups with two or more priority tiers, and not for too-long prompts or blocked content [RDISP-104]. |
| wf | Weighted failover | This path runs only when the operator turned it on and the group shuffles by weight [RDISP-106][RDISP-120]. |
| ded | Dedicated lists | Too-long prompts and blocked content use their own backup lists alone when set, never the general list; otherwise they use the general list [RDISP-108][RDISP-110][RDISP-109]. |
| gen | General list | An entry for the group itself wins over the catch-all entry [RDISP-111]. |
| walk>orig | Every backup fails | The caller gets the original error, not a backup's, with a note on what was tried when the operator allows it [RDISP-115][RDISP-272]. |

## Logging callbacks count each outcome and can start a cooldown
After each provider call, the router's logging callbacks update its counters, except for calls without router bookkeeping [RDISP-196]. A success adds to the deployment's counts, and a failure can bench the deployment for a few seconds [RDISP-172][RDISP-191][RDISP-193].

For a counted success, `deployment_callback_on_success` adds 1 to the in-memory `<id>:successes` key for 60 s [RDISP-171][RDISP-172]. It adds per-minute token and request usage only for deployments with limits, minus what the loop already counted at response time [RDISP-173][RDISP-178][RDISP-181]. It swallows its own errors and skips realtime sessions and batch retrieves [RDISP-170][RDISP-174].

On failure, `deployment_callback_on_failure` skips advisor-orchestration errors, provider 404s from background-response polls, 408s from a caller-set timeout and caller-scoped authentication failures [RDISP-190]. Otherwise it takes a `cooldown_time` from the deployment, then the error's `retry-after`, then the router, 5 s by default [RDISP-191]. With a deployment id, it adds 1 to `<id>:fails`, asks the cooldown handler whether to bench the deployment, and re-raises its own errors [RDISP-193][RDISP-195].

Without a configured id, `generate_model_id` hashes the group name and each setting's key and value in insertion order with SHA-256, so reordering settings changes the id [RDEPLOY-007][RDISP-240][RDISP-241].

## Files, batches and embeddings take their own hand-written paths
Embeddings, file uploads and batch jobs have their own entry points [RDISP-052][RDISP-057][RDISP-074]. An upload goes to every healthy deployment at once; a batch lookup asks many at once and returns the first match [RDISP-059][RDISP-080][RDISP-083].

Embeddings run through the same fallback entry [RDISP-052][RDISP-055].

`acreate_file` returns the first upload's response with a map from deployment id to file id [RDISP-058][RDISP-067]. It never falls back to another group, and a retry re-uploads everywhere [RDISP-069][RDISP-286]. If one upload fails, that error surfaces while the others keep running [RDISP-281].

`acreate_batch` and `acancel_batch` each select one deployment and run through the fallback entry, so a retried create can make a second batch [RDISP-074][RDISP-075][RDISP-076][RDISP-077][RDISP-286]. `aretrieve_batch` asks every healthy deployment, or every router deployment without a model, and returns the first batch found, without retries [RDISP-079][RDISP-080][RDISP-083][RDISP-084].

## Watch out
- Several endpoint names, including some video, interaction and container-file calls, return nothing without calling the provider, so the caller gets an empty result and no error [RDISP-296].
- A request that runs out of retries still waits one more pause before any backup starts, delaying its reply or error [RDISP-297].
- A request that asks for zero retries gets none, even when a retry policy would retry its error; a router-wide zero does not override a policy [RDISP-138].
- A retry policy that covers bad requests (status 400) retries them, though the eligibility check would normally stop them [RDISP-138]. Every retry re-sends the whole job, so a retried batch creation can make a second batch [RDISP-286].
- A dedicated backup list for too-long prompts or blocked content overrides the general list: with no matching entry, not even a catch-all, the request fails at once [RDISP-108][RDISP-110][RDISP-117].
- When an order-level walk fails, the caller gets that walk's last error instead of the original, with no explanation [RDISP-105][RDISP-298].
- A file upload to several deployments that fails part-way can leave files behind that the reply's file map does not list and nothing removes [RDISP-299].
- A caller who can pass internal settings can raise its own backup limit [RDISP-301].
