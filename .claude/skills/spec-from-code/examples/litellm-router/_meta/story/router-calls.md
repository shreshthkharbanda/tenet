---
module: router-calls
---
# Each attempt makes one provider call, and broken streams can get a second chance

@plain
The router answers each request by trying one AI provider at a time [RCALL-164] [SYS-013]. Each try is an attempt, and an attempt makes exactly one provider call [RCALL-164]. Before calling, the attempt adds the chosen provider's access keys, time limits and tools [RCALL-049] [RCALL-066] [RCALL-078]. When the caller asks for a stream, the answer arrives in small pieces [RCALL-053] [RCALL-055]. If a stream breaks before any text reaches the caller, the router retries or falls back, as its settings allow [RCALL-053] [RCALL-007] [RCALL-172]. If a chat answer already showed text, the caller gets the error unless continuation applies [RCALL-006] [RCALL-019]. When recovery fails, the caller gets the provider's own error whenever the router has one to pass on [RCALL-159]. A stream the caller abandons unread can also hold one of a provider's few parallel slots until someone rebuilds the router [RCALL-203].

@minute
The retry loop runs one attempt per try, `_acompletion` for async chat [RCALL-044]. The attempt picks a deployment, binds it into the request and makes exactly one provider call, inside the deployment's parallel slot when it has a limit [RCALL-045] [RCALL-048] [RCALL-050] [RCALL-164]. It counts each success, counts failures other than timeouts once the deployment's model is known, and stamps failures on a selected deployment for the retry loop [RCALL-054] [RCALL-056] [RCALL-057] [RCALL-060] [RCALL-061]. It reads a stream's first chunk itself, so a failure reading it is retried like any other [RCALL-053]. A wrapper then guards the stream: a later break before content falls back unless the request turned fallbacks off [RCALL-007] [RCALL-172]. A break after content surfaces the provider's error unless `enable_mid_stream_fallback_continuation` is on and every check passes [RCALL-006] [RCALL-019].

## Words you'll see
| Term | Means | In the code | Claims |
| --- | --- | --- | --- |
| attempt | one try at serving a request on one deployment; it makes exactly one provider call | `_acompletion`, the per-attempt functions | RCALL-044, RCALL-164 |
| asynchronous and synchronous calls | two ways to call the router: an asynchronous call lets the program do other work while it waits, a synchronous call makes it wait | `acompletion`, `completion` | RCALL-160, RCALL-179 |
| retry loop | the router's outer loop that runs attempts one after another and decides whether to try again | `async_function_with_retries` | RCALL-063 |
| deployment | one configured provider model with its own credentials, limits and id; several can serve one model group | `litellm_params`, `model_info` | RCALL-049, RCALL-068 |
| model group | the public model name a caller asks for, which several deployments can share | `model`, `model_group` | RCALL-059 |
| parallel slot | one of a deployment's limited places for calls in flight at the same time | `max_parallel_requests` | RCALL-050, RCALL-177 |
| continuation | finishing a broken chat answer on another deployment by sending the partial text as the start of the reply | `enable_mid_stream_fallback_continuation` | RCALL-008, RCALL-019, RCALL-023, RCALL-169 |
| binding | writing the chosen deployment's metadata, tags, tools, time limits and client into the request before the call | `_update_kwargs_with_deployment` | RCALL-064, RCALL-066, RCALL-068, RCALL-073, RCALL-076, RCALL-078, RCALL-081 |
| metadata bucket | the request's bookkeeping dictionary, where the router records the routed deployment and its tags in place | `metadata`, `litellm_metadata` | RCALL-068, RCALL-073, RCALL-161 |
| client-side credentials | a key or endpoint the caller sends with the request instead of the configured one | `api_key`, `api_base`, `base_url` | RCALL-065 |
| tools | functions the model may call, merged from the deployment and the request | `tools`, `tool_choice` | RCALL-066 |
| time limit | how long a call may take, resolved separately for streaming and ordinary calls | `timeout`, `request_timeout`, `stream_timeout` | RCALL-082, RCALL-083 |
| call counters | in-memory tallies of calls, successes and failures, kept per router | `total_calls`, `success_calls`, `fail_calls` | RCALL-160 |
| failure stamp | facts the attempt writes on an error so the retry loop knows which deployment failed and its retry count | `failed_deployment_id`, `retry_skip_deployment_id`, `num_retries` | RCALL-060, RCALL-061, RCALL-063 |
| content filter | the provider's signal that it blocked an answer, which the router can turn into an error | `content_filter`, `ContentPolicyViolationError` | RCALL-051 |
| stream wrapper | the router's layer around a provider stream that catches a break and tries to recover | `_acompletion_streaming_iterator` | RCALL-001 |
| mid-stream error | the error a stream raises when it fails after opening; it carries the provider's own error inside | `MidStreamFallbackError`, `original_exception` | RCALL-003, RCALL-006 |
| committed stream | a stream whose generated text already reached the caller, so a restart would repeat it | `is_pre_first_chunk`, `generated_content` | RCALL-005 |
| fallback chain | the other model groups the router tries after a failure; each one it tries is a fallback | `fallbacks`, `content_policy_fallbacks` | RCALL-007, RCALL-172 |
| request snapshot | a copy of the request kept from before selection, used to restart a broken stream | `mid_stream_fallback_snapshot_kwargs` | RCALL-044 |
| prefill | an assistant turn marked so the model carries on from its text | `prefix` | RCALL-023 |
| token limit | the most tokens, the small text pieces providers count, that the caller lets the answer use | `max_tokens`, `max_completion_tokens`, `extra_body` | RCALL-008 |
| constraining setting | a request setting that a continued answer could break, such as a fixed output format | `response_format`, `n` | RCALL-021 |
| Responses API and Anthropic Messages | two request formats the router serves besides chat, each with its own kind of stream | `aresponses`, `anthropic_messages` | RCALL-118, RCALL-125 |
| early status events | events at the start of a Responses API stream that carry no answer text | `response.created`, `response.in_progress`, `response.queued` | RCALL-029 |
| frame | one event of an Anthropic Messages stream; content frames commit the stream, keepalive frames do not | `content_block_delta`, `ping` | RCALL-130, RCALL-131 |
| retry budget | how many same-group retries a broken Anthropic Messages stream may use | `num_retries`, `retry_policy` | RCALL-142, RCALL-143, RCALL-144 |
| generic API call | the shared attempt path for endpoints the endpoint factory builds, such as Responses | `_ageneric_api_call_with_fallbacks` | RCALL-116 |
| prompt-management tool | an integration the router knows by name, such as Langfuse, that supplies the prompt for a model group whose one deployment is named after it | `langfuse/gpt-4o`, `prompt_id` | RCALL-093, RCALL-095 |
| logging record | the record that tracks one request for logging; the proxy server supplies one with each request | `litellm_logging_obj` | RCALL-094 |

## At a glance
| When | Then | Claims |
| --- | --- | --- |
| A chat stream breaks before any generated text reached the caller | it re-enters the fallback chain with the original messages, unless the request turned fallbacks off | RCALL-005, RCALL-007, RCALL-172 |
| A chat stream breaks after text reached the caller, with continuation off (the default) | the caller gets the provider's `original_exception` (else the mid-stream error) and no fallback runs | RCALL-006, RCALL-169 |
| Text reached the caller, continuation is on and every check passes | the answer continues on another deployment from an assistant prefill | RCALL-008, RCALL-019 |
| A token limit has no tokens left, such as `max_tokens` 5 with 5 emitted | the original error surfaces without a fallback | RCALL-008 |
| The request carries `api_key`, `api_base` or `base_url`, even set to None | the router records the call under a per-request deployment with its own id | RCALL-065, RCALL-069 |
| A non-streaming chat answer ends with `content_filter` and the router's content-policy gate holds | it becomes `ContentPolicyViolationError` for the retry and fallback loop | RCALL-051 |
| The caller closes or drops an async chat stream before its first read | the parallel slot stays held and the provider stream stays open | RCALL-200 |

## The attempt binds the chosen deployment into the request before calling
The attempt writes the chosen deployment's tools, time limits and tags into the request and records it in the metadata bucket [RCALL-066] [RCALL-068] [RCALL-073] [RCALL-078]. Retries and fallback attempts reuse that one request, so each new binding overwrites the previous deployment's metadata [RCALL-181]. Router-wide defaults fill only settings the request left out, except default metadata, which wins over request metadata of the same name [RCALL-064].

A request carrying `api_key`, `api_base` or `base_url`, even set to None, gets a per-request deployment whose own id goes into metadata; it never joins the model list [RCALL-065] [RCALL-069]. When the request's tools are a list, a tuple or empty, deployment tools come first, and a request `tool_choice` wins whenever the request has that key, even as None [RCALL-066].

Each time limit comes from the first source that sets one: the request, the deployment's entry for the request's service tier, the deployment, then the router; a zero counts as unset [RCALL-082] [RCALL-083]. In split mode, which async chat uses, a streaming request also gets the longer of the two limits as `timeout`, so a stream answered in one piece gets the longer limit [RCALL-048] [RCALL-078].

## Each attempt makes one provider call and records how it went
The asynchronous chat attempt makes its one provider call inside one of the deployment's parallel slots, when the deployment has a limit [RCALL-050]. For a stream, it waits for the first piece before handing it back [RCALL-053]. A stream that dies before its first piece arrives therefore fails like an ordinary call, and the retry loop handles it [RCALL-052] [RCALL-053].

Success adds one to `success_calls` under the provider model, for example `"openai/gpt-4o"` [RCALL-054]. A failure adds one to `fail_calls` when the deployment's model was already resolved, and the attempt stamps the error when a deployment was selected [RCALL-057]. The stamp carries the deployment's configured `num_retries` when the error has none, and the failed deployment's id unless an earlier hop stamped one [RCALL-060] [RCALL-061].

A timeout error differs: while the global debug flag is on (the default), its message gains the deployment's time limits, and `fail_calls` does not change [RCALL-056]. A non-streaming answer that the provider ended with `content_filter` becomes a `ContentPolicyViolationError` only when the router's content-policy gate holds; otherwise the caller gets the filtered answer [RCALL-051]. The gate reads only router settings: an untried target left in the router's content-policy list, or, with no such list, a `"*"` catch-all in its fallbacks [RCALL-051].

## A chat stream that breaks before the caller sees text falls back
When a chat stream breaks before any text reached the caller, the router restarts the original request on its fallback chain, unless the request turned fallbacks off [RCALL-005] [RCALL-007] [RCALL-172]. When text already reached the caller, a restart would repeat it, so the caller gets the provider's own error unless continuation applies [RCALL-006] [RCALL-019].

The stream wrapper takes over the parallel slot and releases it when the stream ends, once the caller has started reading [RCALL-055] [RCALL-012]. It intercepts only a mid-stream error; other errors reach the caller unchanged [RCALL-003].

A committed stream is one whose break came after the first chunk, once some generated text went out; a role-only or empty piece commits nothing [RCALL-005]. An uncommitted break uses the request snapshot with the original messages, and the request's own fallback lists when sent, even an explicit None that turns the router's list off [RCALL-007] [RCALL-172]. The sync wrapper follows the same rule without continuation and runs the fallback chain inside the caller's read, blocking its thread [RCALL-038] [RCALL-039] [RCALL-179].

@figure flow id=chat-break title="What the chat stream wrapper does when a stream breaks"
| node break | Stream breaks mid-answer | RCALL-003 |
| node sent | Text already reached caller? | RCALL-005 |
| node allowed | Continuation allowed? | RCALL-019 |
| node room | Tokens left under limit? | RCALL-008 |
| node chain | Fallback chain runs | RCALL-007 |
| node error | Caller gets an error | RCALL-006, RCALL-013 |
| node done | Caller gets fallback answer | RCALL-010 |
| break > sent | wrapper checks output | RCALL-005 |
| sent > chain | no | RCALL-007 |
| sent > allowed | yes | RCALL-019 |
| allowed > error | no | RCALL-006 |
| allowed > room | yes | RCALL-008 |
| room > error | none left | RCALL-008 |
| room > chain | yes, send prefill | RCALL-008 |
| chain > done | fallback streams | RCALL-010 |
| chain > error | fallback fails too | RCALL-013 |

@steps chat-break
| break | A break arrives | The wrapper catches only the stream-break error, closes the provider stream and frees the deployment's parallel slot [RCALL-003] [RCALL-004]. |
| sent>chain | Nothing shown yet | The router restarts the request from its saved copy, with the original messages, on the fallback chain [RCALL-007]. |
| sent>allowed | Text already shown | A restart would repeat words, so the router continues only when the continuation option is on and every check passes [RCALL-019]. |
| room>chain | Room left | The router lowers the token limit by what the first answer used and sends the partial text as the start of the reply [RCALL-008]. |
| allowed>error | Not allowed | The caller gets the provider's own error rather than the router's internal wrapper error, whenever the wrapper carries one [RCALL-006] [RCALL-159]. |
| chain>error | Fallback fails too | The router logs the failure, then raises the provider error carried inside it, or the failure itself when it carries none [RCALL-013]. |

## After the caller sees text, a chat stream continues only when allowed
Continuation lets another deployment finish a chat answer that broke after text reached the caller, sending the partial text as the start of the reply [RCALL-008] [RCALL-023]. It is off unless the router's settings turn it on, covers only asynchronous chat streams, and runs only when a list of checks passes [RCALL-169] [RCALL-019].

With `enable_mid_stream_fallback_continuation` on, a committed stream continues only when all of these hold, in order [RCALL-019]:
- the error carries generated text and no disqualifying content, and the provider error is not a content-policy violation [RCALL-019];
- when the cut stream names a deployment, it is a router deployment, not a per-request credential one [RCALL-019];
- the settings it received do not constrain continuation, such as a JSON `response_format` or `n` above 1 [RCALL-020] [RCALL-021];
- no reachable fallback target overrides request settings or names a deployment that cannot continue [RCALL-022];
- no output guardrail runs on the post-call event [RCALL-019].

The continuation request ends with the partial text as an assistant prefill: a cut after "Hello" appends an assistant turn "Hello" marked as a prefix [RCALL-023]. A request already ending in a plain assistant turn builds nothing; the break surfaces [RCALL-024]. The router subtracts the emitted tokens from every integer `max_tokens` and `max_completion_tokens`, including those inside `extra_body` [RCALL-008]. A limit of 100 with 40 tokens emitted becomes 60; a limit of 5 with 5 emitted surfaces the original error [RCALL-008]. It waits up to 1 second for the cut stream's failure logging, then re-enters the chain [RCALL-008].

A splicer cuts a full echo of the sent text from the fallback's output, but a partial echo gets through [RCALL-014]. After "Hello world" went out, a fallback that yields "Hello" and then ends delivers "Hello" again [RCALL-014]. Post-call rules, when set, re-run after every released chunk, so a rule that only the finished answer satisfies fails early [RCALL-015].

@figure timeline id=continuation-example title="Example: a chat answer cut after 40 tokens finishes on a second deployment"
| lane caller | Caller |
| lane router | Router |
| lane a | Deployment A |
| lane b | Deployment B |
| 0s | a | sends the first piece | streaming | RCALL-053 |
| 0s | router | hands the stream over | wrapper holds the slot | RCALL-055 |
| 1s | caller | reads 40 tokens of text | text shown | RCALL-005, RCALL-008 |
| 2s | a | connection breaks mid-answer | stream cut | RCALL-003 |
| 2s | router | closes stream, frees slot | slot released | RCALL-004 |
| 2s | router | checks continuation rules | eligible | RCALL-019 |
| 2s | router | cuts limit 100 to 60 | 60 tokens left | RCALL-008 |
| 3s | router | waits up to 1 second | ready to continue | RCALL-008 |
| 3s | b | gets partial text as prefill | continuing | RCALL-008, RCALL-023 |
| 4s | caller | sees only new text | one joined answer | RCALL-014 |
| 5s | router | combines both legs' usage | usage summed | RCALL-010 |

## Responses API and Anthropic Messages streams hold early events so they can recover
Responses API streams hold back their early status events until the answer starts, and fall back on any break, even after output reached the client [RCALL-029] [RCALL-031]. Anthropic Messages streams hold back early frames too, while a retry or fallback could still take over [RCALL-129] [RCALL-134].

The Responses API wrapper holds at most 200 early status events at a time and releases them in order before the first other event [RCALL-029]. When text was generated, the fallback input appends a developer message asking the model to continue where it stopped, then the partial text as an assistant message [RCALL-026] [RCALL-031].

An Anthropic Messages stream commits at the first `content_block_delta` frame or once 200 frames wait [RCALL-131]. Before commit, an error frame with status 429 or at least 500 is recoverable if the retry budget or a fallback allows it [RCALL-136]. Any other error frame, including the gateway's own tool-retrieval failure, reaches the caller as sent [RCALL-136]. A recoverable failure retries in the group with the usual backoff, then goes to the fallback chain once the budget runs out [RCALL-141] [RCALL-147] [RCALL-151]. The budget is a count an earlier retry committed to, else a retry policy's count for the failure, else the integer `num_retries` of the request, deployment or router, else 0 [RCALL-143] [RCALL-144].

@figure states id=messages-stream title="An Anthropic Messages stream before and after it commits"
| state holding | Holding early frames | RCALL-134 |
| state live | Forwarding frames live | RCALL-129 |
| state retry | Retrying in same group | RCALL-146 |
| state backup | Trying fallback chain | RCALL-151 |
| state failed | Caller gets an error | RCALL-152 |
| holding > live | content or 200 frames | RCALL-131 |
| holding > retry | recoverable error frame | RCALL-135, RCALL-141 |
| retry > live | retry stream opens | RCALL-149 |
| retry > backup | budget runs out | RCALL-141 |
| backup > live | fallback stream opens | RCALL-151 |
| backup > failed | fallback fails too | RCALL-152 |
| live > failed | error after content | RCALL-136, RCALL-139 |

@steps messages-stream
| holding | Holding back | Before any content, while a retry or a fallback could still take over, the router holds start-of-message frames back [RCALL-129] [RCALL-134]. |
| holding>live | Content arrives | The first content frame, or a full buffer of 200 frames, flushes the held frames and goes live [RCALL-131] [RCALL-137]. |
| holding>retry | A recoverable error | A rate-limit or server error before content starts a retry in the same model group while the retry budget lasts [RCALL-136] [RCALL-141]. |
| retry>backup | Budget spent | When the retries run out, the last error goes to the fallback chain [RCALL-141] [RCALL-151]. |
| live>failed | Too late to recover | After content, the provider's error frame reaches the caller as the provider sent it [RCALL-136] [RCALL-139]. |

## Image, audio, rerank and generic calls follow the same attempt pattern
The asynchronous calls for image generation, transcription, speech and text completion run the same fallback loop as chat, and a failure sends a background alert before the error returns to the caller [RCALL-100] [RCALL-157]. Each attempt sends the provider the deployment's configured model, not the group name, except the plain synchronous text-completion call [RCALL-196] [RCALL-198].

Image group `"img"` calls `"openai/gpt-image-1"` [RCALL-196]. These attempts stamp a retry-skip id, so the retry loop skips that deployment only for a non-retryable status such as 400 or 401 [RCALL-063]. Factory-built endpoints, such as Responses and Anthropic Messages, use the generic API call and the `litellm_metadata` bucket [RCALL-116] [RCALL-118]. When selection fails and the router asked for pass-through, it calls the provider function directly with the requested name, without deployment settings [RCALL-117]. Outside async chat, the parallel slot covers only the provider call, so it limits stream openings, not open streams [RCALL-195].

Call counters use inconsistent keys: async chat counts under the provider model, transcription and speech under the group, sync image generation under `""` [RCALL-160].

## Watch out
- An asynchronous chat stream the caller closes or drops before reading its first piece never frees its deployment's parallel slot or closes the provider connection [RCALL-200] [RCALL-203]. With a limit of one parallel call, every later call to that deployment then fails with status 429, which here means all its parallel slots are in use [RCALL-200].
- A Responses API stream that breaks after output reached the client still falls back, so the client can receive pieces of two different responses [RCALL-191].
- When the fallback for a broken chat stream answers in one piece, the caller gets one empty item and loses the fallback's answer [RCALL-192].
- A model group whose prompt comes from a prompt-management tool always fails with a missing-key error unless the caller passes its own logging record, as the proxy server does [RCALL-094] [RCALL-197].
- A caller who turned fallbacks off can still get a blocked-content error instead of a filtered chat answer, when the router has a catch-all fallback and no fallback list for blocked content [RCALL-201].
- A caller allowed to send its own endpoint but no key makes the router send the deployment's configured key to that endpoint, which the caller controls [TARGETS-207] [TARGETS-211]. Other admin settings the router meant to strip reach it too [TARGETS-212].
- Two calls send the wrong thing: reranking sends a built-in language function as its input, and the synchronous text-completion call sends the group's public name [RCALL-190] [RCALL-198]. When that name is not itself a valid provider model, the text-completion call fails or reaches a different model [RCALL-198].
