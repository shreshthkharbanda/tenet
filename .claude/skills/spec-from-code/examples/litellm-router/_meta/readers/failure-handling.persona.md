# Persona reader: failure-handling, round 5

## 1. In my words

1. One public model name can sit in front of several copies of the model; the chapter calls the copies deployments. [FAILURE-034]
2. When a call to one copy fails, the router decides whether to bench that copy: a short timed pause, called a cooldown, so new requests go to the other copies. [FAILURE-021, RDISP-191]
3. Before any rule applies, nine checks can veto the bench, for example an unknown deployment, a failure of the caller's own key, a zero cooldown time, or a provider-default deployment. [FAILURE-022]-[FAILURE-030]
4. Under default settings a 401 or 404 benches the copy at once, even when it is the only copy. [FAILURE-044]
5. A 429 benches the copy unless it is the only one. [FAILURE-043]
6. A 500 does not bench on its own: it needs over half of at least 5 recent requests, counted on that one server, to have failed. [FAILURE-043, FAILURE-073]
7. A bench lasts 5 seconds unless something sets it otherwise. [FAILURE-048, RDISP-191]
8. The bench is one entry in a shared store (Redis), and other servers usually notice it within about a second. [FAILURE-052, FAILURE-009]
9. A bench shorter than one second stays on one server, so the other servers keep sending traffic to that copy. [FAILURE-006]
10. After that the router may retry the same group, then try backup models from a list, skipping any it already tried. [FAILURE-103, FAILURE-145]
11. If every copy is benched and no backup model answers, the caller gets a 429 "try again" error. [FAILURE-179, RDISP-115]
12. Prometheus numbers can record benches, but the bench itself alerts nobody. [FAILURE-056]
13. A lone copy that returns 429s or 500s mostly keeps getting traffic, because it needs 1000 requests in a minute failing before it is benched. [FAILURE-043]
14. The first 50 characters of the error text are stored unmasked, so a key echoed early in an error could leak into the shared store and logs. [FAILURE-210]
15. The "try again in" number in the 429 may not be the real time left. [FAILURE-017, FAILURE-178]

## 2. Where I got lost

- "lone deployment: the only deployment of its model group, when the router has no other deployment it may use instead for that request". I read this three times. If it is the only one, why the extra clause? Can a lone deployment stop being lone depending on the request? What is "may use instead" about?
- "Nine ordered checks can stop a bench before any rule decides" and then the only description is "an unknown deployment, a failure of the caller's own credential, a request rejected before the call, or a personal Copilot session or credential" plus four more. I count eight phrases for nine checks, so I cannot match the names to the nine. I would ask for a numbered list.
- "a personal Copilot session or credential": Copilot is never explained. Is it a provider? Why does it get its own checks?
- "a request rejected before the call": rejected by whom, and for what reason?
- "a failure of the caller's own credential ... such as a stored key that was rejected or rate-limited": what is a "stored key"? Stored where? Why would a rate limit on the caller's key not hurt the shared copy?
- "provider-default deployment: a deployment the router lists as a provider's default". Lists where? Who decides? Why can it never be benched?
- "a status that needs no bench": which statuses? The chapter only partly says (every 4xx except 429, 401, 402, 404 and 408). It does not say anything about 3xx, 2xx-with-error, or 5xx at that step.
- "Before the three rules, a 402 on a lone deployment ends with no cooldown". Which three rules? I could not find them named anywhere. Later: "A few kinds of failure ... skip all three" and "counts the failure, picks a cooldown time and asks for a decision" is also three things. I do not know whether these are the same three.
- "The deployment's own numbers come first: A deployment with its own allowance gets counted with its number for this error, or with the router's number when it has none for this error". Read twice, still not sure whose number applies when.
- "allowance" vs "allowed-fails policy" vs "allowed-fails counter" vs "retry policy" vs "retry count": five similar terms. I kept mixing them up. "allowed-fails policy: ... not the retry policy" tells me what it is not, not what it is.
- "The router benches once the count goes above the allowance, so an allowance of 1 benches on the second failure, and 0 on the first". "Allowance of 0 benches on the first failure" reads the opposite of "allowance" to me.
- "The router compares its own failure allowance with the library-wide default, 3 unless changed; an equal value counts as unset". Which library? I think this means that someone who deliberately sets 3 gets default behavior; I am not sure that is what is meant, and I would ask whether that is a trap for customers.
- "A deployment with its own allowance ... A lone deployment with only a plain allowance never benches this way". What is a "plain" allowance, as opposed to a per-error one?
- "Any other failure benches the deployment only when over half of at least 5 requests in this server's 60-second window failed, or all of at least 1000 for a lone one". "Over half" and "all" are different tests; why? Also does a lone 429 go here? The "Watch out" says yes; the step before says "A 429 benches unless the deployment is lone", and I had to infer the rest.
- "retryable status: 408, 409, 429 or any status of 500 and above" and then "A status that is not retryable, such as 401 or 404, benches even a lone deployment". It is surprising that not retryable means benched immediately; and 402 and 408 sit between the two rules, so I could not tell what a non-lone 402 does.
- "per-minute counts: each server's own success and failure counts ... normally over a 60-second window from the first count". "From the first count" means it is not a sliding window? "normally" hides what the exception is.
- "A pause shorter than one second stays on one server" and "Redis keeps whole seconds". Why would Redis not hold less than a second? And "servers": I could not tell whether the router is one process or many servers. "this server" and "the router" are used as if different.
- "read interval: how often, at most, a server asks Redis about a bench it does not hold in its own memory". Nowhere says what Redis is; I assumed a shared cache.
- "the error message with its first 50 characters kept and the rest starred": starred means asterisks? I assumed so.
- "Slack alert: ... sent only when Slack alerting is set up and the request did not come through the proxy". What is "the proxy"? The chapter also says "the proxy's check that a key may call a backup model". Is the proxy a different product from the router? Which one does my customer use?
- "health mark: a health check's verdict on a deployment; separate from a bench, it counts only when health-check routing is on". I do not know what health-check routing is. It is defined but I could not tell why it is in this chapter.
- "retry count: ... a retry skips a deployment that failed with a status that is not retryable, such as 400 or 404, if another remains". I could not parse what the retry count is from this definition. Then: "A request that sets its own retry count to 0 turns the policy off; a router-wide 0 does not". Why the difference, and what does a router-wide 0 do?
- "fallback depth: how many backup attempts deep a walk is; the maximum is checked only when a walk starts". And in Watch out: "With the maximum number of fallbacks set to 1 and three backup models listed, all three get tried". That contradicts my reading of "maximum number of fallbacks". I read it three times. The explanation, "only stops each backup from starting fallbacks of its own", is the only thing that resolves it.
- "nested walk" and "A backup call can nest": I understood the words but not why a customer would care, or how deep it can go.
- "attempted set: ... an entry with extra settings counts apart from the bare model name". What are "extra settings"? Later "an order level": what is an order level?
- "An entry that is neither a model name nor a set of settings never counts as tried, so it can run again". What else could an entry be? I cannot picture it.
- "Pinned provider resource" in the figure (and "Some operations keep to the original model group when the request carries a file, batch or job id"). I guess it means a file or batch that lives at one provider, but "pinned" is never defined.
- "access and budget checks: two optional checks whoever builds the router can add". Who builds the router: us, the customer, or the vendor? "optional" for whom?
- "fallback headers: x-litellm-attempted-retries ...". The name "litellm" appears here for the first time and is never explained. Is it the product name?
- "error-list opt-in: a request setting that adds the fallback-errors header". Which setting, and who sets it, the caller?
- "The x-litellm-attempted-fallbacks header can undercount". Whose report would be wrong: the customer's monitoring? I would ask whether we should tell customers not to rely on it.
- "The 'try again in' number is the shortest configured cooldown, not the time left on any cooldown". In the worked example, at 3s the error says "try again in 5" while the real wait is 2s, which is the exact case the warning is about, yet the example does not point this out.
- "When no deployment of a model survives selection, cooldowns included": "survives selection" is odd phrasing; and the chapter says "in the usual case the caller sees it only if no backup model answers". What is the unusual case?
- "Under default settings, a 429 or 5xx never benches a lone deployment unless all of at least 1000 requests in a minute failed": "never ... unless" in the same breath. I read twice.
- "connection-error text: the text 'APIConnectionError' ... an error message containing it stops the bench at the status check". Why would a real connection failure not bench the copy? That feels backwards for an outage story, and the chapter gives no reason.
- "Prometheus metrics: ... each bench marks the deployment as out and adds one to its cooled-down count". Fine, but who reads this, and would a customer's monitoring show a deployment benched?
- The title says "for seconds", but the cooldown time is "the deployment's own setting, else the error's retry-after header, else the router's, 5 seconds by default". Can a long retry-after value from the provider bench a copy for minutes? Not said.
- "5xx" is used without saying it means any 5-hundred status.
- Who would notice: only the 429 for callers and Prometheus numbers are named. I could not tell what an operator sees when a bench happens, or how a customer finds out that a copy is out.

## 3. What I would tell a customer

If one copy of a model starts failing or hitting rate limits, the router can set that copy aside for a few seconds, 5 by default, and send requests to your other copies, then try the backup models you list. If every copy is set aside and no backup answers, your callers get a 429 "try again" error. I would check one thing first: if you have only a single copy of a model, the router will keep sending it traffic through most errors, so I would ask an engineer how your setup behaves before promising automatic failover.
