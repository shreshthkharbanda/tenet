# Implicit decisions checklist

When a spec omits a decision, an implementer invents one, and two implementations of the "same" spec
diverge exactly there. The rebuild-test literature (Augment, 2026), the spec-portability study
(arXiv 2608.21208), and Fowler's regeneration experiments all land on the same list: the divergences are
rarely in the main path, they are in these. Walk this list for every module. For each item, either write
the claim, write "not applicable because …" in your head and move on, or write a `{gap}`.

The rule that makes this work: **absence of a safeguard is a behavior.** "No timeout", "no retry",
"input is not validated", "errors are swallowed", "ordering is unspecified" are all claims.

## Inputs and validation
- Which inputs are validated, in what order, and what the first failing check returns (exact message).
- Trimming, case folding, normalization (unicode, paths, URLs, phone numbers), max lengths, encodings.
- Null / empty / missing vs explicit default: are they distinguished?
- Unknown fields: rejected, ignored, or passed through?
- Type coercion ("1" vs 1, "true" vs true).
- Limits: max size, max count, max depth, pagination bounds, and what happens at and past each.

## Errors
- Exact error types, codes, messages, HTTP statuses, exit codes, and which surface sees which.
- Error wrapping: is the cause preserved? Is the message rewritten?
- What is logged on error and at what level; what is never logged (secrets, PII).
- Partial failure: in a batch of N, what happens when item k fails? Stop, skip, or roll back?
- Which errors are swallowed and where.

## Retries, timeouts, backoff
- Timeouts per external call (connect vs read), and what happens when they fire.
- Retry count, which errors are retried, backoff shape, jitter, total deadline, idempotency of the retried call.
- Nested retries (a client that retries inside a loop that retries).
- Circuit breakers, rate limits, and their reset rules.

## Concurrency and ordering
- What runs in parallel, with what bound.
- Locks, transactions, isolation level, and the exact scope of each.
- Ordering guarantees (stable sort? FIFO? by timestamp with ties?).
- Idempotency keys and their lifetime.
- Check-then-act windows the code tolerates.

## State, persistence, caching
- Every read and write, including "incidental" ones (last-seen timestamps, counters, audit rows).
- Cache keys, TTLs, invalidation triggers, what happens on a stale read.
- Transaction boundaries: what is committed together.
- Migrations and compatibility with old data.
- File formats, encodings, newline conventions, atomic writes or not.

## Time, randomness, environment
- Clock source (wall vs monotonic), timezone assumptions, DST handling.
- Random sources and seeds; UUID versions.
- Environment variables read, and at what moment (import time vs call time).
- Locale, platform, and path separator assumptions.

## Configuration
- Every knob, its default, its type, where it is read, and precedence among sources.
- Behavior on invalid or missing config (fail at startup vs at first use).
- Feature flags and what each toggles.

## Security and identity
- Authentication and authorization checks and where they sit in the call order.
- What is trusted from the caller without checking.
- Secrets handling (never copy them into the spec).
- Input that reaches a shell, a query, a path, a template, or a deserializer.

## Interfaces and compatibility
- Public names that are bound at runtime (factory assignments, setattr loops, registries, decorators,
  generated tables): every one, with where it is bound.
- Wire formats, field order where it matters, versioning, deprecations still honored.
- Library behaviors that leak through (hash algorithms and costs, serialization quirks, default headers).
- Validation-library output a caller sees: the exact error text a schema or validation library
  produces for each invalid input this code accepts, and its coercions (int to float, str to int,
  tuple to list) that show up in later messages or values. Run the validator once and copy the text.
- Exit codes, signals handled, stdout vs stderr.

## Resource limits
- Memory and size bounds, streaming vs buffering, max connections, pool sizes, queue depths.
- What happens at exhaustion.

## Observability
- Log lines that carry data callers depend on (exact formats), metrics names, trace propagation.

## Lifecycle
- Startup order and failures, readiness, graceful shutdown, what is flushed, what is lost.

## Sibling paths
- When one mechanism behaves differently across sibling entry points (chat vs other endpoints, sync vs
  async, streaming vs non-streaming, router vs direct SDK use), state the difference side by side and
  its consequence for a caller ("the concurrency slot is held for the life of a chat stream but released
  when a Responses stream object is returned, so open Responses streams are not capped"). Stating each
  path's mechanism separately is not enough: readers do not diff them.

## Dead and conditional code
- Branches that cannot be reached, flags that are always on, compatibility shims: say so. A reviewer
  needs to know what is live.
