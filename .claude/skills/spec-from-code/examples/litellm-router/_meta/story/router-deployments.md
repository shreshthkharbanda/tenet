---
module: router-deployments
---
# The router files each deployment under one id that keys its prices and lookups

@plain
The router keeps a deployment list [RDEPLOY-023]. A deployment is one way to reach an AI model: a provider, a model and the keys to call it [RDEPLOY-001], [RDEPLOY-097]. Several deployments can share one public name, called a model group [RDEPLOY-163]. When the router starts with a list, it checks each deployment and settles its deployment id [RDEPLOY-012], [RDEPLOY-007]. The same settings give the same id after a restart, unless a row lists an id with no value [RDEPLOY-007], [RDEPLOY-008]. That id ties the deployment to its own prices and its deployment budget [RDEPLOY-080], [RDEPLOY-091]. A model group's prices come from its deployments in this list [RDEPLOY-133], [RDEPLOY-138]. One bad entry makes startup fail with that entry's error [RDEPLOY-033]. With skipping turned on, the router logs the error and leaves that entry out [RDEPLOY-033]. A failed edit can take a working model offline [RDEPLOY-209].

@minute
The model-list load builds each row in a fixed order, and the first failure ends that row's build [RDEPLOY-015]-[RDEPLOY-024]. A row with no declared id gets a SHA-256 hash of its name and expanded parameters [RDEPLOY-007]. The router appends each passing row to `model_list` and indexes it by id, by name and, when it has both a team and a team public name, by team [RDEPLOY-057]. Runtime add and upsert run only the provider and strategy-router checks [RDEPLOY-182]. Each deployment with an id registers its model info in the process-wide catalog under that id, without prices for a strategy router, plus a filtered copy under each shared backend key [RDEPLOY-080]-[RDEPLOY-082].

## Words you'll see
| Term | Means | In the code | Claims |
| --- | --- | --- | --- |
| deployment | one way to reach a model: a public name, provider settings with credentials, and descriptive info that carries an id | `model_name`, `litellm_params`, `model_info` | RDEPLOY-001 |
| model group | the public name callers ask for; several deployments can share it | `model_name` | RDEPLOY-163 |
| deployment id | the key of one deployment; on load, a hash of its settings when the row declares none | `model_info.id`, `generate_model_id` | RDEPLOY-007 |
| deployment list | the router's stored deployments in insertion order | `model_list` | RDEPLOY-186, RDEPLOY-197 |
| model-list load | the startup path that empties the registry and builds every row from the settings | `set_model_list` | RDEPLOY-001, RDEPLOY-002 |
| secret reference | a setting value that names an environment variable to read instead | `os.environ/` | RDEPLOY-006 |
| skip-invalid setting | a router setting: drop a bad deployment and carry on instead of failing | `ignore_invalid_deployments` | RDEPLOY-033 |
| config row | a row that came from the settings file rather than the database | `db_model` | RDEPLOY-013 |
| reserved capacity | capacity paid as a flat cost rather than per token, known as provisioned throughput (PTU); its id and price rules apply to config rows | `ptu_shares`, `LITELLM_ENABLE_PTU_COST_ATTRIBUTION` | RDEPLOY-005, RDEPLOY-015 |
| access window | a daily interval when a deployment is reserved for the teams it lists | `access_windows` | LIMITS-003, LIMITS-004, LIMITS-008, RDEPLOY-016 |
| environment gate | the check that keeps a row only in the environments it lists | `supported_environments`, `LITELLM_ENVIRONMENT` | RDEPLOY-014, RDEPLOY-021 |
| tag pattern | a regular expression a deployment declares for tag-based routing | `tag_regex` | RDEPLOY-022 |
| wildcard router | the matcher for deployments whose name holds a star | `pattern_router` | RDEPLOY-026 |
| strategy router | a deployment whose model setting marks it as a complexity, adaptive, quality or semantic router; it is not a model the router can call | `auto_router/` | RDEPLOY-060, RSELECT-015, RSELECT-016 |
| adaptive router | a strategy router that keeps learned state; built after every other row | `adaptive_routers` | RDEPLOY-074, RDEPLOY-072 |
| price catalog | the process-wide table of model prices and limits that every router shares | `litellm.model_cost` | RDEPLOY-188 |
| per-token prices | what one input or output token costs | `input_cost_per_token`, `output_cost_per_token` | RDEPLOY-020 |
| price reload replay | re-writing every live deployment's catalog entries after the catalog reloads | `replay_model_cost_registrations` | RDEPLOY-085 |
| runtime add, upsert, delete | the calls that change one deployment while the router runs | `add_deployment`, `upsert_deployment`, `delete_deployment` | RDEPLOY-040, RDEPLOY-046, RDEPLOY-053 |
| deployment budget | a spending cap and period for one deployment, tracked by its id | `max_budget`, `budget_duration` | RDEPLOY-091 |
| indexes | maps from an id, a name, or a team and public name to positions in the list | `model_id_to_deployment_index_map`, `model_name_to_deployment_indices` | RDEPLOY-187 |
| team public name | the name a team-owned deployment goes by for its team | `team_public_model_name` | RDEPLOY-057 |
| paused deployment | a deployment an admin has blocked | `blocked` | RDEPLOY-097 |
| deployment lookup | fetching one stored deployment by its id, or the first one of a group name | `get_deployment`, `get_deployment_by_model_group_name` | RDEPLOY-095, RDEPLOY-096 |
| discovered limits | token limits the router reads from an endpoint's own model listing | `arefresh_model_info`, `/v1/models` | RDEPLOY-105, RDEPLOY-108 |
| model alias | another name that points at a model group | `model_group_alias` | RDEPLOY-116 |
| group info | the merged description of a model group: limits, prices and capabilities | `get_model_group_info` | RDEPLOY-137, RDEPLOY-138, RDEPLOY-131 |
| per-minute rate limits | tokens and requests a group may use per minute | `tpm`, `rpm` | RDEPLOY-134 |
| rate-limit headers | response headers that tell the caller how much of this minute's limit is left | `x-ratelimit-remaining-tokens` | RDEPLOY-146 |
| reasoning-effort levels | the named reasoning-effort settings a group's models accept, which clients can see | `supported_reasoning_efforts` | RDEPLOY-140, RDEPLOY-210 |
| pin | a remembered choice that keeps related requests on one deployment for a set time | `deployment_affinity_ttl_seconds` | RDEPLOY-067, RDEPLOY-214 |

## At a glance
| When | Then | Claims |
| --- | --- | --- |
| A row fails a check and `ignore_invalid_deployments` is off | the error propagates and router construction fails | RDEPLOY-033 |
| A row fails a check and `ignore_invalid_deployments` is on | the load logs and drops the row; it retries only an unresolvable provider, at the next price reload | RDEPLOY-033 |
| The environment settings are valid and a row's `supported_environments` lacks the current `LITELLM_ENVIRONMENT` | the load skips it with a warning, after its price entries went into the catalog | RDEPLOY-014, RDEPLOY-021, RDEPLOY-020 |
| A config row has reserved-capacity terms while attribution is on | the load stores its per-token prices as `0.0` | RDEPLOY-017 |
| Two rows share an id and neither has reserved-capacity terms | the list keeps both; id lookups see only the later one | RDEPLOY-180 |
| An upsert drops `max_budget` or `budget_duration` | the deployment leaves the budget limiter | RDEPLOY-052 |
| A caller with no team asks for a group whose deployments all belong to teams | service tiers come from all its unpaused deployments, and the upstream model from the first of them | RDEPLOY-117, RDEPLOY-118, RDEPLOY-119 |
| A configured token limit is present but malformed, such as `"128,000"` | The per-name lookup reports no limit when it is the first deployment's, and the group listing leaves that deployment out of the maximum | RDEPLOY-114, RDEPLOY-113 |
| A deployment is deleted | its catalog entries stay until the next price reload | RDEPLOY-056 |
| Selection runs synchronously, or the async entry point runs under a router-wide routing strategy outside the five async-capable ones | no pre-routing step runs, so no strategy router chooses the model | RSELECT-060, RSELECT-128 |

## Loading checks rows in order; a failure drops the row or stops startup
When the router starts with a list, the model-list load builds each deployment one at a time [RDEPLOY-012], [RDEPLOY-001]. It fills in secret references and settles the deployment id, then runs a fixed series of checks [RDEPLOY-006], [RDEPLOY-007]. A failed check drops the row when the skip-invalid setting is on, and stops startup when it is off [RDEPLOY-033].

`set_model_list` empties the deployment list, its indexes and the semantic, complexity and quality registries [RDEPLOY-002]. Each top-level `os.environ/` value becomes the secret it names, except workload-identity pointer fields [RDEPLOY-006]. This pass skips nested values; registration later reads data-source endpoints and keys straight from the environment [RDEPLOY-006], [RDEPLOY-027]. A list of organizations becomes one deployment per organization, all sharing one id [RDEPLOY-009].

@figure flow id=row-build title="How the model-list load builds one row"
| node row | Row from the settings | RDEPLOY-001 |
| node prep | Secrets filled, id settled | RDEPLOY-006, RDEPLOY-007 |
| node rules | Reserved capacity, access window valid? | RDEPLOY-015, RDEPLOY-016 |
| node fields | Fields valid? | RDEPLOY-017 |
| node price | Prices inherited and recorded | RDEPLOY-019, RDEPLOY-020 |
| node env | Active in this environment? | RDEPLOY-021 |
| node valid | Patterns and provider valid? | RDEPLOY-022, RDEPLOY-024 |
| node register | Wildcards and strategy routers | RDEPLOY-026, RDEPLOY-031 |
| node stored | Stored and indexed | RDEPLOY-023, RDEPLOY-057 |
| node skipped | Skipped with a warning | RDEPLOY-021 |
| node failed | Dropped, or startup fails | RDEPLOY-033 |
| row > prep | one row at a time | RDEPLOY-001 |
| prep > rules | id settled | RDEPLOY-007 |
| rules > fields | yes | RDEPLOY-016 |
| rules > failed | no | RDEPLOY-015, RDEPLOY-016 |
| fields > price | yes | RDEPLOY-017 |
| fields > failed | no | RDEPLOY-017 |
| price > env | catalog entry written | RDEPLOY-020 |
| env > skipped | no | RDEPLOY-021 |
| env > valid | yes | RDEPLOY-021 |
| env > failed | bad environment settings | RDEPLOY-014 |
| valid > failed | no | RDEPLOY-022, RDEPLOY-024 |
| valid > register | yes | RDEPLOY-024 |
| register > stored | appended | RDEPLOY-023 |
| register > failed | setup error | RDEPLOY-034 |

@steps row-build
| prep | Fill secrets, settle the id | Each top-level secret reference in the provider settings becomes its value, except workload-identity pointer fields [RDEPLOY-006]. A row that declares no id gets one made from its settings, the same after every restart [RDEPLOY-007]. |
| rules | Check capacity and windows | Every row's access window settings must be valid [RDEPLOY-016]. A config row with reserved capacity needs an id of its own, but only when flat-cost billing is on or the row splits its capacity among teams [RDEPLOY-015]. |
| price | Record prices before the gate | The row's prices go into the price catalog before the environment check, so a row skipped or rejected later still leaves an entry until the next price reload [RDEPLOY-020]. |
| env>skipped | Skip rows for other environments | When the environment settings are valid, a row that lists environments stays only if the current environment is one of them; otherwise the router skips it with a warning [RDEPLOY-014], [RDEPLOY-021]. |
| env>failed | Bad environment settings fail | A missing or invalid current environment, or an invalid listed one, raises an error instead of skipping the row [RDEPLOY-014]. |
| valid | Check patterns and provider | Every tag pattern must compile, and the provider must be one the router knows, unless the row names a prompt-management model [RDEPLOY-022], [RDEPLOY-024]. |
| failed | Drop the row, or stop | With the skip-invalid setting off, the first failure stops the router from starting; with it on, the router drops the row and moves on [RDEPLOY-033]. |
| stored | Store and index | A passing row joins the end of the deployment list and the lookups by id and name, and by team when it has both a team and a team public name [RDEPLOY-023], [RDEPLOY-057]. |

Nothing rolls back a failure after registration began, so a dropped row can still sit in the wildcard router [RDEPLOY-034].

## Adaptive routers wait for the whole list; other strategy routers start at once
Some deployments are strategy routers [RDEPLOY-060]. In the usual case, one can choose the model a request goes to, before normal selection [RSELECT-060], [RSELECT-061], [RSELECT-105]. The router builds most of them as each row loads [RDEPLOY-031]. It builds adaptive routers only after every row exists, so they see the whole list [RDEPLOY-011], [RDEPLOY-072].

A deployment whose model starts with `auto_router/` is a strategy router, and its prefix picks the kind: complexity, adaptive, quality or else semantic [RDEPLOY-060]. Each kind checks its own required settings, and a second router with the same name and tags is a duplicate error [RDEPLOY-061], [RDEPLOY-063], [RDEPLOY-066], [RDEPLOY-068], [RDEPLOY-069]. A complexity router that claims a licensed capability must fit under a limit the router asks for on every registration; with no limit set, there is no ceiling [RDEPLOY-065], [RDEPLOY-076].

## Each deployment writes its own entry into the shared price catalog
Each deployment that has an id records its full details under that deployment id, in a price catalog that every router in the process shares [RDEPLOY-080], [RDEPLOY-188]. Those details include its per-token prices, unless it is a strategy router, which records none [RDEPLOY-082]. So two deployments of one model can carry different prices [RDEPLOY-213].

Each deployment also writes a filtered copy under each shared backend key, keeping only catalog fields and none of its own prices [RDEPLOY-081]. Before registering, a row can fill missing prices from its underlying model's built-in entry, in four steps that each need their own condition [RDEPLOY-020]:
- Off-peak base rates, only when off-peak pricing is on and the row sets no input per-token price, no input per-second price, no general per-second price and no tiered pricing [RDEPLOY-028].
- Cache prices, only when an input price is set; an explicit `0.0` counts as set [RDEPLOY-020].
- Service-tier prices, skipped when neither per-token price is set [RDEPLOY-020].
- The tiered output rate, only for tiered pricing that lacks an output rate [RDEPLOY-030].

Take two deployments of openai/gpt-4o: cheap sets both per-token prices to 0.0, and std sets none [RDEPLOY-213]. Cheap's entry holds the 0.0 prices plus inherited built-in ones, such as a cache-read price of 1.25e-06 [RDEPLOY-213]. Std's entry holds only its id, while the shared gpt-4o entry keeps 2.5e-06 input and 1e-05 output, so std's deployment info reports those built-in prices [RDEPLOY-213], [RDEPLOY-130].

Every registration is non-persistent, so after a catalog reload each live router's `replay_model_cost_registrations` retries the queued provider failures, re-registers every row still in its list, and clears group caches [RDEPLOY-188], [RDEPLOY-085], [RDEPLOY-086]. Only routers built with a list take part [RDEPLOY-012].

## Runtime edits run fewer checks and can lose a working deployment
While the router runs, the proxy can add, edit or delete one deployment at a time [RDEPLOY-040], [RDEPLOY-046], [RDEPLOY-053]. These changes skip most of the checks that loading applies [RDEPLOY-042]. An edit removes the old version before it adds the new one, so a failed edit can leave a model without its working deployment [RDEPLOY-047], [RDEPLOY-209].

`add_deployment` returns nothing when the id already exists, and a deployment built without an id gets a random one [RDEPLOY-040], [RDEPLOY-045]. It has no error handling, and it syncs the budget after storing the row, so a budget error leaves the row stored and routable [RDEPLOY-043].

`upsert_deployment` first looks up the id and strips capability fields; an error there propagates whatever the skip-invalid setting says, and nothing changes [RDEPLOY-049]. It returns nothing when name, provider settings and model info all match the stored row [RDEPLOY-046]. Otherwise it removes the old row, releases its strategy slots and adds the new one at the end of the list [RDEPLOY-047]. A failure later in the upsert ends as follows [RDEPLOY-049], [RDEPLOY-051]:
- Skip-invalid on, failure before the new row is stored: the router re-adds the old deployment at the end and logs that it restored it [RDEPLOY-049], [RDEPLOY-050]. If that re-add fails too, it logs a warning and the old row stays gone; an id that was new has nothing to restore [RDEPLOY-050].
- Skip-invalid on, failure after the new row is stored, as in the budget sync or the adaptive pass: the failed row stays and the old one is gone [RDEPLOY-049], [RDEPLOY-215].
- Skip-invalid off: the error propagates and nothing restores the old row; a failure after the new row is stored leaves that row in place [RDEPLOY-051].

`delete_deployment` returns the removed row, or nothing for an unknown id [RDEPLOY-053]. It repairs every index, unregisters the budget and releases strategy slots [RDEPLOY-053], [RDEPLOY-058]. Apart from a failed strategy-slot release, which it logs while still returning the row, it swallows any error and returns nothing, even after the row left the list [RDEPLOY-054], [RDEPLOY-055].

@figure timeline id=failed-edits title="Example: two failed edits of deployment d2, with skip-invalid on"
| lane d2 | Deployment d2 |
| lane callers | Callers of model m |
| 0s | d2 | serves m on gpt-4o | serving m | RDEPLOY-049 |
| 1 min | d2 | edit names an unknown provider | old m restored at end | RDEPLOY-049, RDEPLOY-050 |
| 1 min | callers | requests still reach m | served | RDEPLOY-050 |
| 2 min | d2 | edit to adaptive router, no settings | stored as m3 | RDEPLOY-049 |
| 2 min | callers | m has no deployment left | m gone | RDEPLOY-049, RDEPLOY-215 |

## Lookups read three indexes, and many answers come from the earliest deployment
The router finds deployments through three indexes: by deployment id, by name, and by team [RDEPLOY-187]. Many answers about a model name come from its first deployment in list order, and an edit moves a deployment to the end, which can change those answers [RDEPLOY-197].

The first-deployment answers are the by-name deployment lookup, configured mode, display name, token limits, upstream model and the adaptive router's cost reading [RDEPLOY-197], [RDEPLOY-070]. A team-owned deployment counts as usable only by its own team; one with no team is usable by everyone [RDEPLOY-098]. Credential lookup tries the id, the name, the team public name, then a wildcard, and returns nothing for a paused deployment [RDEPLOY-099].

Discovered limits fill only gaps: a configured limit that is present always wins [RDEPLOY-110]. `arefresh_model_info` probes only deployments whose provider resolves to `"hosted_vllm"`, `"openai"`, `"text-completion-openai"` or `"openai_like"`, that have a base address, no star in the model and no client-side credentials [RDEPLOY-106]. A probe that misses the cache sends one request to `/v1/models` with a 5-second timeout, and up to 8 probes run at a time [RDEPLOY-105], [RDEPLOY-108]. The router keeps discovered limits for 600 s and discards a result whose row was replaced during the probe [RDEPLOY-109].

## Group info takes the widest limits and highest prices of its members
To describe a model group, the router merges every deployment behind it [RDEPLOY-133], [RDEPLOY-138]. Limits and prices take the largest value, most features count when any member has them, and per-minute rate limits add up [RDEPLOY-138], [RDEPLOY-134].

`get_model_group_info` follows a model alias one hop, then gathers the deployments named exactly the group plus routing-group members of that name, or the matching wildcard deployments when there are none [RDEPLOY-131], [RDEPLOY-133]. The first member seeds the answer, and later members widen it, except in these fields [RDEPLOY-137], [RDEPLOY-138]:
- Fast mode holds only when every member supports it [RDEPLOY-139].
- Reasoning-effort levels are the intersection, and one unknown member makes the group unknown [RDEPLOY-140].
- The supported-parameter list takes the latest member's value that is set, even an empty one [RDEPLOY-138].
- Client-side auth settings come from the last member, when it sets them [RDEPLOY-141].

One memo shared by every router in the process caches these answers, and any router's change clears every router's entries [RDEPLOY-143]. After a call, the router stamps the group name on the response and, when it knows the group, the rate-limit headers [RDEPLOY-147]. A rate-limit header the provider already sent keeps the provider's value, and the router still adds its other ones [RDEPLOY-148]. For example, a group with `tpm` 5000 and `rpm` 50 that used 500 tokens and 5 requests this minute reports 4500 tokens and 45 requests remaining [RDEPLOY-146]. Remaining tokens can go negative, while remaining input and output tokens stop at 0 [RDEPLOY-146].

## Watch out
- Deployments the proxy adds or edits at runtime skip the environment, tag-pattern and access window checks, and the secret expansion, that loading applies [RDEPLOY-207]. One can serve in the wrong environment or carry an unexpanded secret reference [RDEPLOY-207].
- A failed edit can take a working model offline [RDEPLOY-209], [RDEPLOY-215]. With the skip-invalid setting off, the edit fails with its error and nothing restores the old deployment [RDEPLOY-209]. With it on, a failure late in the edit keeps the broken new one, while the router's warning says it is dropping it [RDEPLOY-215].
- A list of organizations on one deployment becomes several deployments sharing one deployment id [RDEPLOY-208]. A failure on one of them cools down all of them, and lookups by id find only the last one [RDEPLOY-208].
- Building any router from a list of deployments silently stops feedback to the adaptive routers of every other router in the same process [RDEPLOY-206].
- One deployment whose model the price catalog does not list hides a whole group's reasoning-effort levels from clients [RDEPLOY-210].
- A second router in one process can end up using the first router's pin cache and settings [RDEPLOY-216]. This happens when its strategy router pins requests with the same pin lifetime as the first router's pinning check [RDEPLOY-214].
