---
module: request-targets
---
# Small helpers turn a requested name into one exact model, server and key

@plain
A caller asks the router for a model by name, and the router picks one deployment to serve it [TARGETS-059]. The helpers in this chapter shape that choice into one exact target [TARGETS-010] [TARGETS-046] [TARGETS-063]. A deployment name with a star can stand for many models, and the most specific match wins [TARGETS-003] [TARGETS-007]. Inside a Kubernetes cluster, a call can go to one server pod instead of the shared service name [TARGETS-046]. A caller may send its own key or server address [TARGETS-063]. Each deployment can also cap how many calls run at once [TARGETS-072]. When every slot is taken, the caller can get a "too many requests" error, and some star patterns can pick the wrong provider [TARGETS-076] [TARGETS-208]. Worst of all, a caller allowed to set its own address can have the administrator's key sent there [TARGETS-207].

@minute
Wildcard deployments sit in a registry sorted by specificity, and the first pattern matching the start of the requested name wins [TARGETS-003] [TARGETS-007]. On the async path, selection then drops other teams' deployments and, for web-search requests, deployments unable to search [TARGETS-109] [RSELECT-128]. For an opted-in deployment, pod resolution usually points `api_base` at one pod address, and otherwise keeps the service name [TARGETS-046] [TARGETS-059] [TARGETS-171]. Caller-sent credentials reach the provider call, as does every admin field the caller does not resend, even one stripped from the per-request record [TARGETS-211]. On the async completion and generic paths, a per-process slot limiter rejects overflow with an immediate 429 [TARGETS-076].

## Words you'll see
| Term | Means | In the code | Claims |
| --- | --- | --- | --- |
| deployment | one configured route to a provider model: its settings plus an info record holding its id | `litellm_params`, `model_info` | TARGETS-002, TARGETS-010, TARGETS-080 |
| wildcard pattern | a deployment name containing a star, which stands for any text in a requested name | `PatternMatchRouter`, `model_name` | TARGETS-002, TARGETS-006 |
| specificity | how specific a pattern is: its length first, then its count of special characters | `calculate_pattern_specificity` | TARGETS-020 |
| routed model | the provider model a wildcard match sends on, worked out per request | `litellm_params.model` | TARGETS-010, TARGETS-013 |
| asynchronous | describes a call through the router's non-blocking entry points, such as its async completion; blocking chat calls skip the team and web-search filters and take no slot | `acompletion` | TARGETS-076, RSELECT-128 |
| team owner | the team a deployment belongs to; an owned deployment serves only that team | `model_info.team_id` | TARGETS-085, TARGETS-100 |
| web-search support | a deployment's flag saying whether it can run a web search; a missing flag means yes | `supports_web_search` | TARGETS-107 |
| pod | one running server copy inside a Kubernetes cluster, with its own address | `pod_ip` | TARGETS-046 |
| pod discovery | an opt-in that points a deployment's calls at one pod address instead of its service name | `kubernetes_pod_discovery`, `KubernetesPodDiscovery` | TARGETS-024, TARGETS-046, TARGETS-171 |
| service address | the base address a deployment calls, whose host name stands for a group of pods | `api_base` | TARGETS-024, TARGETS-046 |
| name lookup | a domain name system (DNS) query for the pod addresses behind a service name; the waiting call gives up after 2 seconds | `getaddrinfo` | TARGETS-022, TARGETS-051 |
| outbound proxy | a server that relays the process's outgoing web traffic, set in the process environment | `HTTP_PROXY` | TARGETS-048 |
| pod list | the sorted pod addresses cached for one service host and port | `_PodSet` | TARGETS-026, TARGETS-028, TARGETS-031 |
| refresh interval | how old a pod list may get before a call looks it up again, 5 seconds unless set | `KUBERNETES_POD_DISCOVERY_REFRESH_INTERVAL_SECONDS` | TARGETS-022, TARGETS-170 |
| idle eviction | dropping a pod list that no call has used for over 300 seconds, unless set otherwise | `KUBERNETES_POD_DISCOVERY_IDLE_EVICTION_SECONDS` | TARGETS-022, TARGETS-170 |
| round robin | giving each new call the next pod in turn | `round_robin` | TARGETS-039 |
| session id | a caller's label that sends a session's first attempt to its top-ranked pod and each retry to the next; system-generated ids do not count | `litellm_session_id`, `session_id`, `session_affinity` | TARGETS-040, TARGETS-043, TARGETS-044 |
| retry count | how many times this request has already been retried | `request_retry_count` | TARGETS-045 |
| proxy bypass list | the hosts that skip the outbound proxy | `NO_PROXY` | TARGETS-048, TARGETS-209 |
| client-side credentials | a key or base address the caller sends with its own request | `api_key`, `api_base`, `base_url` | TARGETS-061 |
| per-request record | a copy of the deployment built for one request, with its own id and pricing | `original_model_id` | TARGETS-070 |
| clear list | the admin fields the per-request record drops when the caller changes the address | `CredentialLiteLLMParams` | TARGETS-065, TARGETS-067 |
| workload-identity disable flag | a setting meant to stop Anthropic token federation toward a host the caller chose | `anthropic_disable_workload_identity_federation` | TARGETS-066 |
| slot | one place under a deployment's cap for a call in flight | `in_flight` | TARGETS-071, TARGETS-072 |
| parallel-request cap | the most calls one deployment may have in flight in one process, on the asynchronous completion and generic paths | `max_parallel_requests`, `rpm`, `tpm` | TARGETS-076, TARGETS-077, TARGETS-079 |
| retry setting | how many times the Router's loop retries a failed attempt, 2 by default | `num_retries` | TARGETS-076 |
| fallback | another model group or tool the router tries after the first one fails | `fallbacks` | TARGETS-090, TARGETS-143 |
| batch row model | the model field inside each row of a batch upload file | `body.model` | TARGETS-128 |
| search tool | a named web-search back end with its own provider and key | `search_tool_name`, `search_provider` | TARGETS-141, TARGETS-147, TARGETS-148 |
| error detail switch | a global setting, on by default, that lets the Router add fallback notes to errors | `litellm.expose_router_debug_in_errors` | TARGETS-174 |

## At a glance
| When | Then | Claims |
| --- | --- | --- |
| An eligible call carries a session id the system did not generate | it gets the session's top-ranked pod; each retry moves one rank down | TARGETS-040, TARGETS-043 |
| The pod option is the text "true" or 1, or the address is "https" | the call keeps the service name | TARGETS-024, TARGETS-025 |
| The process has an "http" or "all" proxy and `NO_PROXY` exempts the service but not the pod | the call keeps the service name, with one warning per host | TARGETS-048, TARGETS-049 |
| A base-address redirect hits a per-user OAuth Copilot deployment with no credential name | a 400 error before the helper clears any field | TARGETS-069 |
| A teamless proxy admin asks for a model whose candidates are all team-owned, named exactly that model, from two or more teams | a 400 error asking for the deployment id | TARGETS-103, TARGETS-104 |
| A web-search request finds no deployment that supports search | an empty list, with no fallback to the unfiltered list | TARGETS-108 |
| `litellm.expose_router_debug_in_errors` is off, or the call is a nested fallback hop | the error gets no fallback note | TARGETS-174 |

## A requested name becomes a short list of usable deployments
The router first turns the requested name into candidate deployments, and a name can match a wildcard pattern, most specific pattern first [TARGETS-003] [TARGETS-007]. For asynchronous calls, it then drops other teams' deployments, and deployments that cannot search the web when the request needs it [TARGETS-109] [RSELECT-128].

Each deployment name with a star becomes a wildcard pattern in the Router's registry [TARGETS-002]. The registry orders patterns by specificity, length first, so a lookup tries "llmengine/*" before the catch-all "*" [TARGETS-020] [TARGETS-021]. A lookup returns copies of the deployments under the first pattern that matches the start of the name [TARGETS-007] [TARGETS-010].

The routed model depends on the stars in the deployment's own model [TARGETS-013]. Without a star it stays as written, so "llmengine/*" mapped to "anthropic/claude" always sends "anthropic/claude" [TARGETS-013]. With at least as many stars as the pattern captured, each star takes the next captured piece, so "llmengine/foo" under "llmengine/*" with model "openai/*" sends "openai/foo" [TARGETS-014]. With fewer stars, the name the pattern matched goes through unchanged [TARGETS-015].

A pattern lookup that misses retries with the provider in front, but a bare provider name never matches its own wildcard [TARGETS-016] [TARGETS-017].

The team filter keeps deployments with no team owner and those whose team owner is the request's team, so a request with no team loses every team-owned one [TARGETS-085] [TARGETS-100]. When the request's tools include a `"web_search"` or `"web_search_preview"` tool, the second filter drops deployments whose `supports_web_search` value is present but falsy (false, None, 0 or empty) [TARGETS-106] [TARGETS-107].

## Pod discovery picks one pod address for each eligible call
Inside a Kubernetes cluster, a deployment's address can name a service, and a name lookup returns the pods behind it [TARGETS-031] [TARGETS-046]. When a deployment opts in, the router usually sends each call to one pod's address instead [TARGETS-024] [TARGETS-046]. With no known pods, an "https" address or an outbound proxy rule, the call keeps the service name [TARGETS-025] [TARGETS-028] [TARGETS-046] [TARGETS-048].

Pod discovery applies only when a deployment sets `kubernetes_pod_discovery` to boolean true and its `api_base` is a plain "http" address whose host is a name, not an IP address [TARGETS-024]. An "https" address keeps its host name, because a pod IP would break the certificate's host-name check [TARGETS-025]. Every selection result passes through this step, including picks from a custom routing strategy [TARGETS-059] [TARGETS-060].

The resolver caches pods per service host and port, so deployments naming the same service share one pod list and one turn order [TARGETS-026]. For a list older than the refresh interval, one call starts a name lookup and waits up to 2 seconds, while calls arriving meanwhile get the old list [TARGETS-022] [TARGETS-029].
A "no such name" or "no data" answer means no ready pods: the resolver caches an empty list, and calls use the service name until the next refresh [TARGETS-033]. Any other network-level failure, including the timeout, keeps the old pods and waits a full interval before the next lookup [TARGETS-034]. An error of another kind, such as an invalid host name, reaches the caller [TARGETS-038].

@figure states id=pod-list title="A pod list's life, from first lookup to idle eviction"
| state none | No pod list | TARGETS-028 |
| state looking | Looking up pods | TARGETS-029 |
| state fresh | Fresh pod list | TARGETS-028 |
| state empty | No ready pods | TARGETS-033 |
| state stale | Stale pod list | TARGETS-028 |
| none > looking | first eligible call | TARGETS-028 |
| looking > fresh | pods found, or old kept | TARGETS-032, TARGETS-034 |
| looking > empty | name not found | TARGETS-033 |
| fresh > stale | refresh interval passes | TARGETS-028 |
| empty > stale | refresh interval passes | TARGETS-033 |
| stale > looking | next call refreshes | TARGETS-028, TARGETS-029 |
| stale > none | idle, then swept | TARGETS-022, TARGETS-161 |

@steps pod-list
| none | Nothing cached yet | Every deployment that names the same service host and port shares one pod list [TARGETS-026]. |
| none>looking | The first call looks up | The call that starts a lookup waits up to 2 seconds for the answer [TARGETS-022] [TARGETS-029]. Calls arriving meanwhile use the service name [TARGETS-028]. |
| looking>fresh | Pods found | The list holds the distinct addresses sorted as text, so 10.0.0.10 comes before 10.0.0.2 [TARGETS-031]. A transient lookup failure keeps the old pods instead [TARGETS-034]. |
| looking>empty | No ready pods | Calls use the service name, with no new lookups until the interval passes [TARGETS-033]. |
| fresh>stale | The list grows old | After 5 seconds by default, the next call refreshes the list [TARGETS-022] [TARGETS-028]. |
| stale>looking | A refresh is in flight | Other calls that arrive during the refresh get the old list instead of waiting [TARGETS-029] [TARGETS-176]. |
| stale>none | An idle list is swept | By default, the next eligible call drops a list unused for over 300 seconds, unless that list's refresh is in flight [TARGETS-022] [TARGETS-028] [TARGETS-161]. |

## Calls take turns across pods unless a session keeps them together
Calls without a session take the pods in turn, a round robin [TARGETS-039]. A call that carries a session id goes to that session's top-ranked pod, and each retry moves to the next pod in the ranking [TARGETS-040].

When both the old and the new list have pods, the turn position carries over a refresh, modulo the new list size [TARGETS-032]. Otherwise, and after an eviction, it restarts at the first pod [TARGETS-032]. Concurrent calls without a session to one service get consecutive pods, because the position moves under a lock [TARGETS-177].

With a session id, the resolver ranks pods by a hash of the session id and each pod address, then picks the pod at rank retry count modulo pod count [TARGETS-040] [TARGETS-045]. When a pod leaves, only sessions whose top pod it was move [TARGETS-042]. The id comes from metadata or the top-level `litellm_session_id`, never from a bare `session_id` argument [TARGETS-043] [TARGETS-044].
@figure timeline id=turns title="Example: three pods take turns, then the list shrinks and resets"
| lane list | Cached pod list |
| lane calls | Incoming calls |
| 0s | list | lookup finds three pods | 10.0.0.10, 10.0.0.2, 10.0.0.9 | TARGETS-031, TARGETS-032 |
| 0s | calls | first call | sent to 10.0.0.10 | TARGETS-032 |
| 1s | calls | second call | sent to 10.0.0.2 | TARGETS-032 |
| 6s | list | refresh finds two pods | 10.0.0.2, 10.0.0.9 | TARGETS-028, TARGETS-032 |
| 6s | calls | third call, turn carried over | sent to 10.0.0.2 | TARGETS-032 |
| 7s | calls | fourth call | sent to 10.0.0.9 | TARGETS-032, TARGETS-039 |
| 7 min | list | idle list swept on next call | looked up again, three pods | TARGETS-161, TARGETS-032 |
| 7 min | calls | fifth call | sent to 10.0.0.10 | TARGETS-032 |

## A caller's own address redirects the call but keeps admin settings
A caller can send its own key or server address [TARGETS-062]. When it changes the address, the router's record of the request drops the administrator's cloud, region, token, organization and header settings [TARGETS-065] [TARGETS-067]. The call to the provider still carries every administrator setting the caller did not resend, the key included [TARGETS-211].

A request carries client-side credentials when its arguments include `api_key`, `api_base` or `base_url`, even when the value is None [TARGETS-061] [TARGETS-062]. The Router overlays those values on a copy of the deployment, the per-request record, which gets a new id [TARGETS-063] [TARGETS-070].

When the caller sends `api_base` or `base_url`, the helper strips the clear list from that record and sets the workload-identity disable flag [TARGETS-065] [TARGETS-066]. The clear list also covers project fields, but not `api_key` [TARGETS-067] [TARGETS-207]. A key alone strips nothing [TARGETS-064].

The provider call ignores that record and starts from the deployment's own settings with the request arguments on top [TARGETS-211]. For example, an Anthropic deployment called with `"http://evil.example"` still passes `"admin-key"`, organization "adminorg" and its extra headers to the provider call [TARGETS-211]. The disable flag never reaches the call either, so only the Anthropic auth path's own host allowlist blocks federation there [TARGETS-066] [TARGETS-212].

## Each deployment caps calls in flight and rejects the overflow at once
Each deployment can limit how many calls it runs at once [TARGETS-077]. When an asynchronous completion or generic call finds every slot busy, it fails at once with a "too many requests" error about this deployment's own slots [TARGETS-073] [TARGETS-076]. The caller sees it only when retries and fallbacks also fail [TARGETS-076].

The cap comes from the first setting present: `max_parallel_requests`, then `rpm`, then `tpm` divided by 1000 and multiplied by 6, at least 1, then the Router's default [TARGETS-077]. A cap of 0 means no limit, while a negative cap rejects every request [TARGETS-078]. The limiter lives in the Router cache's in-memory layer, so the cap counts calls per process [TARGETS-079].

On the async completion and generic paths, the Router holds a slot around the provider call; the sync completion path holds none [TARGETS-076]. The rejection carries status 429 with the concurrent-requests rate-limit type, naming the deployment's own full slots, not a provider limit [TARGETS-073]. The retry loop treats that 429 like a provider's: it retries after backoff while the group has a healthy deployment and retries remain [TARGETS-076].

Take one deployment with a cap of 2, a 0.3-second provider call and 6 concurrent async calls [TARGETS-076]. With the default `num_retries` of 2, all 6 succeed and at most 2 run at once [TARGETS-076]. With `num_retries` set to 0, 2 succeed and 4 fail with the 429 [TARGETS-076].

## Batch files, search tools and failure messages follow their own rules
Three side jobs use these helpers too: batch files get their model rewritten row by row, searches spread across same-named tools, and a note on the final error says which fallbacks ran [TARGETS-091] [TARGETS-092] [TARGETS-094] [TARGETS-128] [TARGETS-146].

For an upload whose purpose is exactly "batch" and that is not a passthrough, the rewrite sets `body.model` in every row with a body object to the selected deployment's model [TARGETS-123] [TARGETS-128] [TARGETS-135]. Because every row changes, a restricted model named inside the file cannot slip past the batch model allowlist [TARGETS-135]. If any row never decodes as JSON, the helper returns the original file unchanged rather than ship a truncated batch [TARGETS-132].

A search call names a tool through `search_tool_name`, and each attempt picks one same-named tool at random [TARGETS-142] [TARGETS-146]. The tool's own provider, key and address always win over the request's [TARGETS-148]. The Router's fallback loop runs the call, so a fallback from "web1" to "web2" serves a failed "web1" search [TARGETS-143]. Retries do not run, whatever `num_retries` says, unless a retry policy covers the error or a model group shares the tool's name [TARGETS-143].
In the usual case, the note starts `"LiteLLM: model group '<group>' failed with the error above."` and names fallbacks tried or skipped for access or budget, with the detail cut to 2000 characters [TARGETS-089] [TARGETS-091] [TARGETS-092] [TARGETS-093] [TARGETS-174]. Mapping targets print with keys such as `"api_key"` masked after 4 characters, but a key named "apikey" prints verbatim [TARGETS-095].

## Watch out
- A caller allowed to set its own server address can have the administrator's provider key sent to that address [TARGETS-207].
- Admin settings a redirect should strip, such as organization, extra headers and cloud credentials, still reach the provider call [TARGETS-212].
- When a pattern has more stars than its provider model, and that model has at least one, the router passes on the name it matched, unchanged [TARGETS-015]. For a pattern starting with a star, such as Meta Llama on Bedrock, that name lacks the provider, so callers can get another provider or an error [TARGETS-208].
- Under default settings a failed search gets no retry, even with several same-named tools; the caller gets the error unless a fallback serves it, and the router queues an alert [TARGETS-145] [TARGETS-213].
- The call cap, the pod list and its turn order live inside each server process, so every running copy of the router keeps its own [TARGETS-023] [TARGETS-079].
- When the process has an "http" or "all" outbound proxy and the bypass list names the service, a network range for the pods exempts nothing [TARGETS-048] [TARGETS-050]. Calls then keep the service name, and the log shows one warning per host [TARGETS-049].
- A session id the system generated does not pin a pod; such calls take turns like any other [TARGETS-043].
