---
module: routing-contracts
---
# One set of shared rules judges routing setups, so router and proxy agree

@plain
Someone has to describe the router's setup of AI models [CONTRACTS-013] [CONTRACTS-120]. It says which models exist, how they are grouped, and which auto-routers pick a model for each request [CONTRACTS-013] [CONTRACTS-120]. The router, the setup-file loader and the admin requests that add models all ask this part of the system, a shared rulebook, so they agree [CONTRACTS-001] [CONTRACTS-008] [CONTRACTS-010]. Many auto-router mistakes get a plain message saying how to fix them [CONTRACTS-023] [CONTRACTS-025] [CONTRACTS-036]. The rulebook also counts licensed features against a limit [CONTRACTS-063]. It works out which effort levels each model accepts [CONTRACTS-109]. When it goes wrong, an admin sees a change refused, or the proxy will not start [CONTRACTS-008] [CONTRACTS-006]. Or a model shows no effort levels although its operator listed some [CONTRACTS-156].

@minute
The Router, the proxy's config loader and its admin endpoints all call these pure rules, so each answers the same way [CONTRACTS-001] [CONTRACTS-008] [CONTRACTS-010]. The rules classify `auto_router/` names, check required settings, and count licensed features and changed scoring rules against caller-supplied limits [CONTRACTS-015] [CONTRACTS-027] [CONTRACTS-063] [CONTRACTS-083]. They also validate routing groups, capture caller settings for baseline requests, and resolve reasoning effort levels [CONTRACTS-120] [CONTRACTS-090] [CONTRACTS-109]. Most return a violation message instead of raising; the routing-group and strategy checks raise [CONTRACTS-023] [CONTRACTS-117] [CONTRACTS-124]. None keeps state or touches the network [CONTRACTS-136] [CONTRACTS-140].

## Words you'll see
| Term | Means | In the code | Claims |
| --- | --- | --- | --- |
| auto-router | a deployment whose provider model name starts with a fixed prefix; the router sorts it by kind; it is not a provider model | `auto_router/`, `classify_strategy_router_model` | CONTRACTS-001, CONTRACTS-013, CONTRACTS-014 |
| proxy | the server in front of the router that loads the setup file and takes admin requests that add or change models | `proxy_server` | CONTRACTS-006, CONTRACTS-008, CONTRACTS-010 |
| licensed feature | a complexity-router feature whose number of routers is capped by a limit the caller passes in; the proxy takes it from its license | `GatedAutoRouterCapability`, `capability_limit_violation` | CONTRACTS-051, CONTRACTS-063, CONTRACTS-142 |
| reasoning effort level | a named effort a request can ask a reasoning model for: none, minimal, low, medium, high, xhigh or max | `REASONING_EFFORT_ADVERTISEMENT_ORDER`, `resolve_supported_reasoning_efforts` | CONTRACTS-100, CONTRACTS-109 |
| model group | the public model name callers ask for, which several deployments can share | `model_name` | CONTRACTS-002, CONTRACTS-130 |
| deployment | one configured entry the router can send requests to: a provider model name plus its settings and model facts | `litellm_params`, `model_info` | CONTRACTS-162 |
| provider model name | the model a deployment is set to call; an auto-router puts its prefix here, not in its public model name | `litellm_params.model` | CONTRACTS-023, CONTRACTS-039 |
| router kind | which of four strategies an auto-router uses: semantic, complexity, adaptive or quality | `StrategyRouterKind`, `complexity_router`, `adaptive_router`, `quality_router` | CONTRACTS-013, CONTRACTS-015 |
| violation message | a plain reason a setup is refused, returned instead of an error; no message means the check found nothing wrong | `validate_strategy_router_model_write`, `validate_complexity_router_config_write` | CONTRACTS-023, CONTRACTS-030 |
| complexity settings block | the one settings block that configures a complexity router, and its optional default model setting | `complexity_router_config`, `complexity_router_default_model` | CONTRACTS-020, CONTRACTS-034 |
| dependency | a model an auto-router must be able to reach, with a role such as tier, default or classifier | `strategy_router_dependencies`, `StrategyRouterDependency` | CONTRACTS-012, CONTRACTS-038 |
| tier | one level of models a complexity router can send a request to | `tiers` | CONTRACTS-044, CONTRACTS-068 |
| classifier | the part of a complexity router that chooses a tier for each request; its kind is one setting, heuristic v1 when unset | `classifier_type` | CONTRACTS-045, CONTRACTS-057, CONTRACTS-075 |
| scoring rules | the heuristic v1 settings, such as tier boundaries and keyword lists, that the tuning quota watches | `HEURISTIC_V1_TUNING_FIELDS` | CONTRACTS-068 |
| fingerprint | a hash of the scoring rules a router's settings write out | `tuning_fingerprint` | CONTRACTS-069, CONTRACTS-070, CONTRACTS-073 |
| recorded baseline | each router's fingerprint as the proxy first stored it | `auto_router_tuning_baseline_v3`, `snapshot_tuning_baselines` | CONTRACTS-006, CONTRACTS-067, CONTRACTS-079 |
| router identity | the key a recorded baseline sits under: the database id, or the name and tags from the config file | `router_identity`, `db:`, `yaml:` | CONTRACTS-076, CONTRACTS-077 |
| tuning quota | the limit on how many routers may differ from their recorded baseline at once | `tuning_quota_violation` | CONTRACTS-083, CONTRACTS-084 |
| tuned router | a heuristic v1 router whose fingerprint differs from its recorded baseline; it holds one slot of the tuning quota | `is_mutable_tuned_candidate`, `mutable_tuned_identities` | CONTRACTS-080, CONTRACTS-081, CONTRACTS-083 |
| routing group | a named set of model groups with its own routing strategy, or a priority group callers ask for by name | `RoutingGroup`, `parse_routing_groups` | CONTRACTS-003, CONTRACTS-120, CONTRACTS-121 |
| routing strategy | the rule that picks one deployment for a request, such as simple-shuffle | `VALID_ROUTING_STRATEGIES`, `validate_routing_strategy` | CONTRACTS-116, CONTRACTS-117 |
| priority group | a routing group that gives each member a priority, which becomes its deployments' order | `model_priorities`, `apply_routing_group_priority` | CONTRACTS-118, CONTRACTS-122 |
| catalog-mapped | the model catalog gives the deployment a mode and the operator's own model facts give none | `deployment_is_catalog_mapped` | CONTRACTS-108 |
| model catalog | the built-in table of model facts and prices, read fresh on every call | `litellm.model_cost` | CONTRACTS-102, CONTRACTS-137 |
| reasoning switch | the model fact that says whether the model reasons at all | `supports_reasoning` | CONTRACTS-109, CONTRACTS-110 |
| level flag | a yes-or-no fact for one level: none, minimal, low, xhigh or max | `supports_low_reasoning_effort` | CONTRACTS-103 |
| declared level list | an explicit list of accepted levels in the model facts | `reasoning_effort_levels` | CONTRACTS-104, CONTRACTS-111 |
| baseline request | the routed request rebuilt for a baseline deployment, with its settings and then the caller's on top | `baseline_request` | CONTRACTS-094, CONTRACTS-095 |
| captured settings | the caller's allowlisted request settings, copied, with a read-only top level | `capture_baseline_parameters`, `BASELINE_PARAMETERS` | CONTRACTS-086, CONTRACTS-090, CONTRACTS-093 |

## At a glance
| When | Then | Claims |
| --- | --- | --- |
| A provider model name lacks the `auto_router/` prefix and carries no auto-router setting | the naming check returns no violation: it is a regular model | CONTRACTS-014, CONTRACTS-024 |
| A regular provider model name carries auto-router settings | refused: keep the prefix and change the public model name instead | CONTRACTS-023 |
| Two non-priority groups share a model | parsing raises one error naming every conflict; priority groups are exempt | CONTRACTS-128, CONTRACTS-129 |
| A group member is not in the model list | a warning only, and only when the caller passes model names | CONTRACTS-130 |
| The reasoning switch is exactly false | no levels, whatever the flags or a declared level list say | CONTRACTS-109 |

## The text after the auto-router prefix decides the router's kind
An auto-router is a deployment whose provider model name starts with a fixed prefix, and the text after that prefix picks its kind: semantic, complexity, adaptive or quality [CONTRACTS-013] [CONTRACTS-015] [CONTRACTS-016]. Each kind needs its own settings before the router can load it [CONTRACTS-019]-[CONTRACTS-022].

The prefix is the exact text `auto_router/`, matched case-sensitively and untrimmed, so a name starting with a capital A is a regular model [CONTRACTS-013] [CONTRACTS-014]. After the prefix, a rest beginning with `complexity_router`, `adaptive_router` or `quality_router` names that kind, by prefix, so `"auto_router/complexity_router-eu"` is a complexity router [CONTRACTS-015]. Every other name under the prefix is semantic, even an empty rest or a doubled prefix [CONTRACTS-016]. The Router decides a deployment's kind only through `classify_strategy_router_model` [CONTRACTS-001].

The required settings per kind are [CONTRACTS-019]-[CONTRACTS-022]:
- semantic: a routing config, inline or as a file path, plus a default model and an embedding model [CONTRACTS-019]
- complexity: `complexity_router_config` or `complexity_router_default_model`, either one alone [CONTRACTS-020]
- adaptive: its own config [CONTRACTS-021]
- quality: its config or a default model [CONTRACTS-022]

Health checks and permission checks ask `strategy_router_dependencies` which models a router must reach [CONTRACTS-012]. It reads raw settings only, so a malformed field yields no dependency rather than an error [CONTRACTS-049] [CONTRACTS-050].

## Each auto-router change goes through up to three checks that can refuse it
When an admin request adds or changes a model, the proxy runs up to three checks in order [CONTRACTS-008]. It asks whether the complexity settings block would load, whether complexity settings sit in the right place, and whether the name fits the settings [CONTRACTS-029] [CONTRACTS-034] [CONTRACTS-027]. The admin gets a failing check's reason back as a status 400 (bad request) error [CONTRACTS-008].

The content check validates the complexity settings block with the router's own settings model, so the proxy refuses a write exactly when the router would refuse to build it [CONTRACTS-029]. An absent block passes, and an empty one takes every default [CONTRACTS-029]. Only the first error is reported; a tier boundaries value that is not a mapping gives `"complexity_router_config is invalid at tier_boundaries: Input should be a valid dictionary. The router would drop this deployment at load time, so the write is rejected instead."` [CONTRACTS-030] [CONTRACTS-158]. An unknown top-level key with a string name passes whatever its value, while a top-level key that is not a string is refused [CONTRACTS-031]. Some nested blocks refuse unknown keys [CONTRACTS-171].

The placement check runs only when the provider model name is a complexity router or either complexity setting is present [CONTRACTS-034]. It refuses top-level keys that belong inside the block, since the provider would reject them as unknown parameters [CONTRACTS-036].

The naming check comes last [CONTRACTS-008]. It never reads the settings' contents, and its messages say how to fix the write [CONTRACTS-023] [CONTRACTS-028]. Loading its config file, the proxy refuses a misplaced setting (only on a deployment carrying complexity settings) or a licensed feature over its limit, before the router could silently drop the deployment [CONTRACTS-010].

@figure flow id=write-checks title="How the proxy judges a change to an auto-router"
| node change | Change to a model | CONTRACTS-008 |
| node content | Complexity settings block loads? | CONTRACTS-029 |
| node scoped | Carries complexity settings? | CONTRACTS-034 |
| node placed | Settings nested correctly? | CONTRACTS-035, CONTRACTS-036 |
| node named | Name fits its settings? | CONTRACTS-023, CONTRACTS-027 |
| node refused | Refused with a reason | CONTRACTS-008 |
| node passed | Change not refused here | CONTRACTS-024, CONTRACTS-028 |
| change > content | content first | CONTRACTS-008 |
| content > refused | no | CONTRACTS-030 |
| content > scoped | yes | CONTRACTS-029 |
| scoped > placed | yes | CONTRACTS-034 |
| scoped > named | no | CONTRACTS-034 |
| placed > refused | stray keys found | CONTRACTS-036 |
| placed > named | yes | CONTRACTS-035 |
| named > refused | no | CONTRACTS-027 |
| named > passed | yes | CONTRACTS-028 |

@steps write-checks
| content | Content comes first | The proxy first checks that the complexity settings block would load, whatever the model is called [CONTRACTS-029]. |
| scoped | Placement is scoped | The placement check runs only for a complexity router, or when either complexity setting is present [CONTRACTS-034]. |
| placed>refused | Stray settings | Settings written beside the block would reach the provider as unknown parameters, so the proxy refuses the change [CONTRACTS-036]. |
| named | Name comes last | The name must fit the settings: no doubled prefix, no empty router name, and every required setting present [CONTRACTS-025] [CONTRACTS-026] [CONTRACTS-027]. |
| refused | One reason back | The admin gets the failing check's message back with status 400 [CONTRACTS-008]. |

## Licensed features and changed scoring rules count against a limit
On the proxy, a license-based limit caps how many complexity routers may use each licensed feature, such as custom prompts [CONTRACTS-142] [CONTRACTS-063] [CONTRACTS-055]. A second limit caps how many may run with changed scoring rules [CONTRACTS-083] [CONTRACTS-142]. Over the second limit, the proxy refuses the admin's change, and a proxy holding too many changed routers stops at startup [CONTRACTS-008] [CONTRACTS-006].

The licensed features are the heuristic v2 classifier (alone or in a chain), the Capability classifier, the Fuse v2 classifier, and custom tier definitions or operator-written classifier prompts [CONTRACTS-052] [CONTRACTS-053] [CONTRACTS-054] [CONTRACTS-055]. A router claims a feature only when its provider model name is a complexity router, so a quality router with the same settings claims nothing [CONTRACTS-061]. Over the limit, the check returns a message such as `"At most 1 auto-router(s) with classifier_type 'capability' (Capability) can be registered but this would make 2. Use a different classifier or remove an existing Capability router."`, which names no license [CONTRACTS-063].

The tuning quota covers named complexity routers with valid settings on the heuristic v1 classifier, the default [CONTRACTS-075] [CONTRACTS-078]. A tuned router is one whose fingerprint differs from its recorded baseline, or from the shipped defaults when it has none [CONTRACTS-080]. Only the scoring rules feed the fingerprint, so changing tiers uses no slot, nor does changing the classifier within heuristic v1 [CONTRACTS-068] [CONTRACTS-078] [CONTRACTS-083]. When the proxy boots and finds no stored baselines, it records every such router's fingerprint under `auto_router_tuning_baseline_v3`, keyed by router identity [CONTRACTS-006] [CONTRACTS-067] [CONTRACTS-076].

When an edit would leave a router tuned, `tuning_quota_violation` counts it plus every other tuned router, never itself twice [CONTRACTS-083]. So re-editing keeps a slot, and reverting frees it [CONTRACTS-084]. Over the quota the proxy answers `403` with a license remedy appended; here 403 means the quota is full [CONTRACTS-008]. Take two heuristic v1 complexity routers, A and B, with a limit of 1 [CONTRACTS-082]:

@figure timeline id=quota title="Example: two routers share a limit of one tuned router"
| lane proxy | Proxy |
| lane a | Router A |
| lane b | Router B |
| 0 min | proxy | boots, finds no baselines | records both fingerprints | CONTRACTS-006, CONTRACTS-079 |
| 1 min | a | scoring rules edited | tuned, holds the slot | CONTRACTS-080, CONTRACTS-083 |
| 2 min | b | scoring rules edited | refused, quota full (403) | CONTRACTS-008, CONTRACTS-083 |
| 3 min | b | only its tiers changed | accepted, no slot used | CONTRACTS-068, CONTRACTS-083 |
| 4 min | a | scoring rules edited again | accepted, keeps its slot | CONTRACTS-084 |
| 5 min | a | reverted to its baseline | untuned, slot freed | CONTRACTS-084 |
| 6 min | b | scoring rules edited | tuned, holds the slot | CONTRACTS-083, CONTRACTS-084 |

## Routing group checks run in a fixed order, and the first failure wins
A routing group gives a set of model groups its own routing strategy [CONTRACTS-121]. A priority group is a name callers ask for, and it gives each member's deployments that member's priority as their order [CONTRACTS-003]. Groups pass a fixed series of checks, and the first failure raises an error for the caller setting up the router or the admin saving settings [CONTRACTS-002] [CONTRACTS-007] [CONTRACTS-124].

For a priority group, `apply_routing_group_priority` returns a changed copy and leaves the stored deployment alone; for any other group it returns the same deployment unchanged [CONTRACTS-118]. `parse_routing_groups` checks, in this order [CONTRACTS-120]-[CONTRACTS-130]:
- each group builds as a `RoutingGroup`; a priority group needs non-empty, distinct members, a priority for exactly each member, each a whole number from 1 to 9007199254740991 [CONTRACTS-120] [CONTRACTS-122] [CONTRACTS-123]
- every name is non-empty, though a name of only spaces passes [CONTRACTS-124]
- no group is named `"default"`, which is reserved for the implicit fallback group [CONTRACTS-125]
- names are unique; the error names only the first duplicate in sort order [CONTRACTS-126]
- each non-priority group's strategy is one of the accepted strategy names, matched exactly; `"priority"` is never a top-level strategy [CONTRACTS-116] [CONTRACTS-117] [CONTRACTS-127]
- no model sits in two non-priority groups; one error lists every conflict, and priority groups are exempt [CONTRACTS-128] [CONTRACTS-129]
- last, a member missing from the model list only logs a warning line, and only when the caller passes model names [CONTRACTS-130]

A bad strategy argument surfaces only when the Router builds the group's selector [CONTRACTS-132]. The Router adds one rule: a priority group may not share a name with a model or alias, while a non-priority group only gets a warning [CONTRACTS-002].

## Each deployment resolves its reasoning effort levels, or they stay unknown
Each deployment's reasoning effort levels resolve to one of three answers: unknown, known to accept none, or a list of levels [CONTRACTS-109] [CONTRACTS-110] [CONTRACTS-112]. The first rule that applies decides [CONTRACTS-111] [CONTRACTS-113]. Lists follow a fixed display order: none, minimal, low, medium, high, xhigh, max [CONTRACTS-100]. Callers see a model group's levels in its model information [CONTRACTS-004].

@figure flow id=effort title="How one deployment's effort levels resolve, first rule wins"
| node off | Reasoning switched off? | CONTRACTS-109 |
| node silent | Not marked, no flags? | CONTRACTS-110 |
| node catalog | Catalog-mapped? | CONTRACTS-108, CONTRACTS-110 |
| node listed | Valid level list declared? | CONTRACTS-111 |
| node flags | Any level flag set? | CONTRACTS-112 |
| node nolevels | Accepts no levels | CONTRACTS-109, CONTRACTS-110 |
| node unknown | Levels unknown | CONTRACTS-110, CONTRACTS-112 |
| node declared | The declared levels | CONTRACTS-111 |
| node composed | Levels built from flags | CONTRACTS-113 |
| off > nolevels | yes | CONTRACTS-109 |
| off > silent | no | CONTRACTS-109 |
| silent > catalog | yes | CONTRACTS-110 |
| catalog > nolevels | yes | CONTRACTS-110 |
| catalog > unknown | no | CONTRACTS-110 |
| silent > listed | no | CONTRACTS-110 |
| listed > declared | yes | CONTRACTS-111 |
| listed > flags | no | CONTRACTS-111 |
| flags > composed | yes | CONTRACTS-113 |
| flags > unknown | no | CONTRACTS-112 |

@steps effort
| off | Off wins | An explicit "no reasoning" fact gives no levels, even when flags or a declared level list say otherwise [CONTRACTS-109]. |
| silent | Nothing said | With no reasoning mark and no level flag, a catalog-mapped model accepts no levels and any other model is unknown; a declared level list is not read [CONTRACTS-110] [CONTRACTS-108]. |
| listed | A list wins whole | A valid declared level list beats the level flags, and an empty list means no levels [CONTRACTS-111]. |
| flags>unknown | No flags | A reasoning model with no level flag and no list is unknown, not given default levels [CONTRACTS-112]. |
| composed | Built from flags | Medium and high are always in, minimal and low unless switched off, xhigh and max only when switched on [CONTRACTS-113]. |

For `resolve_supported_reasoning_efforts`, a deployment is catalog-mapped when the model catalog gives it a mode and the operator wrote none [CONTRACTS-108] [CONTRACTS-110]. For a provider-prefixed entry such as azure/gpt-5-mini, each unset level flag, and an unset declared list, falls back to the unprefixed twin entry, but the reasoning switch does not [CONTRACTS-102] [CONTRACTS-103] [CONTRACTS-166]. When levels are built from flags, none is kept unless switched off, except on the azure provider's gpt-5 family, where it must be switched on [CONTRACTS-114].
## The router keeps the caller's own settings so a baseline request can be rebuilt
On every routing attempt, the router stamps a copy of the caller's own settings on the request, or clears the stamp [CONTRACTS-005]. The copy lets a baseline request be rebuilt later for a baseline deployment [CONTRACTS-094]. The copy leaves out credentials, and the capture gives nothing at all when the settings are too large or not plain data [CONTRACTS-090] [CONTRACTS-092].

The stamp holds the output of `capture_baseline_parameters` [CONTRACTS-005]. It keeps only allowlisted top-level keys, such as tools, temperature and token limits, in allowlist order; model, messages, metadata and stream never go in at the top level [CONTRACTS-086] [CONTRACTS-090]. By default it also adds the caller's extra body last, cut down to allowlisted keys plus messages [CONTRACTS-091]. A request with an API key, messages, a temperature of 0.2 and tools keeps only the tools and temperature [CONTRACTS-090].

The capture fails closed, returning None, when the settings exceed an estimated 4194304 bytes or 32768 charges, nest deeper than 32 levels, or are not plain JSON, such as a tuple [CONTRACTS-088] [CONTRACTS-092] [CONTRACTS-148] [CONTRACTS-163]. A successful capture has a read-only top level holding validated copies, so later changes to the caller's objects do not reach it [CONTRACTS-093].

`baseline_request` first captures the baseline deployment's own settings and returns None if that fails [CONTRACTS-094]. It then layers, later beating earlier: the routed request's other keys, the deployment's settings, the caller's settings, and merged tools [CONTRACTS-095]. With extra bodies included (the default), each side's extra body follows its settings [CONTRACTS-095]. When both sides' tools are lists and one is non-empty, the deployment's tools come first, then the caller's [CONTRACTS-096]. Allowlisted settings in the routed request itself never reach the result [CONTRACTS-097]. So routed max tokens 4, deployment 64 and caller 128 give 128 [CONTRACTS-164].

## Watch out
- Complexity tiers written in the object form, with a model name inside, are not listed as dependencies, so health checks and permission checks do not cover those models [CONTRACTS-155] [CONTRACTS-012].
- A deployment that lists its effort levels but sets neither the reasoning switch nor a level flag ignores its declared level list: no levels if it is catalog-mapped, else unknown [CONTRACTS-156] [CONTRACTS-110].
- One unknown deployment makes a whole model group's effort levels unknown, though the merging rule would keep the other deployments' levels [CONTRACTS-004] [CONTRACTS-115] [CONTRACTS-152].
- A routing group error saved through the proxy's settings update comes back as status 400 but typed as an authentication error [CONTRACTS-007].
- Writing a scoring setting at exactly its shipped default still counts as a change and uses up the tuning allowance, except escalation keywords left at their shipped default [CONTRACTS-070] [CONTRACTS-071].
- A limit of zero refuses even the first router, while no limit at all means unlimited [CONTRACTS-133] [CONTRACTS-142].
- Two license counts disagree for settings holding both old-name and new-name open-source classifier blocks with the old classifier type name [CONTRACTS-157]. If such stored settings exist, the database count claims the custom-prompt feature and the in-memory count does not, so license checks depend on the path [CONTRACTS-157].
