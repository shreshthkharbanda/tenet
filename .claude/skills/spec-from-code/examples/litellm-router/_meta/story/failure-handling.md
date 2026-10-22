---
module: failure-handling
---
# The router can bench a failing deployment for seconds and send requests elsewhere

@plain
Behind one model name, the router can hold several copies of the model, called deployments [FAILURE-034], [RSELECT-044]. This part decides what happens after a call to one deployment fails [FAILURE-021]. The router may bench that deployment for a few seconds, a pause called a cooldown, so new requests go to its other deployments [RDISP-191], [RSELECT-044]. When the servers share a store, the others usually see the pause within about a second [FAILURE-009]. The router may then retry, and after that try backup models from a list, skipping any entry it already tried [FAILURE-103], [FAILURE-145]. If every deployment is paused and no backup model answers, the caller gets a "try again" error [FAILURE-179], [RDISP-115]. A pause shorter than one second stays on one server, so the others keep sending it traffic [FAILURE-006].

@minute
After most failed calls, the router's failure callback counts the failure and asks `set_cooldown_deployments` whether to bench the deployment [RDISP-190], [RDISP-193], [FAILURE-021]. Nine ordered checks and a lone-deployment 402 rule can stop the bench; otherwise the deployment's own allowance, the failure-rate rules or the allowed-fails counter decides [FAILURE-022]-[FAILURE-030], [FAILURE-035], [FAILURE-036], [FAILURE-042], [FAILURE-046]. A cooldown is one timed entry; with Redis and a length of at least 1 second, other servers usually see it within about 1 second [FAILURE-006], [FAILURE-009]. A retry policy sets same-group retries per error type, unless the request sets its retry count to 0 [FAILURE-103], [RDISP-138]. The fallback walk then tries the backup list in order, skipping entries already tried, until one succeeds [FAILURE-145], [FAILURE-150].

## Words you'll see
| Term | Means | In the code | Claims |
| --- | --- | --- | --- |
| deployment | one configured copy of a model: an entry in the router's model list with a model name, its settings and an id | `model_info.id` | RDEPLOY-001, RDEPLOY-007, RDEPLOY-186 |
| model group | all the deployments that share one public model name, such as gpt-4o | `model_group` | FAILURE-034, FAILURE-120 |
| cooldown | a timed bench: while it lasts, selection leaves the deployment out | `deployment:<id>:cooldown`, `CooldownCache` | FAILURE-001, FAILURE-011, RSELECT-044 |
| selection | the step that picks one deployment for each request and leaves out benched ones | `get_available_deployment` | RSELECT-044, RSELECT-054 |
| backup model | another model group that the fallback list names for the failed model group | `fallbacks` | FAILURE-114 |
| cooldown decision | the step that runs the nine checks and the deciding rule, and writes the cooldown | `set_cooldown_deployments` | FAILURE-021, FAILURE-052 |
| caller's own credential | a key or session that belongs to one caller rather than to the shared deployment, such as a stored key that was rejected or rate-limited | `CallerCredentialAuthenticationError`, `CallerCredentialRateLimitError` | FAILURE-023, FAILURE-025 |
| provider-default deployment | a deployment the router lists as a provider's default; the checks never let it be benched | `provider_default_deployment_ids` | FAILURE-030 |
| cooldown time | how long a bench lasts: the deployment's own setting, else the error's retry-after header, else the router's, 5 seconds by default | `cooldown_time`, `DEFAULT_COOLDOWN_TIME_SECONDS` | FAILURE-048, RDISP-191 |
| retryable status | 408, 409, 429 or any status of 500 and above; every other status counts as not retryable | `litellm.should_retry` | FAILURE-044 |
| lone deployment | the only deployment of its model group, when the router has no other deployment it may use instead for that request | `routing_group_has_alternatives`, `team_model_has_alternatives` | FAILURE-034 |
| per-minute counts | each server's own success and failure counts for a deployment, normally over a 60-second window from the first count | `<id>:successes`, `<id>:fails` | FAILURE-072, FAILURE-073 |
| allowance | how many failures a deployment may have before a bench | `allowed_fails` | FAILURE-047, FAILURE-049 |
| allowed-fails policy | failure allowances per error type, set on a deployment or on the router; not the retry policy | `allowed_fails_policy` | FAILURE-035, FAILURE-038 |
| allowed-fails counter | a per-deployment failure count, shared through Redis when present, that normally resets a fixed time after the first failure, 5 seconds by default; retry-after headers never set that time | `deployment:<id>:allowed_fails` | FAILURE-048, FAILURE-049, FAILURE-051 |
| connection-error text | the text "APIConnectionError", the name of the connection error type; an error message containing it stops the bench at the status check | `APIConnectionError` | FAILURE-031, FAILURE-209 |
| read interval | how often, at most, a server asks Redis about a bench it does not hold in its own memory; 1 second by default | `redis_read_interval_seconds` | FAILURE-009 |
| Prometheus metrics | numbers a monitoring system reads; each bench marks the deployment as out and adds one to its cooled-down count, when Prometheus is set up | `set_deployment_complete_outage`, `increment_deployment_cooled_down` | FAILURE-056 |
| Slack alert | a chat message about a failed call, sent only when Slack alerting is set up and the request did not come through the proxy | `slack_alerting_logger` | FAILURE-175, FAILURE-176 |
| health mark | a health check's verdict on a deployment; separate from a bench, it counts only when health-check routing is on | `DeploymentHealthCache` | FAILURE-078, RSELECT-142 |
| retry count | how many same-group retries a request gets; a retry skips a deployment that failed with a status that is not retryable, such as 400 or 404, if another remains | `num_retries` | RDISP-131, RDISP-148, RDISP-149 |
| retry policy | retry counts per error type, router-wide or per model group | `retry_policy`, `model_group_retry_policy` | FAILURE-099 |
| fallback walk | the router's pass through the backup list, one entry at a time | `run_async_fallback` | FAILURE-138, FAILURE-194 |
| nested walk | a fallback walk that a backup model's own call starts, because each backup call goes through the router again with its own retries | `async_function_with_fallbacks` | FAILURE-120, FAILURE-149 |
| fallback depth | how many backup attempts deep a walk is; the maximum is checked only when a walk starts | `fallback_depth`, `max_fallbacks` | FAILURE-138, FAILURE-147 |
| attempted set | the entries already tried for this request, shared by every nested walk; an entry with extra settings counts apart from the bare model name | `attempted_targets` | FAILURE-109, FAILURE-111, FAILURE-199 |
| access and budget checks | two optional checks whoever builds the router can add, such as the proxy's check that a key may call a backup model | `fallback_access_check`, `fallback_budget_check` | FAILURE-143, FAILURE-144, FAILURE-219 |
| fallback headers | response headers that report retries and fallbacks: x-litellm-attempted-retries, x-litellm-attempted-fallbacks and x-litellm-fallback-errors | `x-litellm-attempted-retries`, `x-litellm-attempted-fallbacks`, `x-litellm-fallback-errors` | FAILURE-156, FAILURE-157, FAILURE-158 |
| error-list opt-in | a request setting that adds the fallback-errors header when a backup model answers | `include_fallback_errors` | FAILURE-150 |
| no-deployment error | the 429 error selection raises when no deployment is left to pick | `RouterRateLimitError` | FAILURE-178, FAILURE-179 |

## At a glance
| When | Then | Claims |
| --- | --- | --- |
| Default settings, no check stops the bench, and a deployment that is not lone fails with 429 | A bench for the cooldown time | FAILURE-043, RDISP-191 |
| Default settings, no check stops it, and a deployment fails with 401 or 404, which is not a retryable status | A bench at once, even for a lone deployment | FAILURE-044 |
| Default settings, no check stops it, and a deployment that is not lone fails with a 5xx | A bench only if over half of at least 5 requests in this server's 60-second window failed, or all of at least 1000 | FAILURE-043, FAILURE-044 |
| Default settings, no check stops it, and a lone deployment fails with 429, 408 or a 5xx | A bench only if all of at least 1000 requests in that window failed | FAILURE-043, FAILURE-044 |
| A 4xx other than 429, 401, 402, 404 and 408, such as 400 or 403 | The status check stops the bench, unless the deployment's own `allowed_fails_policy` has an entry for that error type | FAILURE-031, FAILURE-032 |
| A lone deployment fails with 402 | No bench, unless the deployment's or the router's `allowed_fails_policy` has a matching entry | FAILURE-035 |
| The deployment sets no allowance; the router sets an `allowed_fails_policy`, or an `allowed_fails` other than the global value | The router's counter decides, lone deployments included | FAILURE-042, FAILURE-046 |
| The chosen cooldown time is `0` | No bench at all | FAILURE-027, RDISP-191 |
| Every backup entry fails or gets skipped | The caller gets the original error; a failed order-level walk surfaces its last failure instead | RDISP-105, RDISP-115 |

## Nine ordered checks can stop a bench before any rule decides
Nine checks, in order, can stop a bench [FAILURE-022]-[FAILURE-030]. They stop it for an unknown deployment, a failure of the caller's own credential, a request rejected before the call, or a personal Copilot session or credential [FAILURE-022]-[FAILURE-026]. They also stop it for a zero cooldown time, cooldowns turned off, a status that needs no bench, or a provider-default deployment [FAILURE-027]-[FAILURE-030].

The failure callback skips an advisor orchestration failure, a 404 from a background poll, a 408 from the caller's own timeout and a caller-scoped OAuth failure [RDISP-190]. Otherwise it counts the failure and passes a cooldown time: the deployment's own `cooldown_time` if 0 or more, else a retry-after header of 0 or more, else the router's [RDISP-191], [RDISP-193].

The status check lets the decision go on for 429, 401, 402, 404 and 408, and for every status outside 400 to 499 [FAILURE-031]. It stops the bench for any other 4xx, such as 400 or 403 [FAILURE-031]. It also stops the bench for an empty status and for any error whose text contains `APIConnectionError`, even a 500 [FAILURE-031], [FAILURE-209]. Only an entry for that error type in the deployment's own `allowed_fails_policy` lets the decision go on anyway [FAILURE-032].

## Under default settings, failure rates and status codes decide the bench
Under default settings, when no check stops it, one 401 or 404 benches a deployment at once, even a lone one [FAILURE-044]. One 429 benches it unless it is lone [FAILURE-043]. One 500 does not: a 5xx benches only when over half of at least 5 requests in this server's 60-second window failed, or all of 1000 for a lone one [FAILURE-043], [FAILURE-073].

Before any rule, a 402 on a lone deployment ends with no cooldown unless an `allowed_fails_policy` entry on the deployment or router matches it [FAILURE-035]. Otherwise configuration picks one of three rules [FAILURE-036], [FAILURE-042], [FAILURE-046]:

- **Deployment allowance.** When the deployment's own settings define `allowed_fails` or `allowed_fails_policy`, the counter decides with its number for this error, else the router's threshold [FAILURE-036], [FAILURE-040]. A lone deployment with only a plain number and no matching per-error entry never benches here [FAILURE-039].
- **Failure-rate rules.** Otherwise, when the router has no `allowed_fails_policy` and its `allowed_fails` is unset or equals the global value, these rules decide [FAILURE-042].
- **Router counter.** In every other case the counter decides with the router's settings, lone deployments included [FAILURE-046].

The failure-rate rules read only this server's per-minute counts [FAILURE-045]. The counter adds one per failure under `deployment:<id>:allowed_fails`, in Redis too when present, so the fleet shares it [FAILURE-049]. When the deployment's own number applies, the key gains a suffix, the error's class name or `"generic"`, and each suffix counts separately [FAILURE-040], [FAILURE-049]. It benches once the count goes strictly above the threshold, the first value set among a deployment override, the router's per-error policy and the router's `allowed_fails` [FAILURE-047], [FAILURE-049]. When the counter resets in under 1 second, Redis keeps no count [FAILURE-048], [FAILURE-051].

@figure flow id=cooldown-decision title="How the router decides whether to bench a failed deployment"
| node fail | A call fails | RDISP-193, FAILURE-021 |
| node gates | Does a check stop it? | FAILURE-022, FAILURE-029, FAILURE-030 |
| node own | Deployment sets own allowance? | FAILURE-036 |
| node default | Router allowance left default? | FAILURE-042 |
| node rate | Failure-rate rule matches? | FAILURE-043, FAILURE-044 |
| node count | Count above the allowance? | FAILURE-049 |
| node bench | Bench the deployment | FAILURE-052 |
| node skip | No cooldown | FAILURE-021 |
| fail > gates | checks run in order | FAILURE-022 |
| gates > skip | a check stops it | FAILURE-022 |
| gates > own | no check stops it | FAILURE-036 |
| own > count | yes | FAILURE-040 |
| own > default | no | FAILURE-042 |
| default > rate | yes | FAILURE-042 |
| default > count | no, router numbers | FAILURE-046 |
| rate > bench | a rule matches | FAILURE-043 |
| rate > skip | no rule matches | FAILURE-043 |
| count > bench | above the allowance | FAILURE-049 |
| count > skip | within the allowance | FAILURE-049 |

@steps cooldown-decision
| fail | A call fails | After most failures, the router counts the failure, picks a cooldown time and asks for a decision [RDISP-191], [RDISP-193]. A few kinds of failure, such as a timeout the caller set, skip all three [RDISP-190]. |
| gates | Nine checks come first | The nine checks listed in the section above run in order, and the first that applies stops the bench [FAILURE-022]-[FAILURE-030]. The status check stops it for every 4xx except 429, 401, 402, 404 and 408, unless the deployment's own allowed-fails policy has an entry for that error type [FAILURE-029], [FAILURE-031], [FAILURE-032]. |
| gates>own | A lone 402 stops early | Before the three rules, a 402 on a lone deployment ends with no cooldown, unless the deployment's or the router's allowed-fails policy has an entry for that error [FAILURE-035]. |
| own | The deployment's own numbers come first | A deployment with its own allowance gets counted with its number for this error, or with the router's number when it has none for this error [FAILURE-036], [FAILURE-040]. A lone deployment with only a plain allowance never benches this way [FAILURE-039]. |
| rate | Default settings use failure rates | A 429 benches unless the deployment is lone [FAILURE-043]. A status that is not retryable, such as 401 or 404, benches even a lone deployment [FAILURE-044]. Any other failure benches the deployment only when over half of at least 5 requests in this server's 60-second window failed, or all of at least 1000 for a lone one [FAILURE-043], [FAILURE-073]. |
| count | The counter needs a strict excess | The router benches once the count goes above the allowance, so an allowance of 1 benches on the second failure, and 0 on the first [FAILURE-046], [FAILURE-047], [FAILURE-049]. |
| bench | One entry is the whole bench | The router writes one timed entry [FAILURE-052]. A background task then updates the Prometheus metrics when Prometheus is set up; the bench itself alerts no one [FAILURE-052], [FAILURE-056]. |

## A cooldown is a timed entry that other servers usually see within a second
A bench is one timed entry holding the status, the error message with its first 50 characters kept and the rest starred, the time it started, and its length [FAILURE-002], [FAILURE-003]. When the servers share Redis, the others usually see it within about a second [FAILURE-009]. A bench under 1 second never reaches Redis, because Redis keeps whole seconds [FAILURE-006].

The entry sits under `deployment:<id>:cooldown` in a dedicated cooldown store: its own memory tier, plus Redis when the router has it [FAILURE-001], [FAILURE-006], [FAILURE-008]. It expires after the cooldown time [FAILURE-006]. A Slack alert is a separate path with its own conditions, and an alerting failure never changes the request's outcome [FAILURE-175], [FAILURE-177].

A server that lacks the entry in memory re-reads Redis at most once per read interval, 1 second by default [FAILURE-009]. A failed Redis write, including every cooldown under 1 second, gets swallowed, so that cooldown stays on this server [FAILURE-006], [FAILURE-203]. An entry stays active while its stored time plus its length lies ahead of the reader's clock, so clock skew between servers shifts the end [FAILURE-012], [FAILURE-188]. A synchronous read hit by a Redis error other than an open circuit breaker reports no cooldowns at all, and so does a failed shared batch read [FAILURE-015], [FAILURE-093]. An unhealthy health mark counts for 600 seconds by default [FAILURE-086].

The example assumes default settings, no retry-after header, no per-deployment cooldown time and Redis shared by two servers [FAILURE-009], [FAILURE-048], [RDISP-191].

@figure timeline id=two-rate-limits title="Example: both gpt-4o deployments hit rate limits, with no backup models listed"
| lane a | Deployment dep-a |
| lane b | Deployment dep-b |
| lane peer | Another server |
| lane sel | Selection for gpt-4o |
| 0s | a | call fails with 429 | benched for 5 seconds | FAILURE-043, FAILURE-048 |
| 0s | sel | next pick skips dep-a | dep-b serves | RSELECT-044, FAILURE-011 |
| 1s | peer | re-reads the shared store | sees dep-a benched | FAILURE-009 |
| 2s | b | call fails with 429 | benched for 5 seconds | FAILURE-043, FAILURE-048 |
| 3s | sel | finds no deployment left | 429, try again in 5 | RSELECT-054, FAILURE-179, FAILURE-017 |
| 5s | a | cooldown time passes | serving again | FAILURE-012 |
| 7s | b | cooldown time passes | serving again | FAILURE-012 |

## A retry policy sets how many same-group retries each error type gets
Before trying backup models, the router can retry the same model group, up to its retry count [RDISP-131]. A retry policy, when configured, sets that count per kind of error, such as rate limits or timeouts [FAILURE-099], [FAILURE-103]. A request that sets its own retry count to 0 turns the policy off; a router-wide 0 does not [RDISP-138].

The retry loop consults a policy only when the request did not set `num_retries` to `0` and a `retry_policy` or `model_group_retry_policy` exists [RDISP-138]. A group's own policy replaces the router-wide one whole [FAILURE-099], [FAILURE-100]. A 404 uses the not-found count first, when set; otherwise the lookup walks the error's class upward and takes the first count set, else the default count [FAILURE-102], [FAILURE-103]. A policy count replaces the retry count, so even a 400 or 404 retries that many times [RDISP-138].

## The fallback walk skips backup entries it already tried
After retries run out, the router can try the backup models on its list, one at a time and in order [FAILURE-114], [FAILURE-194]. It skips an entry it already tried for this request, and some entries it may not use [FAILURE-143], [FAILURE-145]. The first backup model that answers ends the search [FAILURE-150].

In a fallbacks list, an exact key wins, else a bare name entry, a provider-prefixed or provider-stripped key, then the catch-all "*" [FAILURE-114]. Across several lookup groups, a group's own chain beats the catch-all [FAILURE-119], [FAILURE-120]. The walk, `run_async_fallback`, re-raises the original error and tries nothing when it starts at or past `max_fallbacks` [FAILURE-138]. A target with a server-owned token-exchange field stops it with an error before any attempt [FAILURE-139].

Each target's identity enters the attempted set before its attempt; a target that is neither a name nor a mapping has none and never counts as a repeat [FAILURE-109], [FAILURE-145], [FAILURE-199]. Each attempt adds one to the depth and calls `async_function_with_fallbacks`, so the backup gets its own retries and can start a nested walk, from its own chain or the original group's [FAILURE-120], [FAILURE-147], [FAILURE-149]. A success sets `x-litellm-attempted-fallbacks` to the walk's depth and, with `include_fallback_errors`, appends the walk's error list [FAILURE-150]. A failure fires the failure event, may bench the target's deployment, and moves on [FAILURE-067], [FAILURE-151]. If nothing succeeds, the walk raises the latest error, or the original if it skipped every target, with no headers [FAILURE-152].

@figure flow id=fallback-walk title="Each backup entry passes five checks before the walk calls it"
| node start | Depth below the cap? | FAILURE-138 |
| node next | Take the next entry | FAILURE-141, FAILURE-194 |
| node same | Same as failed group? | FAILURE-141 |
| node pinned | Pinned provider resource? | FAILURE-142 |
| node allowed | Access and budget allow? | FAILURE-143, FAILURE-144 |
| node tried | Already tried this request? | FAILURE-145 |
| node call | Call the backup model | FAILURE-146, FAILURE-149 |
| node done | Return the response | FAILURE-150 |
| node raise | Raise an error | FAILURE-138, FAILURE-152 |
| start > next | yes | FAILURE-138 |
| start > raise | no, original error | FAILURE-138 |
| next > same | an entry is left | FAILURE-141 |
| next > raise | list used up | FAILURE-152 |
| same > next | yes, skip | FAILURE-141 |
| same > pinned | no | FAILURE-142 |
| pinned > next | yes, skip | FAILURE-142 |
| pinned > allowed | no | FAILURE-143 |
| allowed > next | no, skip | FAILURE-143, FAILURE-144 |
| allowed > tried | yes | FAILURE-145 |
| tried > next | yes, skip | FAILURE-145 |
| tried > call | no, record it | FAILURE-145 |
| call > done | succeeds | FAILURE-150 |
| call > next | fails | FAILURE-151 |

@steps fallback-walk
| start | The cap is checked once | A walk that starts at or past the maximum depth raises the original error and tries nothing [FAILURE-138]. A walk already running never checks the maximum again [FAILURE-147]. |
| same | The failed model is skipped by name | An entry that is just the failed model's name gets skipped [FAILURE-141]. An entry with extra settings, such as an order level, still runs even when it names that model [FAILURE-109], [FAILURE-141]. |
| pinned | Some requests stay put | Some operations keep to the original model group when the request carries a file, batch or job id [FAILURE-137], [FAILURE-142]. They are creating or cancelling a batch, creating, cancelling or reading a fine-tuning job, and reading or deleting a file; creating a file also stays [FAILURE-137]. |
| allowed | Optional access and budget checks | Whoever builds the router can add an access check and a budget check, such as the proxy's check that a key may call a backup model [FAILURE-143], [FAILURE-219]. An entry either check rejects gets skipped and recorded [FAILURE-143], [FAILURE-144]. |
| tried | Tried entries get skipped | The walk skips an entry already tried anywhere in this request, counting an entry with extra settings apart from the bare model name [FAILURE-109], [FAILURE-145]. An entry that is neither a model name nor a set of settings never counts as tried, so it can run again [FAILURE-109], [FAILURE-184]. |
| call | A backup call can nest | Each backup call goes through the router again, with its own retries, and can start a nested walk of its own [FAILURE-149]. |
| call>done | The first success ends the walk | The walk reports its depth in a header and returns, trying no later entry [FAILURE-150]. |
| call>next | A failure moves on | The walk keeps the error and moves to the next entry [FAILURE-151]. |

## When nothing is left to pick, selection fails with a 429 error
When no deployment of a model survives selection, cooldowns included, it fails with a 429 (too many requests) error whose message starts with "No deployments available for selected model" [RSELECT-054], [FAILURE-179]. That error goes to the router's backup handling like other failures; in the usual case the caller sees it only if no backup model answers [RDISP-096], [RDISP-115].

The error is a `RouterRateLimitError`; its "Try again in" value is the smallest configured cooldown among the model's deployments [FAILURE-017], [FAILURE-178]. It adds that all deployments are in cooldown only when every deployment of the model is cooling, and its cooldown list names every benched deployment in the router [FAILURE-178], [FAILURE-179].

## Watch out
- Under default settings, a 429 or 5xx never benches a lone deployment unless all of at least 1000 requests in a minute failed, so the router keeps sending to it [FAILURE-043].
- The router compares its own failure allowance with the library-wide default, 3 unless changed; an equal value counts as unset, so a router allowance of 3 gets the failure-rate rules [FAILURE-042], [FAILURE-208]. A deployment's own allowance of 3 still counts [FAILURE-036].
- With the maximum number of fallbacks set to 1 and three backup models listed, all three get tried when each fails [FAILURE-147]. The setting only stops each backup from starting fallbacks of its own [FAILURE-147].
- A bench shorter than one second stays on one server, so the other servers keep sending traffic to that deployment; this matters when someone sets a cooldown time under 1 second [FAILURE-006], [FAILURE-187].
- An error whose message merely contains the connection-error text stops the bench at the status check, whatever its real status code [FAILURE-031], [FAILURE-209].
- A stored cooldown keeps the first 50 characters of the error text unmasked, so a key echoed early in a provider error can reach the shared store and the logs [FAILURE-210].
- The "try again in" number is the shortest configured cooldown, not the time left on any cooldown [FAILURE-017], [FAILURE-178].
- The x-litellm-attempted-fallbacks header can undercount: when a nested walk succeeds, each outer walk overwrites it with its own smaller depth [FAILURE-213], [FAILURE-216].
