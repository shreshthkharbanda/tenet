---
module: deployment-limits
---
# Team filters and per-minute counters decide whether one deployment takes a request

@plain
This part decides whether one deployment, one copy of a model at an AI provider, may take a request [LIMITS-008], [LIMITS-055]. Listed teams can have a deployment to themselves for set hours each day [LIMITS-003], [LIMITS-008]. A team can also own a share of a provisioned deployment, counted in provisioned throughput units (PTUs) [LIMITS-020], [LIMITS-022]. Other callers lose that deployment, and get an error if nothing else is left [LIMITS-014], [LIMITS-027]. Separately, when an operator turns it on, a per-minute guard counts requests and tokens in each clock minute [LIMITS-050], [LIMITS-141]. A request over a limit gets 429 Too Many Requests from the router itself, not from the provider [LIMITS-060], [LIMITS-062]. One flaw costs capacity: a successful call keeps its whole output reservation for the minute, so callers get refused well below the set rate [LIMITS-200].

@minute
During selection, an access-window filter and then a PTU-share filter drop deployments kept for other teams [LIMITS-027], [LIMITS-008], [LIMITS-023]. When some router in the process lists `enforce_model_rate_limits`, a check then runs on the chosen deployment just before the provider call [LIMITS-050], [LIMITS-051]. It reserves the request's input estimate against any input-token limit and its maximum output against any output-token limit [LIMITS-055], [LIMITS-092], [LIMITS-093], [LIMITS-097]. It then checks any token and request limits, raising a 429 rate-limit error on a breach [LIMITS-055], [LIMITS-060]. A failed call refunds its reservation; a successful router call keeps it until the counter expires, because the success event never finds the reservation note [LIMITS-069], [LIMITS-190], [LIMITS-200].

## Words you'll see
| Term | Means | In the code | Claims |
| --- | --- | --- | --- |
| access window | a daily local-time interval during which a deployment serves only the teams it lists | `model_info.access_windows`, `filter_reserved_deployments` | LIMITS-003, LIMITS-008 |
| PTU share | a team's whole number of provisioned throughput units in one shared deployment | `model_info.ptu_shares`, `filter_ptu_shared_deployments` | LIMITS-020, LIMITS-022 |
| per-minute check | the optional check that enforces a deployment's per-minute limits just before the provider call | `enforce_model_rate_limits`, `optional_pre_call_checks`, `ModelRateLimitingCheck` | LIMITS-050, LIMITS-051 |
| reservation | tokens a request books against the input and output limits before the call | `io_token_pre_call_check`, `async_io_token_pre_call_check` | LIMITS-088, LIMITS-097 |
| input-token limit | the most input tokens a deployment takes in one clock minute | `itpm` | LIMITS-084, LIMITS-092 |
| output-token limit | the most output tokens a deployment takes in one clock minute | `otpm` | LIMITS-084, LIMITS-093 |
| token limit | the most total tokens a deployment takes in one clock minute | `tpm` | LIMITS-054, LIMITS-056 |
| request limit | the most requests a deployment takes in one clock minute | `rpm` | LIMITS-054, LIMITS-059 |
| counter | a number in the router's cache for one deployment, one limit and one UTC minute, written with a 60-second expiry | `<id>:<model>:tpm:<HH-MM>`, `<id>:<model>:rpm:<HH-MM>`, `global_router:<id>:<model>:itpm:<HH-MM>`, `global_router:<id>:<model>:otpm:<HH-MM>` | LIMITS-053, LIMITS-089 |
| rate-limit error | the error a refused request gets, with status 429 | `litellm.RateLimitError` | LIMITS-060, LIMITS-099 |
| refund | taking a reservation back off its counters and clearing its note | `io_token_refund_failure`, `refund_stale_reservation_before_retry` | LIMITS-109, LIMITS-110 |
| success event | the logging step that runs after a call succeeds and counts its tokens | `log_success_event`, `async_log_success_event` | LIMITS-066, LIMITS-067 |
| failure event | the logging step that runs after a call fails | `log_failure_event`, `async_log_failure_event` | LIMITS-069 |
| reservation note | four bookkeeping entries in the request's metadata that record each reserved amount and its counter | `_litellm_itpm_reserved`, `_litellm_otpm_reserved`, `_litellm_itpm_cache_key`, `_litellm_otpm_cache_key` | LIMITS-080, LIMITS-100 |
| reconcile | correcting a reservation to the tokens the call really used | `io_token_reconcile_success`, `async_io_token_reconcile_success` | LIMITS-104, LIMITS-106 |
| reserved-deployment error | the error a caller gets when the team filters leave no deployment | `litellm.BadRequestError` | LIMITS-014, LIMITS-027 |
| team ceiling | the tokens per minute a team's shares buy on one model group | `team_ptu_ceiling`, `PTUTeamCeiling` | LIMITS-036, LIMITS-037 |
| sizing row | the Azure capacity entry giving the input tokens per minute that one provisioned throughput unit buys | `input_tpm_per_ptu`, `AZURE_PTU_CAPACITY`, `model_info.base_model` | LIMITS-037, LIMITS-039 |
| settings section | one of a deployment's two sections, provider-call settings or descriptive information; a limit can sit in either, or at the deployment's top level | `litellm_params`, `model_info` | LIMITS-054, LIMITS-084 |
| error category | a label on a rate-limit error that tells a provider's limit from the router's own | `category`, `vendor_rate_limit` | LIMITS-062, LIMITS-197 |
| request slot | a per-task holder through which the check reads the request it guards | `io_token_rate_limit_request_kwargs` | LIMITS-081, LIMITS-083 |
| deployment bind | the moment the router attaches a chosen deployment to a request, before each attempt | `_update_kwargs_with_deployment` | LIMITS-083, LIMITS-175 |
| metadata | the caller's dict of request bookkeeping, which the router writes into in place | `metadata` | LIMITS-100, LIMITS-144 |
| Redis | an optional shared store for the router's counters, so every server sees the same counts; without it, each process counts in its own memory | `DualCache` | LIMITS-142, LIMITS-147 |
| asynchronous call | a router call in the non-blocking style, where the server keeps serving other requests while it waits; the check runs its async methods for it | `acompletion`, `async_pre_call_check` | LIMITS-052, LIMITS-121 |
| synchronous call | a router call in the blocking style, where the caller waits for the answer; the check runs its plain methods for it | `completion`, `pre_call_check` | LIMITS-064, LIMITS-121, LIMITS-204 |
| usage-based routing | a routing strategy that reads and writes the same minute counters to pick a deployment | `usage-based-routing-v2` | LIMITS-140 |
| input-token headers | response headers reporting a group's input-token limit, what remains and when the minute resets; output-token headers do the same for output | `x-ratelimit-remaining-input-tokens`, `x-ratelimit-remaining-output-tokens` | LIMITS-113, LIMITS-115 |

## At a glance
| When | Then | Claims |
| --- | --- | --- |
| No router in the process lists `enforce_model_rate_limits` | this module enforces no per-minute limit; the team filters still run | LIMITS-050, RSELECT-024 |
| A deployment sets none of `tpm`, `rpm`, `itpm`, `otpm` | the check passes it unchanged | LIMITS-055, LIMITS-088 |
| This minute's recorded tokens are at or above `tpm` | refusal with 429 and retry-after 60 | LIMITS-056, LIMITS-060 |
| The count, with this request added, exceeds `rpm` | refusal; the count keeps this request | LIMITS-059 |
| A reservation lifts its counter above `itpm` or `otpm` | the check takes it back, and on an output refusal the input one too | LIMITS-097, LIMITS-098 |
| The request sets max tokens to 0 | no output reservation and no output check | LIMITS-095 |
| An admitted router call fails | its reservations come back; token and request counts stay | LIMITS-069 |
| An admitted router call succeeds | no reconcile; its reservations stay until their counters expire | LIMITS-190, LIMITS-200 |
| Anything else raises in the check, such as a null settings section | the check admits and skips the remaining steps; no cooldown follows | LIMITS-064, LIMITS-202 |
| The deployment lacks an id or a provider model | no reservation; input and output limits go unenforced | LIMITS-089 |
| Every candidate falls to an active window that omits the caller's team | `litellm.BadRequestError` with the window's end time and zone | LIMITS-008, LIMITS-014 |
| The caller's team holds a share on some candidate | only shared candidates naming that team stay; other callers, the master key and no-team callers included, keep only open ones | LIMITS-021, LIMITS-022, LIMITS-023 |
| A router loads a model list with malformed windows | an error naming the model, or, when the router ignores invalid deployments, a log line and a skip | LIMITS-015 |

## An active time window keeps a deployment for the teams it lists
An access window keeps a deployment for listed teams during a daily stretch of local time [LIMITS-003], [LIMITS-008]. While a window is active, a caller from an unlisted team, or with no team, loses that deployment [LIMITS-008], [LIMITS-012]. If no deployment is left, the caller gets an error saying when the window ends [LIMITS-014].

Windows sit in `model_info.access_windows`, each with start, end, time zone and teams [LIMITS-003]. The filter turns the current UTC instant into that zone and compares only the time of day, start included and end excluded [LIMITS-004], [LIMITS-005], [LIMITS-014]. A 22:00 to 06:00 window crosses midnight, so it is active at 22:00 and not at 06:00 [LIMITS-006]. A team listed only in an inactive window counts as unlisted; a deployment with no active window stays for everyone [LIMITS-009], [LIMITS-011]. When the filter drops every candidate, selection raises `litellm.BadRequestError` with a message such as `"Deployment g is reserved for another team until 02:07 UTC"`, and a chat call appends its fallback outcome note [LIMITS-014].

## A PTU share keeps a deployment for its holders and sizes their ceiling
A provisioned deployment can split its units among teams as shares [LIMITS-020]. If the caller's team holds a share on any deployment that could serve the request, it keeps only the shared ones naming it; otherwise it keeps only deployments with no shares [LIMITS-022], [LIMITS-023]. Where capacity is known, shares also set a team ceiling on tokens per minute, which the proxy enforces [LIMITS-037], [LIMITS-038], [LIMITS-044].

The map sits in `model_info.ptu_shares`; one invalid entry makes the whole map count as absent, and a valid map is the access rule even without pricing terms [LIMITS-020], [LIMITS-026]. A single-team deployment counts as open here; in a shared group, the router's separate team lookup withholds it from other teams but offers it to a caller with no team [LIMITS-025]. When the filter drops candidates and keeps none, the router raises `litellm.BadRequestError` saying the deployment is reserved for the teams holding a PTU share of it [LIMITS-027].

The team ceiling sums each share times the sizing row's `input_tpm_per_ptu` over the group's sized, shared deployments naming the team [LIMITS-037]. The sizing row comes from the Azure capacity table, matched on `model_info.base_model` first, then on the provider model string [LIMITS-039].
## The per-minute check runs on the chosen deployment just before the call
When switched on, a per-minute check looks at the chosen deployment just before the provider call [LIMITS-050], [LIMITS-051]. It reserves tokens against any input and output limits, then checks any total-token and request limits; the first limit hit refuses with the router's own 429 [LIMITS-055], [LIMITS-060], [LIMITS-062].

A router creates the check only when its `optional_pre_call_checks` list `enforce_model_rate_limits` [LIMITS-050]. It builds one `ModelRateLimitingCheck` over its own cache and adds it to a process-wide callback list, unless one is already there [LIMITS-050]. Routers run every check on that list, so one registration guards every router in the process, all counting in the first router's cache [LIMITS-050], [LIMITS-051].

Each limit is the first set value among the deployment's top level, `litellm_params` and `model_info`, and 0 counts as set [LIMITS-054], [LIMITS-084]. The token limit only reads its counter, because the success event adds tokens after the call [LIMITS-056], [LIMITS-067]. So with no usage recorded even a token limit of 0 admits, and concurrent requests can together pass the limit [LIMITS-056], [LIMITS-172]. The request limit adds 1 first and refuses above the limit, so with a limit of 2 and four concurrent requests on one process, exactly two pass [LIMITS-059], [LIMITS-170].

Every refusal raises `litellm.RateLimitError` with a retry-after header of 60 seconds and text such as `"litellm.RateLimitError: Model rate limit exceeded. TPM limit=1000, current usage=1000"`, to which the router appends an outcome note when it re-raises [LIMITS-060], [LIMITS-099]. Its `category` is the default `vendor_rate_limit` [LIMITS-062]. The async dispatcher hands the refused deployment to the cooldown handler with status 429; failure-handling decides whether it cools down [LIMITS-052].

@figure flow id=minute-check title="The per-minute check, from the chosen deployment to the provider call"
| node chosen | Deployment chosen | LIMITS-051 |
| node io | Input or output limit? | LIMITS-055, LIMITS-085 |
| node fits | Reservations fit? | LIMITS-097 |
| node any | Token or request limit? | LIMITS-055 |
| node tokens | Minute's tokens under limit? | LIMITS-056 |
| node count | New count within limit? | LIMITS-059 |
| node call | Call the provider | LIMITS-055 |
| node refuse | Refuse with 429 | LIMITS-060, LIMITS-099 |
| chosen > io | check switched on | LIMITS-050 |
| io > fits | yes: reserve tokens | LIMITS-088, LIMITS-098 |
| io > any | no | LIMITS-055 |
| fits > any | yes | LIMITS-055, LIMITS-097 |
| fits > refuse | no: take them back | LIMITS-097, LIMITS-098 |
| any > call | no | LIMITS-055 |
| any > tokens | yes | LIMITS-055 |
| tokens > count | under, or no token limit | LIMITS-056 |
| tokens > refuse | no: refund any reservation | LIMITS-056, LIMITS-063 |
| count > call | within, or no request limit | LIMITS-059 |
| count > refuse | no: refund any reservation | LIMITS-059, LIMITS-063 |

@steps minute-check
| chosen | Last check before the call | When switched on, the check sees the chosen deployment just before the provider call [LIMITS-050], [LIMITS-051]. |
| io>fits | Tokens come first | A deployment with an input-token limit first reserves the request's estimated input, and one with an output-token limit reserves its maximum output [LIMITS-055], [LIMITS-092], [LIMITS-093], [LIMITS-100]. |
| fits>refuse | An overflow undoes itself | A reservation that pushes a counter over its limit comes straight back off, and the request gets a 429 [LIMITS-097], [LIMITS-099]. |
| any>call | No limits, no counting | A deployment with neither a token nor a request limit goes on to the provider [LIMITS-055]. |
| tokens>refuse | The token limit only looks | The token limit refuses once the minute's recorded tokens reach it; it adds nothing before the call [LIMITS-056]. |
| count>refuse | The request limit counts first | The request limit adds this request, then refuses above the limit, and the refused request stays in the count [LIMITS-059], [LIMITS-063]. |
| call | Errors let requests through | Any other error inside the check lets the deployment through and skips the remaining steps, leaving only a debug log line [LIMITS-064]. |

## Input and output limits make a request reserve tokens before the call
In the usual case, an input token limit makes a request reserve a guess at its input, and an output token limit the most output it allows [LIMITS-088], [LIMITS-092], [LIMITS-093], [LIMITS-100]. A reservation that would pass its limit comes straight back off, and the check refuses [LIMITS-097], [LIMITS-098].

On the normal call path, the router fills the check's request slot at every deployment bind, but only for deployments with input or output limits [LIMITS-081], [LIMITS-083], [LIMITS-162]. The router's turn-admission path strips those two limits first, so it never reserves [LIMITS-087].

The input reservation is the tokenizer's count of the messages or prompt, or 1 token when that count is 0 or fails [LIMITS-090], [LIMITS-092]. The output reservation is the request's max tokens, else the model's listed maximum, else 4096; an explicit 0 skips it and its check [LIMITS-093], [LIMITS-095]. Nothing caps a reservation, so the check always refuses a request whose reservation alone exceeds its limit [LIMITS-096].

Each reservation adds its amount to the counter, then compares; above the limit it subtracts the whole amount again and raises, while landing exactly on the limit passes [LIMITS-097]. With an output limit of 10, max tokens of 4 and eight concurrent requests, exactly two pass [LIMITS-171].

When the reservations fit, the check writes a reservation note into the request's `metadata`, which through the router's chat calls is the caller's own dict [LIMITS-100]. If the slot holds no request, the counters still grow but no note exists, so nothing refunds that reservation before its counter expires [LIMITS-101].

@figure states id=reservation-life title="What happens to a token reservation after the check makes it"
| state none | No reservation yet | LIMITS-088 |
| state held | Tokens reserved | LIMITS-097, LIMITS-100 |
| state refunded | Given back | LIMITS-109 |
| state kept | Kept until minute ends | LIMITS-190, LIMITS-200 |
| state corrected | Corrected to real use | LIMITS-106 |
| none > held | reservations fit | LIMITS-097, LIMITS-098 |
| held > refunded | failure, refusal or new bind | LIMITS-063, LIMITS-069, LIMITS-110 |
| held > kept | router call succeeds | LIMITS-190 |
| held > corrected | success event finds note | LIMITS-066, LIMITS-106 |

@steps reservation-life
| none>held | The reservations fit | For each input or output limit that is set, the check adds the input estimate or the maximum output to this minute's counter, then writes a note into the request [LIMITS-089], [LIMITS-092], [LIMITS-093], [LIMITS-097], [LIMITS-100]. |
| held>refunded | Trouble gives tokens back | A failed call, a token or request refusal in the same check, or the next deployment bind subtracts the reserved amounts and clears the note [LIMITS-063], [LIMITS-069], [LIMITS-110]. |
| held>kept | Success keeps everything | The router's success event never finds the note, so the whole reservation stays until the minute's counter expires [LIMITS-190], [LIMITS-200]. |
| held>corrected | Correction needs the note | Only a success event that carries the note where the check looks, with a usage count, corrects the counters to real use [LIMITS-066], [LIMITS-106], [LIMITS-107]. |

## A successful router call keeps its whole reservation until the minute ends
A failed call gives its reserved tokens back [LIMITS-069], [LIMITS-109]. A successful call through the router does not: its whole reservation stays on the counters until they expire, even when the reply used far fewer tokens [LIMITS-190], [LIMITS-200].

A failure event refunds the reserved amounts and clears the note, but never touches the token or request counters [LIMITS-069], [LIMITS-109]. A token or request refusal in the same check also refunds, when the slot holds the request that reserved [LIMITS-063], [LIMITS-122]. So does the next deployment bind of any request carrying a note, including a later request that reuses the caller's dict; that refund trusts forged notes too [LIMITS-083], [LIMITS-144], [LIMITS-112].

The success event reconciles only when it finds the note in the callback's top-level `metadata` or the standard logging object's metadata [LIMITS-066]. The router's success events carry it in neither place, so the router never reconciles a successful call [LIMITS-190], [LIMITS-200]. A success event that does carry the note there corrects each counter by actual minus reserved, provided it finds the call's usage [LIMITS-106], [LIMITS-107].

The success event also adds total tokens to the token counter, but skips events with no model name [LIMITS-067]. So the router's streaming chat and Anthropic-messages calls never count toward the token limit [LIMITS-204]. If the model name it writes under ever differs from the provider model the check reads, the token limit never applies [LIMITS-198].

In the example, deployment D's output limit is 50, and the clock starts on a UTC minute [LIMITS-099], [LIMITS-141]. Had the router reconciled A, the counter would have read 5, leaving room for B [LIMITS-190], [LIMITS-097].

@figure timeline id=output-limit title="Example: an output limit of 50 a minute and two requests for 40"
| lane a | Request A |
| lane b | Request B |
| lane d | Output counter |
| 0s | a | asks for up to 40 tokens | admitted | LIMITS-093, LIMITS-097, LIMITS-099 |
| 0s | d | rises by 40 | 40 of 50 | LIMITS-097, LIMITS-099 |
| 10s | a | succeeds after 5 output tokens | done | LIMITS-190 |
| 10s | d | no correction for A | still 40 of 50 | LIMITS-190, LIMITS-200, LIMITS-099 |
| 20s | b | asks for up to 40 tokens | refused with 429 | LIMITS-097, LIMITS-099 |
| 20s | d | briefly 80, then back down | 40 of 50 | LIMITS-097, LIMITS-099 |
| 60s | d | next UTC minute begins | fresh counter | LIMITS-141 |
| 61s | b | caller sends it again | admitted | LIMITS-097, LIMITS-141 |
| 61s | d | rises by 40 | 40 of 50 | LIMITS-097, LIMITS-099 |

## Every counter lives one UTC minute and spans servers only through Redis
Each limit counts one fixed clock minute in UTC, then starts a fresh count [LIMITS-141]. While a shared Redis store works, the request and reservation limits count the traffic of every server [LIMITS-142]. Without Redis, each process counts alone [LIMITS-147].

A counter key holds the deployment id, provider model and UTC hour and minute, such as `"global_router:d1:gpt-4o:itpm:01-36"`, and every write carries a 60-second expiry [LIMITS-089], [LIMITS-080], [LIMITS-053].
A group's remaining-usage response gains input-token headers only with an input limit, output-token ones only with an output limit [LIMITS-113], [LIMITS-115].

## Watch out
- A successful router call keeps its whole token reservation for the minute, so callers see output-limit refusals well below the set rate [LIMITS-200], [LIMITS-190].
- Streaming chat calls and Anthropic messages calls never count toward a deployment's token limit, so that limit does not bound them [LIMITS-205], [LIMITS-204].
- On every router, a caller can forge a reservation note that lowers another deployment's counter; a forged 1-token refund per request keeps a 1-request-a-minute deployment admitting without end [LIMITS-112], [LIMITS-110].
- The check fails open: a null settings section, or max-tokens text such as "abc" on an input- or output-limited deployment, lets the request through with every limit off [LIMITS-139], [LIMITS-064], [LIMITS-202]. Only a debug log line records it [LIMITS-064].
- These refusals carry a provider's rate-limit label, so clients that sort errors by source blame the provider for the router's own limit [LIMITS-197], [LIMITS-062].
- If Redis fails, two servers, each counting alone, admit up to twice the limit on an asynchronous call [LIMITS-142], [LIMITS-121]. A synchronous call then skips request, input-token and output-token limits [LIMITS-142], [LIMITS-121].
- With the usage-based routing strategy (version 2) also on, each request counts twice, so a limit of 4 requests a minute admits only 2 [LIMITS-140].
- A broken share map counts as no share, and deployments added while the router runs skip the check that refuses one, so an empty share map serves every team [LIMITS-136], [LIMITS-025].
