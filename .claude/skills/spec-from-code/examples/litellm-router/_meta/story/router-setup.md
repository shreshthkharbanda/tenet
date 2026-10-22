---
module: router-setup
---
# Building a router settles its defaults and the rule that picks each deployment

@plain
The router is a library inside the caller's own program [SYS-001]. A caller asks for a model group, a public model name [RSETUP-096]. On each try, it picks one deployment of that group: one provider's copy of the model [RSETUP-162]. This part builds the router from optional settings [RSETUP-277]. For the retry count and fallback cap, it takes your value, else a library-wide one, else a built-in default [RSETUP-031], [RSETUP-032]. It also decides which rule picks the deployment for each request [RSETUP-105]. Usually a chat request then goes into the retry and fallback loop [RSETUP-157], [RSETUP-190]. When this goes wrong, some bad settings stop the build with an error, and others are kept silently [RSETUP-257], [RSETUP-260]. A default queue priority set to any whole number makes every asynchronous chat request fail with an error [RSETUP-297].

@minute
The constructor reads its global settings once, builds the caches and registers callbacks on process-wide lists [RSETUP-277], [RSETUP-014], [RSETUP-049]. It validates the generic and content-policy fallback lists and, except for `"lar1"`, the top-level strategy, then builds that strategy's selector when it has one [RSETUP-257], [RSETUP-040], [RSETUP-045], [RSETUP-072]. Per request, the routing context takes a valid per-request override first, then the model's routing group, then the top-level strategy [RSETUP-105]-[RSETUP-108]. `completion` stamps bookkeeping into the request and hands it to the retry and fallback loop [RSETUP-157]. `acompletion` does too, except it diverts a prompt-management model, and sends a whole-number priority through the scheduler first [RSETUP-186], [RSETUP-187], [RSETUP-190].

## Words you'll see
| Term | Means | In the code | Claims |
| --- | --- | --- | --- |
| router | the object that takes requests for model groups and picks a deployment for each try | `Router` | SYS-001, RSETUP-162, RCALL-045 |
| model group | the public model name a caller asks for, shared by one or more deployments | `model_name` | RSETUP-092, RSETUP-096 |
| deployment | one provider's copy of a model, with its own credentials | `model_list`, `litellm_params` | RSETUP-022, RSETUP-024, RSETUP-166 |
| global setting | a library-wide value the router uses when your setting is unset, or your fallback list empty | `litellm.num_retries`, `litellm.fallbacks` | RSETUP-031, RSETUP-037 |
| retry count | how many more tries the loop makes inside the same group | `num_retries` | RSETUP-031 |
| fallback cap | the most fallback hops one request may take | `max_fallbacks` | RSETUP-032 |
| allowed failures | how many failures a deployment may have before it cools down | `allowed_fails` | RSETUP-026, FAILURE-046 |
| cooldown time | how long a failing deployment sits out | `cooldown_time` | RSETUP-027 |
| timeout | how long a provider call may run | `timeout` | RSETUP-033 |
| strategy | the rule that picks one deployment among the healthy ones | `routing_strategy` | RSETUP-036, RSETUP-083, RSELECT-067, RSELECT-068 |
| selector | the object that carries out a least-busy, usage-based, latency-based or cost-based strategy | `RouterStrategySelector`, `leastbusy_logger` | RSETUP-068, RSETUP-069, RSETUP-072 |
| routing group | a named set of model groups with its own strategy | `routing_groups` | RSETUP-088, RSETUP-091 |
| priority group | a routing group called by its own name; it can rank its members, and its strategy is random shuffle | `"priority"` | RSETUP-094, RSETUP-107 |
| per-request override | a strategy name sent with one request, used for that request only | `routing_strategy` | RSETUP-100, RSETUP-105 |
| routing context | the strategy and selector chosen for one request | `_get_routing_context` | RSETUP-105, RSETUP-108 |
| callback lists | process-wide lists of callbacks: objects the library notifies around every provider call | `litellm.callbacks`, `litellm.success_callback` | RSETUP-049, RSETUP-078 |
| pre-call check | an optional check that can filter deployments or raise an error before a call | `optional_pre_call_checks` | RSETUP-136, RSETUP-145, RSETUP-168, AFFINITY-009 |
| discard | detaching a router from the process-wide lists | `discard()` | RSETUP-062, RSETUP-064 |
| blocking chat call | the chat method that makes its caller wait for the reply, with no queue | `completion` | RSETUP-157, RSETUP-160 |
| asynchronous chat call | the chat method a caller's program can wait on while doing other work; unlike the blocking chat call, it can queue requests | `acompletion` | RSETUP-186, RSETUP-190, RSETUP-160 |
| retry and fallback loop | the code that retries inside a group, then tries other groups | `function_with_fallbacks`, `async_function_with_fallbacks` | RSETUP-157, RSETUP-190 |
| metadata bucket | the request's metadata, which the router writes bookkeeping into in place | `metadata` | RSETUP-268 |
| fallback controls snapshot | a copy of the request's own fallback lists, kept so a broken stream re-enters the chain with them | `_mid_stream_fallback_controls` | RSETUP-158, RSETUP-189 |
| priority | a whole number that sends an asynchronous chat request through a queue | `priority`, `default_priority` | RSETUP-190, RSETUP-191 |
| scheduler | the queue that holds prioritised requests until their turn | `schedule_acompletion` | RSETUP-190, RSETUP-192 |
| prompt-management model | a model group served by one deployment whose model names a logging integration | `_is_prompt_management_model` | RSETUP-187, RSETUP-188 |
| attempt | one try against one deployment; each retry or fallback hop is a new attempt | `_completion` | RSETUP-161, RSETUP-266 |
| shadow traffic | background copies of a request sent to other groups; the caller's reply never waits for them | `silent_model` | RSETUP-165, RSETUP-177, RSETUP-185, RCALL-047 |
| content-policy fallbacks | groups to try when a provider blocks a reply for its content | `content_policy_fallbacks` | RSETUP-172 |
| default fallbacks | catch-all fallback groups for any model, kept under one shared key | `default_fallbacks` | RSETUP-038 |
| environment gate | for a deployment that lists environments, the rule that loads it only on servers in one of them | `supported_environments`, `LITELLM_ENVIRONMENT` | RSETUP-202, RSETUP-207 |

## At a glance
| When | Then | Claims |
| --- | --- | --- |
| You pass a Redis host without a port | no Redis is set up at construction, so the router runs in memory until Redis is attached later | RSETUP-006, RSETUP-065 |
| A request's override is none of random shuffle, least-busy, the two usage-based strategies, latency-based or cost-based, for example `"lar1"` | a warning is logged and the model's normal strategy applies | RSETUP-100, RSETUP-101 |
| A request names a priority group itself, with no valid override | candidates are all members' deployments, team-scoped when a team id is given; the strategy is random shuffle | RSETUP-093, RSETUP-105, RSETUP-107 |
| A generic or content-policy fallback entry is not a mapping with exactly one key | construction raises a value error naming the first bad entry; context-window entries are never checked | RSETUP-131, RSETUP-132, RSETUP-133, RSETUP-134 |
| A pre-call check name is unknown or misspelled | it is ignored with no warning | RSETUP-144 |
| An asynchronous request has a truthy whole-number priority | it goes through the scheduler; a request priority of 0 counts as none, so the router's default applies | RSETUP-190, RSETUP-191 |
| A blocking request names a deployment id, not a model name, as its model | the global pre-call checks are skipped | RSETUP-168 |
| A reply is filtered; the router has content-policy fallbacks, but none for this group | the filtered reply returns, even with default fallbacks set | RSETUP-172, RSETUP-304 |
| A deployment lists environments but `LITELLM_ENVIRONMENT` is unset | the environment gate raises a value error | RSETUP-204 |
| A deployment's environment list is empty and `LITELLM_ENVIRONMENT` holds a valid value | the deployment is inactive everywhere | RSETUP-205, RSETUP-207 |

## A missing setting falls back to a global value or a built-in default
For the retry count and fallback cap, a router checks three places in turn: your value, a library-wide setting, then a built-in default [RSETUP-031], [RSETUP-032]. It reads its library-wide settings once, when it is built, so changing one later leaves an existing router alone [RSETUP-277]. Some bad settings stop the build with an error; others are stored unchecked [RSETUP-257], [RSETUP-260].

An unknown constructor keyword raises a type error, so the proxy filters its settings against the valid names first [RSETUP-292], [RSETUP-059]. An explicit retry count or fallback cap wins even when it is 0, and the built-in defaults are 2 retries and 5 fallbacks [RSETUP-031], [RSETUP-032]. Allowed failures take your argument, else the global setting, which defaults to 3 [RSETUP-026].

Three settings treat 0 as unset [RSETUP-260]. A cooldown time of 0 becomes the 5-second default, a health staleness threshold of 0 becomes 600 seconds, and a timeout of 0 becomes the global request timeout [RSETUP-260]. The global request timeout defaults to 6000 seconds unless an environment variable sets it [RSETUP-033]. No numeric setting is range-checked, so a negative timeout is stored as given [RSETUP-260]. The client time-to-live setting is stored, but nothing reads it, so it has no effect [RSETUP-276].

At construction, the router sets up Redis only when you pass a Redis URL, or both a host and a port [RSETUP-006]. The proxy can attach Redis later, and does so only when the router has none [RSETUP-065], [RSETUP-067]. The router's caches for routing state, session bindings and prompt-cache pins share that one Redis client [RSETUP-014]. With Redis, cooldowns and usage are shared with every router on the same Redis; without it, they stay in one process [RSETUP-269].

Construction raises on the first bad setting, in this order: Redis setup, the deployment list, the fallback lists, the top-level strategy, the routing groups, then the retry and allowed-fails policies [RSETUP-257]. Each generic or content-policy fallback entry must be a mapping with exactly one key [RSETUP-040], [RSETUP-132], [RSETUP-133]. Validation does not check that key's value, whether the groups exist, or duplicates [RSETUP-134].

## Three layers decide which strategy picks a deployment for a request
Each request's strategy, the rule that picks one deployment, comes from the first of three places that applies [RSETUP-105]-[RSETUP-108]. A valid strategy sent with the request wins [RSETUP-105]. Next comes a routing group: one the request names, or a non-priority group the model belongs to [RSETUP-106], [RSETUP-091]. Last comes the router's own strategy [RSETUP-108].

At construction the router validates its top-level strategy, except `"lar1"`, and builds its selector when the strategy has one [RSETUP-045], [RSETUP-071]. Five strategies get a selector: least-busy, both usage-based ones, latency-based and cost-based; random shuffle needs none [RSETUP-072]. Each routing group gets its own selector the same way [RSETUP-088]. Building groups is all-or-nothing, so a bad group leaves the previous groups in place [RSETUP-089].

The routing context resolves any alias before the group lookup [RSETUP-106]. An override other than the router's own strategy or random shuffle gets a selector, built on first use with empty settings [RSETUP-102], [RSETUP-072]. Members of a priority group are not mapped to it, so only a request that names the priority group itself, with no valid override, gets its random shuffle [RSETUP-091], [RSETUP-105], [RSETUP-107].

@figure flow id=routing-context title="How one request's strategy is chosen"
| node req | Request arrives | RSETUP-105 |
| node ovr | Valid override sent? | RSETUP-100 |
| node useovr | Use the override | RSETUP-105 |
| node named | Names a routing group? | RSETUP-106 |
| node pri | Priority group? | RSETUP-107 |
| node shuf | Use random shuffle | RSETUP-107 |
| node member | Member of a group? | RSETUP-106 |
| node usegrp | Use the group's strategy | RSETUP-106 |
| node top | Use the router's strategy | RSETUP-108 |
| req > ovr | read the request | RSETUP-100 |
| ovr > useovr | yes | RSETUP-105 |
| ovr > named | no, or ignored | RSETUP-101 |
| named > pri | yes | RSETUP-106 |
| pri > shuf | yes | RSETUP-107 |
| pri > usegrp | no | RSETUP-106 |
| named > member | no | RSETUP-106 |
| member > usegrp | yes | RSETUP-106 |
| member > top | no | RSETUP-108 |

@steps routing-context
| ovr | The request can name a rule | A request can carry its own strategy, and it wins over everything else when it is a supported strategy name [RSETUP-100], [RSETUP-105]. |
| ovr>named | Bad overrides are ignored | Any other value is ignored with a warning, so a bad value stored on a key or team never fails the request [RSETUP-101]. |
| pri>shuf | Priority groups shuffle | Without a valid override, a request that names a priority group uses random shuffle, with no selector [RSETUP-105], [RSETUP-107]. |
| member>usegrp | Group members follow their group | A model that belongs to a non-priority routing group uses that group's strategy [RSETUP-106]. |
| top | The router's rule comes last | A model in no group uses the router's own strategy [RSETUP-108]. |

## A router's callbacks live on lists every router in the process shares
Building a router adds its callbacks to the callback lists that every router in the same process shares [RSETUP-049], [RSETUP-078]. Those callbacks count usage and decide cooldowns after each provider call, through the library's logging rather than the call itself [SYS-003]. Detaching the router later removes most of them, but not all [RSETUP-062], [RSETUP-064].

Construction turns on the global setting that hides debug information, and creates a global response cache only when response caching is on and none exists [RSETUP-002], [RSETUP-012].

The default and group selectors double as logging callbacks: each joins the global callback list when that setting holds a list, and a least-busy one also joins the input list [RSETUP-078], [RSETUP-090]. A new pre-call check is dropped when the router already holds one of the same class [RSETUP-145].

Calling `discard()` removes the router from the set of live routers and strips every callback that is one of its own methods [RSETUP-062]. It also removes its recorded pre-call checks from the main callback list [RSETUP-063]. It leaves the selectors and the Slack alerting logger, which are registered as objects rather than as the router's own methods [RSETUP-064]. It also leaves the continuation-prefill check, which is never recorded among the router's pre-call checks [RSETUP-061]. A constructor that fails after registering its callbacks leaves them registered, and nothing can discard the half-built router [RSETUP-264], [RSETUP-301].

## Each chat call gets stamped, then goes to the queue or the loop
The asynchronous chat call records the request's details and bookkeeping [RSETUP-186]. In the usual case, it then sends the request to a priority queue or straight to the retry and fallback loop [RSETUP-187], [RSETUP-190]. The blocking chat call has no queue and sends no alerts [RSETUP-160].

`acompletion` writes the model, the messages, the stream setting and the per-attempt function into the request, then stamps the caller's metadata bucket in place [RSETUP-186], [RSETUP-268]. A prompt-management model goes to the prompt-management path and returns its result directly, with no snapshot, queue or duration report [RSETUP-187]. For every other model, the router stores the fallback controls snapshot, so a stream that breaks later re-enters the chain with the caller's original lists [RSETUP-189], [RSETUP-158].

The priority is the request's `priority` when truthy, else the router's `default_priority`, so a request priority of 0 counts as none [RSETUP-191]. A whole number goes through the scheduler; anything else goes straight to the retry and fallback loop [RSETUP-190]. A whole-number default breaks this path, because the scheduler call then lacks its priority and raises a type error [RSETUP-284]. On any failure, the same error is re-raised, and a background alert goes out only when Slack alerting is configured and the request did not come through the proxy [RSETUP-194], [RSETUP-195].

@figure flow id=async-entry title="What the asynchronous chat call does with one request"
| node in | Chat request arrives | RSETUP-186 |
| node stamp | Stamp request bookkeeping | RSETUP-186 |
| node pm | Prompt-management model? | RSETUP-187 |
| node pmpath | Prompt-management path | RSETUP-187 |
| node snap | Snapshot fallback lists | RSETUP-189 |
| node pr | Whole-number priority? | RSETUP-190 |
| node queue | Wait in queue | RSETUP-190 |
| node loop | Retry and fallback loop | RSETUP-190 |
| node ok | Report duration, return | RSETUP-193 |
| node err | Alert, raise same error | RSETUP-194 |
| in > stamp | write model and messages | RSETUP-186 |
| stamp > pm | check the model | RSETUP-187 |
| pm > pmpath | yes | RSETUP-187 |
| pm > snap | no | RSETUP-189 |
| snap > pr | read the priority | RSETUP-191 |
| pr > queue | yes | RSETUP-190 |
| pr > loop | no | RSETUP-190 |
| queue > in | re-enter without priority | RSETUP-192 |
| loop > ok | success | RSETUP-193 |
| loop > err | failure | RSETUP-194 |

@steps async-entry
| stamp | The request is stamped | The router writes the model and messages into the request and stamps the caller's metadata in place [RSETUP-186], [RSETUP-268]. |
| pm | Some models skip ahead | A model served by a single deployment that names a logging integration goes straight to the prompt-management path [RSETUP-187], [RSETUP-188]. |
| pr | Whole numbers wait in line | A whole-number priority on the request sends it to a queue, and a request priority of 0 counts as none [RSETUP-190], [RSETUP-191]. |
| queue>in | Queued requests come back | When its turn comes, the request re-enters the asynchronous chat call without its own priority [RSETUP-192]. |
| loop>err | Errors pass through unchanged | The caller gets the same error, and an alert goes out only when alerting is set up and the request did not come through the proxy [RSETUP-194], [RSETUP-195]. |

The blocking `completion` also skips the prompt-management path and the service-duration report, and re-raises loop errors as the same objects [RSETUP-160], [RSETUP-265].

## Each blocking attempt picks a deployment, calls the provider and checks the reply
Each blocking try picks one deployment, calls its provider and checks the reply [RSETUP-162], [RSETUP-169], [RSETUP-172]. When the provider blocked a reply for its content, a fallback group can answer instead, but only when the router's own settings allow it [RSETUP-171], [RSETUP-172].

The attempt retries nothing itself, and selection errors propagate to the loop [RSETUP-266], [RSETUP-162]. When the deployment names shadow targets, the attempt starts shadow traffic: one background thread per target, with a snapshot taken before credentials and tags are bound [RSETUP-165]. A shadow runs the router's full asynchronous path, its errors are only logged, and a shadow never launches shadows of its own [RSETUP-183], [RSETUP-184], [RSETUP-180].

The provider call merges the deployment's params, then the messages, caching setting and client, then the request's own keys, so request keys win [RSETUP-169]. A streamed reply has its first chunk read inside the attempt, so a stream that fails before that chunk raises inside the loop, where retries apply [RSETUP-174].

When a complete reply's first choice finished with `"content_filter"`, or it has no choices, the router's own settings decide whether the attempt raises a blocked-output error [RSETUP-171], [RSETUP-172]. When the router has content-policy fallbacks, they must give this group a target not yet attempted, and default fallbacks are not consulted [RSETUP-172]. Without them, only a `"*"` default fallback makes the rule raise [RSETUP-172]. Otherwise the filtered reply returns to the caller unchanged, with no error [RSETUP-172].

@figure timeline id=blocked-reply title="Example: group b's reply is blocked, and the router lists a as b's content-policy fallback"
| lane caller | Caller |
| lane b | Group b |
| lane a | Group a |
| 0s | caller | asks for group b | waiting | RSETUP-304 |
| 1s | b | reply ends with content filter | checked by the rule | RSETUP-172, RSETUP-304 |
| 1s | b | b's list names untried a | blocked-output error raised | RSETUP-171, RSETUP-304 |
| 2s | a | loop sends request to a | answers normally | RSETUP-304 |
| 2s | caller | gets a's reply | one fallback attempted | RSETUP-304 |

## Watch out
- A default queue priority set to any whole number, even 0, makes every asynchronous chat call fail, including calls that send no priority; each caller gets an error about a missing argument [RSETUP-297], [RSETUP-284].
- Detaching a router leaves its selectors and Slack alerting on the shared lists [RSETUP-298]. The proxy does this for every request with its own router settings, so those lists keep growing and every later logging event visits them [RSETUP-298].
- With default fallbacks set, building a router appends a catch-all entry to your fallback list, or to the library-wide one on every build [RSETUP-038], [RSETUP-299]. Any non-empty default parameters you pass are also changed in place [RSETUP-043].
- Content-policy fallbacks sent with a single request never make the router act on a blocked reply by themselves; the router's own content-policy fallbacks or a catch-all default must trigger it [RSETUP-307], [RSETUP-303]. Otherwise the caller gets the blocked reply back [RSETUP-303].
- Switching a latency-based router to least-busy through the strategy setup step, not the settings update, makes every later chat call on ungrouped models fail with an error saying no deployments are available [RSETUP-306].
- Printing a deployment masks only the API key unless redaction is on, so other cloud secrets appear in clear text in an informational log line [RSETUP-150], [RSETUP-151].
- Turning off the prompt-caching, model rate-limit or encrypted-content check on one router can silently remove it for another router in the same process that was built without a deployment list [RSETUP-309].
