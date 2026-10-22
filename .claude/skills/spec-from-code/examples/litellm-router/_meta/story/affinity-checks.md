---
module: affinity-checks
---
# Optional filters send each follow-up request to the deployment that holds its state

@plain
For each request, the router picks one deployment from a model group [RCALL-045]. An earlier request's deployment may hold an earlier answer, a cached long prompt, or locked reasoning that only its account can open [AFFINITY-022] [AFFINITY-061] [AFFINITY-087] [AFFINITY-069] [AFFINITY-072]. When switched on, the router notes the deployment chosen for a caller or chat session, and the one that served a long prompt [AFFINITY-045] [AFFINITY-046] [AFFINITY-091]. Locked reasoning carries its deployment's name inside the request [AFFINITY-164]. These optional filters send the next request back there [AFFINITY-028] [AFFINITY-029] [AFFINITY-061] [AFFINITY-087]. If a caller's deployment is unhealthy or gone, normal routing picks another [AFFINITY-030]. That caller can then lose its place in the prompt cache for up to an hour by default [AFFINITY-198]. A follow-up turn can also lose its locked reasoning without any error [AFFINITY-159].

@minute
On the router's async selection path, every registered filter takes the candidate list in turn, after the health and cooldown filters [RSELECT-043] [RSELECT-044] [RSELECT-047] [AFFINITY-009]. The deployment-affinity and prompt-cache filters return the list unchanged or narrowed to one deployment [AFFINITY-022] [AFFINITY-029] [AFFINITY-087]. The encrypted-content filter can keep several, and the continuation filter can keep none [AFFINITY-062] [AFFINITY-133]. A pre-call hook claims caller and session pins just before the provider call, and the first writer wins [AFFINITY-041] [AFFINITY-047]. A success callback writes prompt-cache pins after the call, and the last writer wins [AFFINITY-091] [AFFINITY-114].

## Words you'll see
| Term | Means | In the code | Claims |
| --- | --- | --- | --- |
| model group | the public model name a caller asks for, shared by several deployments | `model_name` | AFFINITY-025, RCALL-045 |
| deployment | one configured way to reach a model at a provider, with its own address, key and unique id | `model_info.id` | AFFINITY-031, AFFINITY-069 |
| locked reasoning | reasoning a provider returned in encrypted form, which a later request replays; only a deployment on the same account keeps it | `encrypted_content` | AFFINITY-058, AFFINITY-072 |
| pin | a stored note that names the deployment holding a caller's, a session's or a prompt's state | `model_id` | AFFINITY-044, AFFINITY-100 |
| candidate list | the deployments still in the running when a filter takes its turn, after earlier filters have had theirs | `healthy_deployments` | AFFINITY-009, AFFINITY-177, AFFINITY-030 |
| filter | an optional check that can shrink the candidate list before the strategy picks one | `async_filter_deployments` | AFFINITY-009 |
| cooldown | a pause during which the router sends a deployment no traffic | `deployment:<model_id>:cooldown` | FAILURE-001, RSELECT-044 |
| asynchronous call | a request made through the router's non-blocking methods, which let the program do other work while it waits | `Router.acompletion` | AFFINITY-012, AFFINITY-157 |
| routing strategy | the rule that picks one deployment from the candidates that remain | `routing_strategy` | AFFINITY-012, RSELECT-068 |
| pre-call checks setting | the router setting that lists which optional filters to build | `optional_pre_call_checks` | AFFINITY-001 |
| deployment-affinity filter | the one filter per router that reads caller pins, session pins and earlier response ids | `DeploymentAffinityCheck` | AFFINITY-001 |
| caller pin | a pin per caller and group, switched on by the caller-affinity name | `deployment_affinity` | AFFINITY-001, AFFINITY-036 |
| session pin | a pin per client session, scoped to the caller when one is known | `session_affinity`, `session_id`, `unscoped` | AFFINITY-001, AFFINITY-027, AFFINITY-037 |
| response continuity | sending a follow-up to the deployment whose earlier response it names | `responses_api_deployment_check`, `previous_response_id` | AFFINITY-002, AFFINITY-022 |
| encrypted-content filter | the filter that returns replayed locked reasoning to a deployment able to decrypt it, when a candidate can | `EncryptedContentAffinityCheck`, `encrypted_content_affinity` | AFFINITY-005, AFFINITY-061, AFFINITY-062 |
| prompt-cache filter | the filter that returns a long prompt to the deployment pinned for its prefix, when that deployment is a candidate | `PromptCachingDeploymentCheck`, `prompt_caching` | AFFINITY-006, AFFINITY-084, AFFINITY-087 |
| continuation filter | the filter that keeps only deployments able to finish a broken stream, when a request continues one | `ContinuationPrefillDeploymentCheck`, `enable_mid_stream_fallback_continuation` | AFFINITY-008, AFFINITY-133, AFFINITY-134 |
| per-group switches | a list of filter names for one group that replaces the global caller, session and response switches | `model_group_affinity_config` | AFFINITY-021 |
| order hop | a fallback attempt aimed at the deployments of one order level inside the group | `_target_order` | AFFINITY-020 |
| priority group | a routing group that uses the priority strategy, where caller, session and prompt-cache pins step aside | `is_priority_group` | AFFINITY-024, AFFINITY-080 |
| caller key | who is calling: the virtual key's hash, or else the user id with a prefix | `user_api_key_hash`, `user_api_key_user_id`, `user_id:` | AFFINITY-034 |
| metadata bucket | the request field that carries bookkeeping, where the proxy or the calling program puts the caller and session | `litellm_metadata`, `metadata` | AFFINITY-150, AFFINITY-184 |
| session marker | a per-request lifetime the router stamps to switch session pins on for one request | `_session_deployment_affinity_ttl` | AFFINITY-026 |
| pin lifetime | how long a caller or session pin lives without renewal, one hour by default | `deployment_affinity_ttl_seconds` | AFFINITY-003 |
| origin marker | a tag on replayed reasoning that names the deployment that produced it | `encitem_`, `litellm_enc:`, `litellm_encrypted_reasoning:` | AFFINITY-058, AFFINITY-059 |
| encryption boundary | the provider address and key pair that decides which account can decrypt reasoning | `api_base`, `api_key` | AFFINITY-069 |
| pinned mark | a request flag that tells the router to skip the strategy when one candidate remains | `_encrypted_content_affinity_pinned` | AFFINITY-061, AFFINITY-013 |
| cache breakpoint | a marker in the messages that ends the part a provider may cache | `cache_control` | AFFINITY-101 |
| cache minimum | the fewest prompt tokens a model will cache | `prompt_cache_min_tokens` | AFFINITY-084 |
| continuation marker | a private object the router puts on a request only when it continues a broken stream | `_mid_stream_continuation` | AFFINITY-130 |
| prefill support | whether a model accepts a partial assistant answer to carry on from | `supports_assistant_prefill` | AFFINITY-131 |
| synchronous call | a request made through the router's blocking methods, which wait for the answer; the pin filters never run for it | `Router.completion` | AFFINITY-012 |
| process-wide filter list | the one list of filters that every router in the process runs | `litellm.callbacks` | AFFINITY-200 |

## At a glance
| When | Then | Claims |
| --- | --- | --- |
| A known caller repeats a request, caller pins are on, and no earlier check decided | only the pinned deployment stays, if it is still a candidate | AFFINITY-029, AFFINITY-030 |
| Session pins are on, or the session marker is set, and the request has a client session id | the session pin is read before the caller pin | AFFINITY-026, AFFINITY-028 |
| Response continuity is on, the request is not an order hop, and `previous_response_id` names a candidate | that deployment wins before the priority-group, session and caller checks | AFFINITY-022, AFFINITY-020 |
| The request is an order hop | the deployment-affinity and prompt-cache filters pass the list through; with an integer order and an origin marker, the encrypted-content filter decides among that order's deployments only | AFFINITY-020, AFFINITY-081, AFFINITY-056, AFFINITY-201 |
| The group is a priority group | caller, session and prompt-cache pins are skipped | AFFINITY-024, AFFINITY-080 |
| A group has per-group switches | they replace the global caller, session and response switches (an empty list turns all three off), and can only add the encrypted-content filter | AFFINITY-021, AFFINITY-055 |
| No candidate is the reasoning's origin or shares its boundary | the reasoning is stripped, a warning is logged, and routing goes on | AFFINITY-064, AFFINITY-159 |
| The prompt has no cache breakpoint, or is below the candidates' lowest cache minimum (`1024` tokens by default) | no prompt-cache pin is read | AFFINITY-084, AFFINITY-111 |
| The call uses a sync router method, or a router strategy with no async selector | no pin filter runs; only the continuation check applies | AFFINITY-012 |
| A filter raises, for example when the encrypted-content filter is active and `litellm_metadata` cannot take new keys | selection fails and the caller gets the error | AFFINITY-070, AFFINITY-157 |

## The filters run between the health checks and the strategy's pick
For an asynchronous call, the router first drops deployments that are cooling down or, when health filtering applies, unhealthy [RSELECT-043] [RSELECT-142] [RSELECT-044]. Each optional filter that is switched on then gets the remaining list in turn [RSELECT-047] [AFFINITY-009]. The routing strategy picks from what is left, unless the encrypted-content filter left one pinned deployment [RSELECT-068] [AFFINITY-013]. A filter error fails the request, and the caller gets it [AFFINITY-157].

In the pre-call checks setting, `deployment_affinity`, `session_affinity` and `responses_api_deployment_check` switch on one shared deployment-affinity filter per router [AFFINITY-001]. The name `encrypted_content_affinity`, in the setting or in a group's switches, adds the encrypted-content filter; `prompt_caching` adds the prompt-cache filter [AFFINITY-005] [AFFINITY-006]. Per-group switches set at construction, or a complexity router that uses a deployment pin, also ensure a deployment-affinity filter exists [AFFINITY-004]. The setting `enable_mid_stream_fallback_continuation` adds the continuation filter [AFFINITY-008].

Each filter takes the previous filter's output, and the encrypted-content filter runs before the deployment-affinity filter [AFFINITY-009] [AFFINITY-177]. No failure callback sees a filter's error [AFFINITY-157]. A sync router method, or an async call whose router-level strategy is not `"usage-based-routing-v2"`, `"simple-shuffle"`, `"cost-based-routing"`, `"latency-based-routing"` or `"least-busy"`, runs none of the pin filters [AFFINITY-012].

## Each request follows its response, session or caller pin, in that order
When its switches are on, the deployment-affinity filter sends a follow-up that names an earlier response back to that response's deployment, if it is still a candidate [AFFINITY-021] [AFFINITY-022] [AFFINITY-023]. Otherwise a chat session's pin decides, then the caller's pin [AFFINITY-028] [AFFINITY-029]. Order hops skip this filter's pins [AFFINITY-020]. With no usable pin, the list passes through unchanged [AFFINITY-030].

@figure flow id=affinity-read title="How the deployment-affinity filter chooses between its pins"
| node hop | Order hop? | AFFINITY-020 |
| node resp | Earlier response names candidate? | AFFINITY-022 |
| node prio | Priority group? | AFFINITY-024 |
| node scope | One shared group name? | AFFINITY-025 |
| node sess | Session pin names candidate? | AFFINITY-028 |
| node caller | Caller pin names candidate? | AFFINITY-029 |
| node one | Only that deployment | AFFINITY-022, AFFINITY-028, AFFINITY-029 |
| node all | Whole list unchanged | AFFINITY-030 |
| hop > all | yes | AFFINITY-020 |
| hop > resp | no | AFFINITY-022 |
| resp > one | yes | AFFINITY-022 |
| resp > prio | no | AFFINITY-023 |
| prio > all | yes | AFFINITY-024 |
| prio > scope | no | AFFINITY-025 |
| scope > all | no | AFFINITY-025 |
| scope > sess | yes | AFFINITY-028 |
| sess > one | yes | AFFINITY-028 |
| sess > caller | no or missing | AFFINITY-028 |
| caller > one | yes | AFFINITY-029 |
| caller > all | no or missing | AFFINITY-030 |

@steps affinity-read
| hop | Order hops skip pins | A fallback attempt aimed at one order level gets the list back untouched, and no pin is read [AFFINITY-020]. |
| resp | An earlier response comes next | With response continuity on, an earlier response that names a candidate wins before the priority-group, session and caller checks [AFFINITY-022]. |
| prio | Priority groups skip the rest | A routing group that uses the priority strategy gets its list back unchanged [AFFINITY-024]. |
| scope | All candidates share one name | The pin belongs to the group name the candidates share; if they disagree, the filter steps aside [AFFINITY-025]. |
| sess | A session pin beats a caller pin | When session pins are active and the request has a session, a session pin that names a candidate wins [AFFINITY-028]. |
| caller | The caller pin comes last | With caller pins on and a known caller, a caller pin that names a candidate wins [AFFINITY-029]. |
| all | No usable pin changes nothing | A missing pin, or one naming no candidate, leaves the choice to the strategy [AFFINITY-030]. |

The caller key is the virtual key's hash from the metadata bucket, or else the user id prefixed with `user_id:` [AFFINITY-034]. The request's own user parameter never counts [AFFINITY-034]. The filter keeps a 64-character key that base-16 parsing accepts, lower-cased, and hashes any other, so raw keys and user ids never reach a cache key [AFFINITY-035]. A session pin key also carries the hashed caller key, or `unscoped` without one, so two callers reusing one session id never share a pin [AFFINITY-037].

Session pins are active when the session switch is on, or when the session marker holds a positive integer [AFFINITY-026]. The filter ignores a session id that the proxy generated for a request that had none [AFFINITY-027]. A failed cache read counts as no pin [AFFINITY-032].

## The first deployment chosen for a caller keeps the pin
Just before the router sends a request to the provider, it claims the caller's and the session's pins for the chosen deployment, when those pins are switched on [AFFINITY-041] [AFFINITY-043]. The first claim wins [AFFINITY-047]. A later claim for another deployment changes nothing, while a repeat claim by the same deployment restarts the pin's lifetime, one hour by default [AFFINITY-047] [AFFINITY-003].

The writer runs inside the async call wrapper of the software development kit (SDK), under the selected deployment's own group name rather than the caller's alias [AFFINITY-041] [AFFINITY-042]. It writes nothing unless caller pins are on with a known caller, or session pins are active with a real session id [AFFINITY-043]. The lifetime is `deployment_affinity_ttl_seconds`, `3600` seconds by default; a session pin uses the session marker's value when the router set one [AFFINITY-003] [AFFINITY-046].

With Redis attached, the claim runs as one atomic Redis script [AFFINITY-048]. If that script fails, the writer claims in memory instead, which keeps the same pod sticky but loses agreement across pods [AFFINITY-049]. Errors during a claim are caught and logged at debug level, and the request goes ahead; a task cancellation still escapes [AFFINITY-051].

@figure timeline id=stale-pin title="Example: a caller pin outlives its deployment, then moves"
| lane c | Caller alice |
| lane pin | Caller pin |
| lane a | Deployment A |
| lane b | Deployment B |
| 0s | c | first request, no pin yet | strategy picks A | AFFINITY-030 |
| 0s | pin | claimed before the provider call | names A for 3600 s | AFFINITY-041, AFFINITY-045, AFFINITY-003 |
| 10 min | c | repeat request reads the pin | served by A | AFFINITY-029 |
| 10 min | pin | A claims it again | expiry reset to 3600 s | AFFINITY-047, AFFINITY-003 |
| 20 min | a | becomes unhealthy | not a candidate | AFFINITY-030 |
| 20 min | b | strategy picks B for alice | serving alice | AFFINITY-030 |
| 20 min | pin | B's claim loses to A | still names A | AFFINITY-047, AFFINITY-163 |
| 70 min | pin | lifetime lapses | no pin | AFFINITY-163 |
| 75 min | b | next request claims the pin | pin names B | AFFINITY-047, AFFINITY-163 |

Two overlapping first requests can land on different deployments, because reading and claiming are separate steps; the first claim wins [AFFINITY-178].

## Encrypted reasoning goes back to the account that can unlock it
A client can send back reasoning that one deployment produced in locked form, tagged with that deployment's id [AFFINITY-058]. Only the same provider account, meaning the same address and key, keeps that reasoning [AFFINITY-069] [AFFINITY-072]. So the filter sends the request to that deployment or a twin on the same account, and otherwise removes the locked reasoning, tagged or not [AFFINITY-061] [AFFINITY-062] [AFFINITY-064].

@figure flow id=encrypted title="Where the encrypted-content filter sends replayed reasoning"
| node mark | Origin marker found? | AFFINITY-058, AFFINITY-059 |
| node cand | Origin is a candidate? | AFFINITY-061 |
| node peer | Candidate shares its boundary? | AFFINITY-062 |
| node pin | Only the origin | AFFINITY-061 |
| node peers | Only boundary peers | AFFINITY-062 |
| node strip | Strip reasoning, route normally | AFFINITY-064 |
| node pass | Whole list unchanged | AFFINITY-060 |
| mark > pass | no | AFFINITY-060 |
| mark > cand | yes | AFFINITY-061 |
| cand > pin | yes | AFFINITY-061 |
| cand > peer | no | AFFINITY-062 |
| peer > peers | yes | AFFINITY-062 |
| peer > strip | no | AFFINITY-064 |

@steps encrypted
| mark | Read the origin | The filter takes the origin from the first marked input item, or else from the first tagged thinking block in the messages [AFFINITY-058] [AFFINITY-059]. |
| cand>pin | Pin to the origin | If the origin is a candidate, the filter returns only it and marks the request as pinned [AFFINITY-061]. |
| peer>peers | Stay on the same account | If the router still knows the origin, every candidate on the same encryption boundary is returned [AFFINITY-062]. |
| peer>strip | Degrade instead of failing | Otherwise the filter logs a warning, strips the encrypted reasoning from the input and the tagged thinking blocks from the messages, and returns the candidates [AFFINITY-064] [AFFINITY-067]. |

The filter runs for a group when its global switch is on or the group's switches list it [AFFINITY-055]. With exactly one candidate left and the pinned mark set, the router skips the strategy, so a rate-aware strategy cannot steer the request away [AFFINITY-013]. On every fallback hop, the router repeats the strip check for the new target [AFFINITY-075].

Stripping edits the caller's lists in place, so a later attempt and an SDK caller see the stripped list [AFFINITY-068] [AFFINITY-181]. The degrade path looks the same whether the origin is cooling down, removed or forged [AFFINITY-065].

## A long cached prompt returns to the deployment that holds its cache
When a long prompt marks where its reusable opening ends, the router remembers which deployment served that opening [AFFINITY-101] [AFFINITY-091]. The next request with the same opening goes back to that deployment, if it is still a candidate [AFFINITY-087]. The filter leaves short prompts, and groups with a single candidate, alone [AFFINITY-082] [AFFINITY-084].

It also steps aside for a priority group, an order hop or missing chat messages [AFFINITY-080] [AFFINITY-081] [AFFINITY-083].

The pin key hashes the cacheable prefix: everything up to the last cache breakpoint, a `cache_control` marker of type `"ephemeral"` [AFFINITY-101] [AFFINITY-102]. Each block's hash chains the hash of everything before it, so a key binds the whole prefix, roles included [AFFINITY-106]. A read probes the keys of the last `20` positions, newest first, so a breakpoint that moved to a later turn still finds the deployment that cached the earlier prefix [AFFINITY-110] [AFFINITY-111]. The key comes from the messages as they will be sent, including breakpoints that auto prompt caching would inject [AFFINITY-086].

A success callback writes the pin, only for the call types `"completion"`, `"acompletion"` and `"anthropic_messages"` [AFFINITY-089]. The logged messages must reach the serving model's own cache minimum [AFFINITY-091]. A pin lasts `300` seconds, or `3600` when a breakpoint asks for `"1h"` and the deployment honours one-hour caching [AFFINITY-112] [AFFINITY-092] [AFFINITY-113]. Writes are last-writer-wins, so in a mixed group the latest serving deployment owns the prefix [AFFINITY-114].

## A broken reply resumes only on a deployment that can continue it
Sometimes a streamed answer breaks after the user has already seen part of it [RCALL-008]. When continuation is switched on, the router can ask another deployment to carry on from that partial answer [AFFINITY-008] [RCALL-019] [RCALL-008]. Only a deployment that accepts a partial answer, and whose own settings do not reshape the output, may take over [AFFINITY-133]. The client then sees one joined reply [AFFINITY-141].

Only an eligible break puts the continuation marker on the request, and no value in request JSON can imitate it [RCALL-008] [AFFINITY-130]. Prefill support comes from the deployment's `supports_assistant_prefill` flag, or else from the model cost map [AFFINITY-131]. Constraints include more than one choice, a structured response format and a forced tool choice [AFFINITY-132]. With no deployment left, the router moves along its fallback chain and finally surfaces the original stream error [AFFINITY-133].

The splice holds the first fallback chunks while they repeat the prefill, drops a full echo, and drops re-sent trailing whitespace [AFFINITY-139] [AFFINITY-140]. With post-call rules set, the outermost splice re-checks the whole text and raises before a failing chunk reaches the client [AFFINITY-142] [AFFINITY-143].

## Watch out
- A caller or session pin is not cleared when its deployment fails or is removed [AFFINITY-198]. Until it lapses (one hour by default) or the deployment returns, that caller's requests go elsewhere, and no other deployment can take over the pin [AFFINITY-163] [AFFINITY-003]. Only a debug-level log line records the miss [AFFINITY-030].
- Caller and session pins are written before the provider answers, so a first request that fails can still pin its caller to the failing deployment [AFFINITY-041] [AFFINITY-194].
- A synchronous call, and any call on a router whose routing strategy lacks an asynchronous version, skips the pin filters, and nothing is logged [AFFINITY-203]. Some of these calls still write pins that nothing reads [AFFINITY-012].
- When one process builds several routers with the same filter settings, the process-wide filter list keeps only the first router's filters, so every router uses that router's pin stores [AFFINITY-200] [AFFINITY-202]. Discarding that first router silently turns the filters off for the rest [AFFINITY-202].
- A reasoning tag carries no signature, so a client can steer a request to any candidate it names [AFFINITY-154]. They do not check caller or session identity either; they rely on the proxy's authentication step, or the calling program, to fill it in truthfully [AFFINITY-184].
- When reasoning cannot return to its origin, the follow-up turn loses it with no error; only a log warning shows it [AFFINITY-159].
- Near the prompt-cache size limit, the read check and the write check measure against different models, so some pins are written but never read [AFFINITY-199].
- When the encrypted-content filter leaves a single pinned deployment, the request skips the routing strategy [AFFINITY-013]. Under usage-based routing version 2, a pinned deployment already at its requests-per-minute limit then fails the request with a rate-limit error to the caller, and goes into cooldown [AFFINITY-013].
