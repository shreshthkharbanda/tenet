---
module: router-selection
---
# The router turns a model name into candidates, filters them, then picks one

@plain
A company can run one AI model in several places, called deployments, that share one public model name [RSELECT-001]. For each request, this part of the router finds every deployment that could serve that name [RSELECT-020]. Filters can then drop deployments that are unhealthy, resting after recent errors, paused, or reserved for another team [RSELECT-024], [RSELECT-043], [RSELECT-044], [RSELECT-046]. By default the router picks one of the rest at random [RSELECT-067], [RSELECT-139]. When the filters leave none, the caller usually gets an error with status 429, which here means no deployment could take the request [RSELECT-054], [RSELECT-283]. On the full path, the router also writes this failure to its info log [RSELECT-054]. One wrong setting can fail every request for a model [RSELECT-279].

@minute
An asynchronous call runs the full path only when the router-wide strategy is one of the five full-path strategies [RSELECT-060]. A routing group's or request's own strategy does not count, and synchronous calls always take the reduced path [RSELECT-060], [RSELECT-121]. The full path starts with the pre-routing hook, where a strategy router can move the request to one of its tiers [RSELECT-061]. Common resolution then turns the name into candidates, and a fixed sequence of filters narrows them [RSELECT-020], [RSELECT-040]. The strategy picks one survivor [RSELECT-067], [RSELECT-068]. An empty list raises `RouterRateLimitError` with status 429 [RSELECT-054].

## Words you'll see
| Term | Means | In the code | Claims |
| --- | --- | --- | --- |
| model group | the public model name a request asks for; several deployments can share it | `model_name` | RSELECT-001 |
| deployment | one place a model runs, with its own provider model, credentials and limits | `model_list`, `litellm_params`, `model_info` | RSELECT-001, RSELECT-203, RSELECT-289 |
| asynchronous call | a request through the router's asynchronous methods, such as its async chat call; it starts at the async entry point | `acompletion`, `async_get_available_deployment` | RCALL-045, RSELECT-060 |
| synchronous call | a request whose selection runs synchronously, such as sync image generation; it always takes the reduced path | `get_available_deployment` | RCALL-106, RSELECT-121 |
| full path | the whole selection: pre-routing hook, name lookup, every filter, then the pick | `async_get_healthy_deployments` | RSELECT-040, RSELECT-061 |
| reduced path | selection without the pre-routing hook, team and web-search filters, callback checks or tag routing, which a router with routing plugins refuses | `_get_available_deployment_unresolved` | RSELECT-060, RSELECT-128, RSELECT-120 |
| router-wide strategy | the strategy setting of the whole router; it alone decides between the full and reduced paths, while a routing group's or request's own strategy changes only the final pick | `routing_strategy` | RSELECT-060, RSELECT-063, RSELECT-278 |
| five full-path strategies | simple-shuffle (the default), least-busy, latency-based-routing, cost-based-routing and usage-based-routing-v2 | `simple-shuffle`, `least-busy`, `latency-based-routing`, `cost-based-routing`, `usage-based-routing-v2` | RSELECT-060, RSELECT-139 |
| other strategy names | the three other accepted names, usage-based-routing, lar1 and provider-budget-routing; any other name is rejected | `usage-based-routing`, `lar1`, `provider-budget-routing` | CONTRACTS-116, RSELECT-060, RSELECT-159 |
| routing group | a named set of model groups sharing one strategy; a request can name the group itself unless a model or alias already uses that name | `routing_groups` | RSETUP-091, RSETUP-092, RSETUP-093 |
| pre-routing hook | the first step of the full path, where a strategy router can move the request to one of its tiers | `async_pre_routing_hook` | RSELECT-092, RSELECT-098 |
| strategy router | an entry under a model name that never calls a provider; it sends the request to one of its tiers, other model names, chosen by its own logic | `auto_router/`, `auto_routers`, `complexity_routers`, `adaptive_routers`, `quality_routers` | RSELECT-015, RSELECT-016, RSELECT-098, RSELECT-105 |
| tag filtering | a switch, for the router or for one request, that lets request tags narrow which deployments serve it | `enable_tag_filtering`, `tag_filtering_match_any` | RSELECT-049, RSELECT-108 |
| tier params | settings a strategy router pins for its chosen tier, such as an output-token limit or a reasoning effort | `TIER_PARAMS_NEVER_DROPPED`, `allowed_openai_params` | RSELECT-031, RSELECT-034, RSELECT-037 |
| session binding | for Claude Code command-line traffic only: a one-hour link, renewed on use, that sends a session's child-agent requests through the strategy router its main requests used | `x-claude-code-session-id`, `x-claude-code-agent-id`, `fallback_depth` | RSELECT-110, RSELECT-115, RSELECT-116 |
| common resolution | the name lookup that turns the requested name into candidates | `_common_checks_available_deployment` | RSELECT-020 |
| specific-deployment request | a request option that matches deployments by provider model string, such as openai/gpt-4o, instead of by model name | `specific_deployment` | RSELECT-021, RSELECT-042 |
| provider model | the provider's own model string that a deployment calls, such as openai/gpt-4o | `litellm_params.model` | RSELECT-017, RSELECT-042 |
| deployment id | the unique name of one deployment, such as dep-0 | `model_info.id` | RSELECT-140, RSELECT-042 |
| alias | a second name that points at a model group, followed one hop | `model_group_alias` | RSELECT-011 |
| wildcard route | a deployment registered under a name pattern, such as openai/*-mini, that serves any name the pattern matches from its start | `wildcard_route_deployments` | RSELECT-003, TARGETS-007 |
| team filter | usually keeps deployments with no owner team plus the caller's team's; an admin without a team reaches one team's deployments, but a name two teams share is refused | `model_info.team_id` | TARGETS-100, TARGETS-103, TARGETS-104, RSELECT-041 |
| web-search filter | for a request that asks for a web-search tool, keeps deployments not marked as lacking web search | `supports_web_search` | TARGETS-106, TARGETS-107, RSELECT-041 |
| access-group filter | the lookup step that checks the caller's key against access groups and can narrow the candidates to deployments in groups the key allows | `access_groups` | RSELECT-030 |
| reservation filter | drops strategy routers, then deployments that an access window or a provisioned-throughput share keeps for other teams | `_filter_reserved_deployments` | RSELECT-024 |
| access window | daily hours, in a set timezone, when a deployment serves only listed teams | `ModelAccessWindow` | LIMITS-003, LIMITS-008 |
| provisioned-throughput share | a team's slice of a shared provisioned deployment; a team holding one uses only its shared deployments, and teams without one are kept off them | `filter_ptu_shared_deployments` | RSELECT-025, LIMITS-022 |
| generic fallback list | the fallbacks entry under a literal star key; lookup uses its first name for an unmatched name, and the list can also be the chain after a failed call | `fallbacks`, `default_fallbacks`, `"*"` | RSELECT-028, RDISP-111 |
| health-check routing | a switch that lets background health checks remove unhealthy deployments | `enable_health_check_routing`, `health_check_probe` | RSELECT-142, RSELECT-145 |
| allowed-failures policy | per-error-type counts of failures a deployment may have before it cools down | `allowed_fails_policy` | RSELECT-171, FAILURE-047 |
| cooldown | a pause after recent errors during which selection skips a deployment, 5 seconds unless the router sets another length; the failure-handling chapter covers it | `deployment:<id>:cooldown`, `cooldown_time` | FAILURE-001, RSELECT-282 |
| paused deployment | a deployment whose blocked setting is the value true itself; the text "true" does not count | `model_info.blocked` | RSELECT-141 |
| callback checks | optional extra filters, such as rate limits, affinity, prompt caching and stream continuation | `async_filter_deployments` | RSELECT-047 |
| affinity | keeping a caller, a session or an earlier response on the deployment that already served it | `DeploymentAffinityCheck` | AFFINITY-001, AFFINITY-002 |
| pre-call checks | the router's own tests of each deployment's context window, per-minute request count and region, plus one request setting | `enable_pre_call_checks` | RSELECT-048, RSELECT-202, RSELECT-203, RSELECT-204, RSELECT-205 |
| structured-output setting | the request's response format, the only request setting that pre-call checks test for provider support | `response_format` | RSELECT-205 |
| routing plugins | configured functions that can narrow which provider models may serve a request | `plugins`, `_routing_plugin_candidate_models` | RSELECT-085, RSELECT-087 |
| order | a deployment's priority number; selection keeps the lowest number present, and a higher number serves when the request names that level, as an order fallback does | `order`, `_target_order` | RSELECT-051, RDISP-104 |
| exclusion lists | deployment ids that failover or a retry asks selection to skip | `_excluded_deployment_ids`, `_retry_skipped_deployment_ids` | RSELECT-052, RSELECT-053 |
| no-deployment error | the error raised when no candidate survives; it uses status 429 (too many requests), which here means no deployment could take the request | `RouterRateLimitError` | RSELECT-054, RSELECT-283 |
| selection errors | the other errors: 400 for a bad name or a reservation, 503 for a paused deployment asked for by id, and errors when pre-call checks or routing plugins leave none | `BadRequestError`, `ServiceUnavailableError`, `ValueError`, `UnsupportedParamsError`, `RouterRateLimitErrorBasic`, `ContextWindowExceededError` | RSELECT-288, RSELECT-024, RSELECT-042, RSELECT-089, RSELECT-208, RSELECT-209, RSELECT-210 |
| pass-through flag | marks a deployment that may serve pass-through endpoints, which use only marked deployments | `use_in_pass_through` | RSELECT-131, RSELECT-132, RSELECT-135 |
| selection trace | the trace span an asynchronous selection runs in, named route followed by the requested model | `route <model>` | RSELECT-072 |
| failure handlers | the request's logging handlers, which receive a full-path selection error when the request carries a logging object | `litellm_logging_obj` | RSELECT-071 |
| settings update | the call that changes router settings while the router runs, and its companion that reads them; the next request uses a change | `update_settings`, `get_settings` | RSELECT-152, RSELECT-252, RSELECT-150 |
| cache flush | a router call, also run by the router's reset call, that empties its caches; it is not a setting | `flush_cache`, `FLUSHALL`, `reset` | RSELECT-183, RSELECT-184 |

## At a glance
| When | Then | Claims |
| --- | --- | --- |
| Several deployments survive under the default `simple-shuffle` | a random pick, weighted by weight, rpm or tpm when set, else uniform | RSELECT-067, RSELECT-139 |
| The filters leave nothing | `RouterRateLimitError` (429); the all-in-cooldown sentence appears only when every deployment id of the group is cooling | RSELECT-054, RSELECT-283 |
| The cooldown filter empties the list, health-check routing is on and `allowed_fails_policy` is set | a warning, and the resting deployments stay candidates | RSELECT-045 |
| The name is a deployment id, not a model name | that deployment after the reservation filter, with no health, cooldown, pre-call or tag filtering; if paused, `ServiceUnavailableError` (503) | RSELECT-022, RSELECT-042 |
| A model group's only deployment is paused | the paused filter empties the list, so `RouterRateLimitError` (429), never the 503 | RSELECT-042, RSELECT-046 |
| Nothing matches, access groups emptied nothing, and a `"*"` list in `fallbacks` is non-empty | its first name serves the request, if that name resolves as a registered name | RSELECT-028, RSELECT-287 |
| Nothing matches and no substitute resolves | `BadRequestError` (400) with an empty provider, naming the substitute if one was tried, else the requested name after its alias hop; configured fallbacks can still run | RSELECT-288, FAILURE-113, RDISP-101 |
| The router-wide strategy is not one of the five full-path strategies | an asynchronous call takes the reduced path | RSELECT-060, RSELECT-128 |
| Routing plugins are configured and the call reaches the reduced path, or plugins narrow the list to nothing | `ValueError`; plugin narrowing never falls back to the unfiltered pool | RSELECT-120, RSELECT-089 |
| Pre-call checks exclude every candidate, none for context window, and every group deployment would reject a non-string `response_format` sent while global drop-params is exactly off | `UnsupportedParamsError` (400) | RSELECT-205, RSELECT-208 |
| Pre-call checks exclude every candidate, the row above does not apply, and one went for its rpm, which never happens under a router-wide `usage-based-routing-v2` | `RouterRateLimitErrorBasic` (429), even if others failed on context window | RSELECT-209, RSELECT-251 |
| Pre-call checks exclude every candidate, some for context window and none for rpm | `ContextWindowExceededError` | RSELECT-210 |
| Async pass-through selection ends with no deployment that sets `use_in_pass_through` | `BadRequestError`, even when only cooldown or health filters removed them | RSELECT-132 |

## The router-wide strategy decides whether a request takes the full path
Selection has a full path and a reduced path that skips several checks [RSELECT-060], [RSELECT-128]. An asynchronous call takes the full path only when the router-wide strategy is one of the five full-path strategies, and a synchronous call always takes the reduced path [RSELECT-060], [RSELECT-121].

@figure flow id=path-choice title="Which selection path a request takes"
| node kind | Asynchronous call? | RCALL-045, RSELECT-121 |
| node strat | Five full-path strategies? | RSELECT-060 |
| node full | Full path | RSELECT-040, RSELECT-061 |
| node plug | Routing plugins configured? | RSELECT-120 |
| node reduced | Reduced path | RSELECT-121, RSELECT-128 |
| node refuse | Error before any lookup | RSELECT-120 |
| kind > strat | yes | RSELECT-060 |
| kind > plug | no, synchronous | RSELECT-121 |
| strat > full | yes | RSELECT-060 |
| strat > plug | no | RSELECT-060 |
| plug > refuse | yes | RSELECT-120 |
| plug > reduced | no | RSELECT-121 |

@steps path-choice
| kind | The calling method decides first | An asynchronous call, such as the async chat call, starts at the full-path check [RCALL-045], [RSELECT-060]. Asynchronous pass-through selection skips this check and always runs the pre-routing hook [RSELECT-130]. Synchronous selection, such as sync image generation, always takes the reduced path [RCALL-106], [RSELECT-121]. |
| strat | Five strategies keep the full path | They are simple-shuffle, the default, plus least-busy, latency-based-routing, cost-based-routing and usage-based-routing-v2 [RSELECT-060], [RSELECT-139]. The other accepted names, usage-based-routing, lar1 and provider-budget-routing, take the reduced path [RSELECT-060], [CONTRACTS-116]. |
| strat>plug | A group's own strategy does not count | Only the router-wide strategy counts here [RSELECT-060]. A routing group or one request can name its own strategy, which changes only how the final pick is made [RSELECT-063], [RSELECT-278]. |
| reduced | What the reduced path skips | It skips the pre-routing hook, the team and web-search filters, callback checks and tag routing [RSELECT-128]. It never runs routing plugins, so on a router that has them every reduced-path call fails before any lookup [RSELECT-128], [RSELECT-120]. |
| refuse | Plugins refuse the reduced path | A router with routing plugins fails the call before any lookup rather than skip its plugins [RSELECT-120]. |

The check compares only the router-wide `routing_strategy` with the five full-path strategies [RSELECT-060]. With routing plugins configured, the reduced path raises `ValueError`, even for an asynchronous call handed down to it [RSELECT-120].

## A strategy router can send the request to another model before lookup
Some model names belong to a strategy router, which never calls a provider itself [RSELECT-015], [RSELECT-016]. On the full path, the router first lets that strategy router move the request to one of its tiers, another model name [RSELECT-061].

@figure flow id=strategy-choice title="How the hook chooses a strategy router for a name"
| node look | Gather strategy routers | RSELECT-105 |
| node tags | Request tags match one? | RSELECT-106 |
| node dflt | A router tagged default? | RSELECT-107 |
| node filt | Tag filtering on? | RSELECT-108 |
| node tagd | Every router has tags? | RSELECT-108 |
| node plain | Ordinary deployments too? | RSELECT-108 |
| node first | First router takes it | RSELECT-109 |
| node take | That router takes it | RSELECT-106, RSELECT-107 |
| node chosen | Router's logic picks a tier | RSELECT-061, RSELECT-098 |
| node none | Ordinary deployment selection | RSELECT-093 |
| look > none | none registered | RSELECT-105 |
| look > tags | some found | RSELECT-105 |
| tags > take | yes | RSELECT-106 |
| tags > dflt | no | RSELECT-107 |
| dflt > take | yes | RSELECT-107 |
| dflt > filt | no | RSELECT-108 |
| filt > tagd | yes | RSELECT-108 |
| filt > first | no | RSELECT-109 |
| tagd > plain | yes | RSELECT-108 |
| tagd > first | no | RSELECT-109 |
| plain > none | yes | RSELECT-108 |
| plain > first | no | RSELECT-109 |
| take > chosen | its own logic | RSELECT-098 |
| first > chosen | its own logic | RSELECT-098 |

@steps strategy-choice
| look | Gather the strategy routers | The hook collects the strategy routers under the name from four kinds, in order: auto, complexity, adaptive and quality routers [RSELECT-105]. With none registered, no strategy router runs [RSELECT-105]. |
| tags | Tags choose the router, not the tier | A request with tags goes to the first strategy router whose tags match its own [RSELECT-106]. That router's own logic then picks the tier [RSELECT-098], [RSELECT-061]. |
| dflt | Then the default tag | Otherwise the first strategy router tagged default takes the request [RSELECT-107]. |
| plain>none | Ordinary deployments keep unmatched traffic | Suppose no router matched so far, tag filtering is on, every strategy router under the name has tags, and the name also has ordinary deployments [RSELECT-108]. Then the request skips the strategy routers and goes to the ordinary deployments [RSELECT-108]. |
| first | Otherwise the first router | Otherwise the first strategy router under the name takes the request [RSELECT-109]. So when one strategy router under the name has no tags, or the name has no ordinary deployments, requests that no tag rule placed still go to a strategy router [RSELECT-109]. |
| chosen | The tier replaces the request | The chosen router's answer replaces the requested model and messages for the rest of selection, and the caller's own messages stay unchanged [RSELECT-061], [RSELECT-076]. |

A strategy router is a marker deployment whose provider model starts with `auto_router/` [RSELECT-015]. The pre-routing hook clears the previous attempt's routing decision, follows one alias hop, applies the session binding, runs any routing plugins, then chooses a strategy router [RSELECT-092]. With none chosen, it returns no response and selection goes on with the requested name [RSELECT-093].

The answer can carry tier params, such as an output-token limit or a reasoning effort, which overwrite same-named request settings [RSELECT-035], [RSELECT-034], [RSELECT-037]. Only provider-rejectable params outside the never-dropped set and any `allowed_openai_params` list can be dropped [RSELECT-031]. The router drops one only when no deployment of the target group accepts it, and an empty target group drops nothing [RSELECT-032], [RSELECT-033].

The session binding needs a `x-claude-code-session-id` header of at least 8 letters, digits, underscores or hyphens, plus an API key hash [RSELECT-110]. A request without `x-claude-code-agent-id` whose name selects a strategy binds the session to that name for 3600 seconds [RSELECT-116]. Requests with the agent id header then route through the bound router while it still selects a strategy for the caller, renewing the binding; otherwise the router deletes it [RSELECT-113]-[RSELECT-115]. Fallback hops, with `fallback_depth` set to anything but 0, skip the binding [RSELECT-112].

## The router resolves the requested name into a list of candidates
The router looks up the requested name by fixed rules and stops at the first rule that matches [RSELECT-020]. A generic fallback list can still serve a name that matches nothing [RSELECT-028].

@figure flow id=resolve-name title="How the router turns a requested name into candidates"
| node spec | Specific-deployment request? | RSELECT-021 |
| node byid | A deployment id? | RSELECT-022 |
| node alias | Follow one alias hop | RSELECT-011 |
| node group | A routing group? | RSELECT-026 |
| node early | Unknown name: team, wildcard | RSELECT-018 |
| node reg | Team's deployments, filtered | RSELECT-027 |
| node exact | Provider model string match | RSELECT-017 |
| node star | Generic fallback list? | RSELECT-028 |
| node done | Candidate list | RSELECT-029 |
| node fail | Bad request, status 400 | RSELECT-288 |
| spec > done | yes: provider model match | RSELECT-021 |
| spec > byid | no | RSELECT-020 |
| byid > done | yes: one deployment | RSELECT-022 |
| byid > alias | no | RSELECT-020 |
| alias > group | name may change | RSELECT-020 |
| group > done | yes: members' deployments | RSELECT-026 |
| group > early | no, unknown name | RSELECT-018 |
| group > reg | no, known name | RSELECT-027 |
| early > done | found | RSELECT-026 |
| early > reg | nothing found | RSELECT-020 |
| reg > done | candidates remain | RSELECT-027 |
| reg > exact | none for this team | RSELECT-027 |
| reg > fail | access groups emptied it | RSELECT-287 |
| exact > done | match found | RSELECT-017 |
| exact > star | still nothing | RSELECT-028 |
| star > done | substitute resolves | RSELECT-287 |
| star > fail | none, or it fails | RSELECT-288 |

@steps resolve-name
| spec | A specific-deployment request | A request option can ask for deployments by provider model string, such as openai/gpt-4o, instead of by model name [RSELECT-021], [RSELECT-042]. The matches still pass the reservation filter, and an empty match is not an error during the lookup itself [RSELECT-021]. |
| byid>done | A deployment id | A name that is a deployment id, not a model name, returns that one deployment after the reservation filter [RSELECT-022]. From then on the router names it by its provider model, so an error about paused dep-0 names openai/gpt-4o [RSELECT-040], [RSELECT-042]. |
| alias | One alias hop | An alias renames the request exactly once [RSELECT-011]. |
| group | Routing groups | A request that names a routing group gets every member's deployments as candidates [RSELECT-026], [RSETUP-093]. |
| early | Unknown names | A name the router does not know tries the caller team's deployments under that name, or every team's for an admin without a team, then wildcard routes [RSELECT-018]. |
| reg>exact | Nothing under the name | When the caller's team has no deployment under the name, the router looks for deployments whose provider model string equals the name [RSELECT-027], [RSELECT-017]. |
| reg>fail | Access groups end the lookup | When the access-group filter empties the list, neither the provider-model match nor the generic fallback list runs, and the lookup fails with status 400 [RSELECT-027], [RSELECT-287], [RSELECT-288]. That error names no provider, so the configured fallbacks can still serve the request afterwards [FAILURE-113], [RDISP-101], [RDISP-111]. |
| star | The generic fallback list | For a name that matches nothing, the lookup uses the first name of the first non-empty list under the star key, if that name is registered [RSELECT-028], [RSELECT-287]. |

Common resolution uses the name exactly as given, with no trimming, case folding or provider-prefix normalisation [RSELECT-220]. The access-group filter acts only when the caller's key lists allowed models that include one of the name's access groups but not the name itself, `"*"` or `"all-proxy-models"` [RSELECT-030]. The reservation filter drops strategy routers, applies access windows at the current UTC time, then provisioned-throughput shares [RSELECT-024]. Each raises `BadRequestError` when it withholds deployments and none survive, for example “Deployment gpt-4o is reserved for another team until 17:00 Europe/Berlin” [RSELECT-024].

A substitute from `fallbacks` resolves only as a registered name, never as an alias, routing group or wildcard route, and substitution never runs after an earlier rule returned [RSELECT-287]. When nothing remains, resolution raises `BadRequestError` (400) with an empty provider, naming the substitute if one was tried, else the requested name after its alias hop [RSELECT-288]. Because the error names no provider, the fallback dispatcher does not stop at it and can still walk the model's fallbacks [FAILURE-113], [RDISP-101].

## The router narrows the candidates through filters in a fixed order
After the lookup, a fixed chain of filters removes deployments that should not serve this request [RSELECT-040]. Filters never reorder deployments; only the final pick adds randomness or ranking [RSELECT-260].

@figure flow id=filter-pipeline title="The order in which filters narrow the candidates"
| node res | Resolve the name | RSELECT-040 |
| node team | Team and web search | RSELECT-041 |
| node direct | Return that one deployment | RSELECT-042 |
| node health | Health checks | RSELECT-043 |
| node cool | Cooldowns | RSELECT-044 |
| node paused | Paused deployments | RSELECT-046 |
| node cb | Callback checks | RSELECT-047 |
| node pre | Pre-call checks | RSELECT-048 |
| node tag | Tags, then plugins | RSELECT-049, RSELECT-050 |
| node ord | Order and exclusion lists | RSELECT-051, RSELECT-052, RSELECT-053 |
| node pick | Strategy picks one | RSELECT-067, RSELECT-068 |
| node err | No-deployment error | RSELECT-054 |
| res > team | candidates | RSELECT-041 |
| team > direct | asked for by id | RSELECT-042 |
| team > health | a list | RSELECT-043 |
| health > cool | survivors | RSELECT-043 |
| cool > paused | survivors | RSELECT-046 |
| paused > cb | survivors | RSELECT-047 |
| cb > pre | survivors | RSELECT-048 |
| pre > tag | survivors | RSELECT-049 |
| tag > ord | survivors | RSELECT-051 |
| ord > pick | something left | RSELECT-067 |
| ord > err | nothing left | RSELECT-054 |

@steps filter-pipeline
| res | Resolution comes first | The name that resolution returns replaces the requested name for every later step and error [RSELECT-040]. |
| team | Team and web search | The team filter usually keeps deployments with no owner team plus the caller team's own [RSELECT-041], [TARGETS-100]. The web-search filter, for a request that asks for a web-search tool, keeps deployments not marked as lacking web search [RSELECT-041], [TARGETS-106], [TARGETS-107]. |
| team>direct | Only a deployment asked for by id skips the rest | A deployment asked for by id, or the default deployment, returns right after these two filters, or fails with a 503 (service unavailable) error when paused [RSELECT-042]. A model group with one deployment still goes through every filter, so its paused deployment ends in the 429 instead [RSELECT-042]. |
| health | Health before cooldown | Health checks remove unhealthy deployments only when health-check routing is on, and they run before cooldowns [RSELECT-043], [RSELECT-142]. |
| cool | Resting deployments drop out | The cooldown filter removes deployments resting after recent errors [RSELECT-044]. If that empties the list while health-check routing and an allowed-failures policy are both set, the router logs a warning and keeps the resting deployments [RSELECT-045]. |
| cb | Callback checks | Optional extra checks follow, such as rate limits, affinity, prompt caching and stream continuation [RSELECT-047]. |
| pre | Pre-call checks need a switch | These checks run only when the router has them switched on and the request has messages or input [RSELECT-048]. |
| ord>err | Nothing left | An empty list ends in the no-deployment error, status 429 (too many requests), which here means no deployment could take the request [RSELECT-054], [RSELECT-283]. |

The 503 is `ServiceUnavailableError`, naming the provider model, not the id [RSELECT-042]. Health checks also do nothing when `allowed_fails_policy` is set without background health-check groups [RSELECT-142]. If every candidate is unhealthy, the full path keeps the whole list, but for a health-check probe the filter returns an empty list, and the call then ends in the no-deployment error [RSELECT-145], [RSELECT-054].

The paused filter counts only `model_info.blocked` equal to the value true, so the string `"true"` does not count [RSELECT-141]. Pre-call checks need `enable_pre_call_checks` on and messages or input in the request [RSELECT-048]. They exclude a deployment over its context window, at its per-minute request limit, or outside the requested region [RSELECT-202]-[RSELECT-204]. The per-minute check reads only this process's in-memory counts and skips entirely under a router-wide `usage-based-routing-v2` [RSELECT-203], [RSELECT-232], [RSELECT-251].

The order filter keeps the requested `_target_order`, or else the lowest declared `order`, or everything when no deployment declares one [RSELECT-051]. The router then removes the failover exclusion list even if that empties the list, but removes the retry skip list only when something would remain [RSELECT-052], [RSELECT-053].

## One strategy picks a survivor, or the caller gets a no-deployment error
When deployments survive, a strategy picks one, by default at random [RSELECT-067], [RSELECT-139]. When none survives, the caller usually gets a 429 error that names a wait time [RSELECT-054], [RSELECT-283].

@figure timeline id=both-cool title="Example: both deployments of gpt-4o rest, and a request finds none"
| lane d0 | Deployment dep-0 |
| lane d1 | Deployment dep-1 |
| lane req | Requests for gpt-4o |
| 0s | d0 | starts a 60-second cooldown | resting | RSELECT-054 |
| 10s | req | resolution finds both deployments | two candidates | RSELECT-020 |
| 10s | req | cooldown filter drops dep-0 | one candidate | RSELECT-044 |
| 10s | d1 | the shuffle picks it | serving | RSELECT-067 |
| 20s | d1 | starts a 60-second cooldown | resting | RSELECT-054 |
| 30s | req | cooldown filter drops both | empty list | RSELECT-044, RSELECT-045 |
| 30s | req | error says retry in 60 seconds | 429, all in cooldown | RSELECT-283 |
| 60s | d0 | cooldown length passes | serving again | FAILURE-012 |
| 80s | d1 | cooldown length passes | serving again | FAILURE-012 |

Under `simple-shuffle` the pick is weighted random by each deployment's weight, rpm or tpm when set, else uniform [RSELECT-067]. Other strategies ask their selector, and a missing selector or an empty answer raises the no-deployment error [RSELECT-068]. A per-request strategy override that differs from the router-wide strategy adds one last check on every pick except a shuffle pick [RSELECT-284].

The no-deployment error is `RouterRateLimitError`, a `ValueError` subclass with status 429 [RSELECT-054]. Its message says no deployment is available for the model and gives a wait: the smallest configured cooldown length among the group's deployments, not the time remaining [RSELECT-283]. With no cooldown entry, or a smallest length of 0, the wait is the cooldown default fixed when the router was built, 5 seconds unless set [RSELECT-283], [RSELECT-282]. In the example each cooldown lasts 60 seconds, so the error at the 30s mark says 60 although dep-0 is halfway through its cooldown [RSELECT-283]. The message adds that all deployments are in cooldown only when every deployment id of the group is cooling, as here [RSELECT-283].

On the full path, the failure handlers receive the error when the request carries a logging object [RSELECT-071]. The whole asynchronous selection runs inside the selection trace `route <model>` [RSELECT-072].

## Some settings change while the router runs, and the next call uses them
The settings update changes some router settings while the router runs, and the next request uses them [RSELECT-252]. Other settings keep the values the router was built with, and the update leaves only a debug log line [RSELECT-152], [RSELECT-252].

@figure flow id=settings-update title="What the settings update does with each key it receives"
| node key | Key on the allowed list? | RSELECT-152 |
| node ignore | Ignored, debug log only | RSELECT-152 |
| node num | Whole-number setting? | RSELECT-153 |
| node cut | Cut to a whole number | RSELECT-153 |
| node apply | Applied in the given order | RSELECT-153 |
| node strat | Strategy name changed? | RSELECT-158 |
| node rebuild | Strategy rebuilt | RSELECT-158, RSELECT-159 |
| node next | Next request uses it | RSELECT-252 |
| key > ignore | no | RSELECT-152 |
| key > num | yes | RSELECT-152 |
| num > cut | yes | RSELECT-153 |
| num > apply | no | RSELECT-153 |
| cut > apply | converted | RSELECT-153 |
| apply > strat | applied | RSELECT-158 |
| strat > rebuild | yes | RSELECT-158 |
| strat > next | no | RSELECT-252 |
| rebuild > next | rebuilt | RSELECT-252 |

@steps settings-update
| key | Which keys count | The update applies the strategy and its settings, routing groups, aliases, fallback lists, retry counts, retry wait and retry policies, allowed failures, timeouts and cooldown time [RSELECT-152]. It also applies weighted failover, stream continuation, tag filtering and its prefix, optional checks and unsupported-parameter fallbacks [RSELECT-152]. |
| key>ignore | Everything else is ignored | Any other key is dropped with only a debug log line, including pre-call checks, health-check routing, the allowed-failures policy, background health-check groups, tag match-any, routing plugins and default fallbacks [RSELECT-152], [RSELECT-252]. Those change only when code sets the router's own value or a new router is built [RSELECT-252]. |
| num>cut | Whole numbers only | Timeout, retry count, retry wait, allowed failures and cooldown time become whole numbers, so 2.9 becomes 2 and a timeout of 0.5 becomes 0 [RSELECT-153]. |
| apply | No rollback | Keys apply one at a time in the order given, so a bad value stops the update after the earlier keys took effect [RSELECT-153]. |
| strat>rebuild | A new strategy rebuilds | A different strategy name rebuilds the strategy, and an unknown name fails before the setting changes [RSELECT-158], [RSELECT-159]. |

The settings update is `update_settings` [RSELECT-152]. `get_settings` returns live attribute values, not copies, with two exceptions [RSELECT-150]. Latency-based routing args come back as a new dict with defaults filled in, and routing groups as a list of dicts [RSELECT-151]. The cache flush, `flush_cache`, is a router method that `reset` also runs, not a setting [RSELECT-183], [RSELECT-184]. With Redis attached it issues `FLUSHALL`, which erases every key on that Redis server [RSELECT-183], [RSELECT-274].

## Watch out
- Asking for a deployment by its id skips health checks, cooldowns and pre-call checks, so a deployment resting after errors still gets the request [RSELECT-042]. An access window or a provisioned-throughput share still applies, and a paused deployment still gives a 503 [RSELECT-022], [RSELECT-042].
- Only the router-wide strategy decides the path [RSELECT-060]. Under one such as usage-based-routing, asynchronous calls skip the strategy routers, team filter, affinity and rate-limit checks, whatever strategy its routing group names [RSELECT-278], [RSELECT-128].
- The strategy name provider-budget-routing passes validation but sets up no way to choose a deployment, which looks like a defect [RSELECT-279]. For a model outside any routing group every request then fails, even with one deployment; only a request by deployment id still works [RSELECT-279].
- Flushing the router's cache erases every key on its shared Redis server, including other applications' data [RSELECT-274], [RSELECT-183].
- The wait in the no-deployment error is the configured cooldown length, not the time left [RSELECT-283]. When no deployment of the group has a cooldown entry, as when all are paused, the error shows the build-time cooldown default, even after the cooldown time was changed [RSELECT-283], [RSELECT-282].
- Setting the router-wide timeout to 0.5 seconds through the settings update stores 0, which calls then skip as unset, so the half-second limit is lost [RSELECT-153], [RSELECT-275], [RCALL-083].
- A routing plugin's narrowed list of provider models stays on the request [RSELECT-276]. So a fallback to another model whose own plugin pass narrows nothing can fail with no deployments left after routing-plugin filtering [RSELECT-276], [RSELECT-089].
- When filters leave no deployment, the full path writes an info log line, and the reduced path writes none [RSELECT-054], [RSELECT-126]. The reduced path calls no failure handlers [RSELECT-128]. An asynchronous call handed to it still runs inside the selection trace; a synchronous call gets no trace from selection [RSELECT-072], [RSELECT-128]. On every path the error reaches the caller's retry and fallback loop, which logs an error line when a fallback walk fails [RSELECT-225], [RDISP-114].
