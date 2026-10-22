# Persona reader: router selection (round 5)

## 1. In my words

1. One AI model can run in several places, called deployments, that share one public name. [RSELECT-001]
2. The router's job is to choose which place serves each request. [RSELECT-020]
3. First it lists every place that could serve the requested name. [RSELECT-020]
4. Then filters remove places that are unhealthy, resting after errors, paused, or kept for another team. [RSELECT-024, RSELECT-043, RSELECT-044, RSELECT-046]
5. From what is left it picks one at random, unless another strategy is set. [RSELECT-067, RSELECT-139]
6. If nothing is left, the caller gets a 429 error, meaning no deployment could take the request. [RSELECT-054, RSELECT-283]
7. There is a full path and a shorter path that skips some checks, such as the team filter. [RSELECT-060, RSELECT-128]
8. Only the router-wide strategy setting picks the path; five named strategies, including the default, get the full path. [RSELECT-060, RSELECT-139]
9. Image generation through the synchronous method always gets the short path. [RSELECT-121]
10. Some model names are really redirectors that send a request on to another model before the lookup. [RSELECT-015, RSELECT-061]
11. After errors, a deployment rests for a while, five seconds by default. [RSELECT-282]
12. Some settings can be changed while the router runs, but many are silently ignored. [RSELECT-152, RSELECT-252]
13. Danger: with provider-budget-routing, every request for a model fails. [RSELECT-279]
14. Danger: with usage-based-routing, customers quietly lose team and rate-limit checks. [RSELECT-278, RSELECT-128]
15. The wait time in the 429 error is the cooldown length, not the time actually left, so it can mislead. [RSELECT-283]
16. I assume the end caller notices a 429; the chapter does not say who reads the info log. [RSELECT-054]

## 2. Where I got lost

Terms I did not understand (the chapter uses them without saying what they are):

1. "model group" versus "routing group" versus "deployment": I could not keep the three apart. "routing group: a named set of model groups sharing one strategy".
2. "team" and "caller": the plain-words paragraph says "reserved for another team" before anyone says what a team is. Is the caller my customer, my customer's user, or my own product?
3. "access group" and "the caller's key": "checks the caller's key against access groups". I do not know what a key or an access group is here.
4. "pre-routing hook": "the first step of the full path, where a strategy router can move the request to one of its tiers". I do not know what a hook or a tier is.
5. "strategy router": "an entry under a model name that never calls a provider". Then "auto, complexity, adaptive and quality routers". None of those four kinds is explained.
6. "tier params": "an output-token limit or a reasoning effort". It is defined in the glossary and never used in the body.
7. "session binding": "for Claude Code command-line traffic only". It appears only in the glossary. Is it relevant to my customers?
8. "common resolution": glossary only. The body just says "Resolution".
9. "lar1": a strategy name with no hint of what it is. Also "usage-based-routing-v2" versus "usage-based-routing": why do they take different paths, and which should a customer use?
10. "callback checks": "such as rate limits, affinity, prompt caching and stream continuation". "Callback" is never explained. I do not know what "stream continuation" is.
11. "affinity": "keeping a caller, a session or an earlier response on the deployment that already served it". I do not know when that matters.
12. "pass-through flag" and "pass-through endpoints": never explained.
13. "selection trace": "the trace span an asynchronous selection runs in, named route followed by the requested model". Is a trace a monitoring tool? Who looks at it?
14. "failure handlers ... when the request carries a logging object": "logging object" is meaningless to me.
15. "structured-output setting: the request's response format, the only request setting that pre-call checks test for provider support". I do not know what that tells a customer.
16. "Redis": "every key on its shared Redis server". Redis is never introduced, and I do not know whose server it is.
17. "wildcard route": "serves any name the pattern matches from its start". The example "openai/*-mini" has a star in the middle, so "from its start" confuses me.
18. "generic fallback list: the fallbacks entry under a literal star key". I read this three times. What is a "star key"?
19. "order: a deployment's priority number; selection keeps the lowest number present, and a higher number serves when the request names that level, as an order fallback does". I read this three times and still cannot say what it does.
20. "exclusion lists: deployment ids that failover or a retry asks selection to skip". I do not know what "failover" or "retry" means for the router here.
21. "provisioned-throughput share ... a team holding one uses only its shared deployments, and teams without one are kept off them". I read this twice.
22. "access window": I understood it as business hours, but I do not know who sets it.
23. "reset call" in "also run by the router's reset call": there is no earlier mention.
24. "allowed-failures policy" and "health-check routing": two switches that appear together. I do not know how a customer sets them.

Sentences I had to read twice or more:

25. "An asynchronous call takes the full path only when the router-wide strategy is one of the five full-path strategies, and a synchronous call always takes the reduced path". But the figure sends a synchronous call to "Routing plugins configured?" and then to "Error before any lookup". So "always takes the reduced path" is not quite true.
26. "so on a router that has them every reduced-path call fails before any lookup". Does that mean a customer with routing plugins can never use image generation? That sounds big, so I want it confirmed.
27. "Asynchronous pass-through selection skips this check and always runs the pre-routing hook". This looks like an exception to the main rule, and I do not know when it applies.
28. "Only the router-wide strategy counts here ... A routing group or one request can name its own strategy, which changes only how the final pick is made". "Strategy" seems to mean two different things (picks the path, picks the deployment). I got lost here.
29. "Ordinary deployments keep unmatched traffic: Suppose no router matched so far, tag filtering is on, every strategy router under the name has tags, and the name also has ordinary deployments". Four conditions at once. I read it three times and the figure for it has a 14-line chain.
30. "The chosen router's answer replaces the requested model and messages for the rest of selection, and the caller's own messages stay unchanged". Replaced, yet unchanged? I do not know which messages are meant.
31. "From then on the router names it by its provider model, so an error about paused dep-0 names openai/gpt-4o". So the error shows a different name than the one the caller asked for. Who sees that, and would a customer be confused?
32. "That error names no provider, so the configured fallbacks can still serve the request afterwards". I do not see why having no provider name lets fallbacks work.
33. "When the caller's team has no deployment under the name, the router looks for deployments whose provider model string equals the name". Why would a name equal a provider string?
34. "If that empties the list while health-check routing and an allowed-failures policy are both set, the router logs a warning and keeps the resting deployments". This seems to contradict "Resting deployments drop out". Under which settings do I get the 429 in the worked example, and under which does the router quietly serve from a resting deployment?
35. "A model group with one deployment still goes through every filter, so its paused deployment ends in the 429 instead." Versus 503 for a paused deployment asked for by id. A customer would see two different errors for the same pause. Which one do they get?
36. "a deployment whose blocked setting is the value true itself; the text "true" does not count". If a customer writes "true" in a config file, is the pause silently ignored? I would have asked who catches it.
37. "the caller usually gets an error with status 429": "usually" is never resolved. When does the caller not get it?
38. The worked example: dep-1 "starts a 60-second cooldown" at 20s, but nothing says why. At 30s the error says "retry in 60 seconds", but dep-0 is only 30 seconds from serving again. I understood this only after reading the "Watch out" line about "the configured cooldown length, not the time left".
39. The glossary says "5 seconds unless the router sets another length", but the example uses 60 without saying so. Where is that set?
40. "When no deployment of the group has a cooldown entry, as when all are paused, the error shows the build-time cooldown default, even after the cooldown time was changed". "Build-time" is unclear, and so is the case.
41. "A routing plugin's narrowed list of provider models stays on the request. So a fallback to another model whose own plugin pass narrows nothing can fail". I got the general idea (a leftover restriction breaks the fallback) but I cannot picture a real case.
42. "The reduced path calls no failure handlers. An asynchronous call handed to it still runs inside the selection trace; a synchronous call gets no trace ... On every path the error reaches the caller's retry and fallback loop, which logs an error line". I could not tell what gets logged where, or what a support engineer would look at.
43. "Setting the router-wide timeout to 0.5 seconds ... stores 0, which calls then skip as unset". Does "unset" mean no timeout at all? I would ask.
44. "Under one such as usage-based-routing, asynchronous calls skip the strategy routers, team filter, affinity and rate-limit checks, whatever strategy its routing group names". Understandable, but I would ask how a customer finds out which strategy they are on.

Places I would have asked a question:

45. "The strategy name provider-budget-routing passes validation but sets up no way to choose a deployment, which looks like a defect." The chapter itself says "looks like a defect". Is it fixed? Do I warn customers off it? Do any of our customers use it?
46. Who sees the "info log" and the "warning"? The chapter names no operator, no customer role, no dashboard. The "who would notice" part of my explanation is therefore a guess.
47. Which of these settings does a customer control, and which does only our engineering team control? The chapter does not say.
48. The settings update silently ignores keys (pre-call checks, health-check routing and others) and only writes a "debug log line". How would an administrator ever find out? Also "No rollback: ... a bad value stops the update after the earlier keys took effect" leaves a half-changed router.
49. Why does "Asking for a deployment by its id" skip cooldowns? Who asks by id, and is that a customer feature?
50. Flushing the cache "erases every key on its shared Redis server, including other applications' data". Who can trigger it? Is it part of the "reset call"?

Structure notes:

51. The "Words you'll see" section has about 45 entries and I could not hold them. Many are used only once, or only in the glossary.
52. Claim IDs run through nearly every sentence. I skipped over them, but they break up the reading.
53. "which here means no deployment could take the request" is repeated three or four times. It is helpful the first time and noise after that.

## 3. What I would tell a customer

When you run the same model in several places under one name, our router works out which places can take each request, drops the ones that are unhealthy, paused, resting after errors or reserved for another team, and picks one at random. If every place is out, your caller gets a 429 error, which here means nothing was available. Before I promise team limits or rate limits, I would check your strategy setting with engineering, because some settings skip those checks and one of them fails every request.
