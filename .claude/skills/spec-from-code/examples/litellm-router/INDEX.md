# LiteLLM Router specification

Behavioral specification of the LiteLLM Router (`litellm/router.py` and `litellm/router_utils/**`) at
commit `93b79d2587d186fb7266556a34a22d03f187a3da` (2026-10-19). Recovered from the code and its tests;
status per module below. Code is the implementation, this is the description of what it does.

The Router is the SDK's load-balancing and reliability layer: it picks a deployment for each call to a
model group, binds it into the provider call, retries within the group, falls back to other groups and
cools down failing deployments. The proxy server and the provider SDK are context, not specified here.

## How to read this
1. `00-overview.md` for purpose, the system map, and the main paths end to end (15 minutes).
2. `01-interfaces.md` for the exact external contract: constructor settings, call methods, per-request
   control kwargs and the error catalog.
3. The modules on the main paths, in the order listed in the overview's Reading order:
   router-setup, router-selection, router-calls, router-dispatch, failure-handling, router-deployments.
4. `02-data.md` (cache keys, records, invariants) and `03-config.md` (every setting, default and
   precedence) as reference. There is no `04-operations.md`: the Router is a library with no build,
   deploy or run surface of its own.
5. `_meta/gaps.md` for what the code does not reveal and someone must decide, and
   `_meta/suspected-defects.md` for behavior that looks unintended.

Claim IDs look like `[RSELECT-044]`. Each claim is one observable fact with a source reference;
`{confirmed}` was read in code or pinned by a test, `{inferred}` rests on a partial read or a dependency,
`{gap}` is an open question. Cross-references between specs use the same IDs.

## Status
| Spec | Claims (confirmed / inferred / gap) | File coverage | Held-out fidelity | Rebuild | Status |
|---|---|---|---|---|---|
| 00-overview.md | 15 / 1 / 0 | n/a | n/a | n/a | draft |
| 01-interfaces.md | 307 / 4 / 2 | n/a | pending | pending | draft |
| 02-data.md | 132 / 22 / 4 | n/a | pending | pending | draft |
| 03-config.md | 156 / 8 / 3 | n/a | pending | pending | draft |
| modules/router-setup.md | 263 / 32 / 6 | 100% | pending | pending | draft |
| modules/router-calls.md | 175 / 13 / 6 | 100% | pending | pending | draft |
| modules/router-dispatch.md | 225 / 20 / 7 | 100% | pending | pending | draft |
| modules/router-deployments.md | 176 / 9 / 7 | 100% | pending | pending | draft |
| modules/router-selection.md | 198 / 17 / 6 | 100% | pending | pending | draft |
| modules/failure-handling.md | 186 / 20 / 6 | 100% | pending | pending | draft |
| modules/deployment-limits.md | 138 / 9 / 7 | 100% | pending | pending | draft |
| modules/affinity-checks.md | 148 / 5 / 8 | 100% | pending | pending | draft |
| modules/routing-contracts.md | 146 / 5 / 6 | 100% | pending | pending | draft |
| modules/request-targets.md | 195 / 7 / 6 | 100% | pending | pending | draft |

Totals: 2,706 claims (2,460 confirmed, 172 inferred, 74 gaps); 45 suspected-defect claims across the
ten modules. File coverage is the share of each module's in-scope files cited by at least one claim.

Status meanings: validated (held-out fidelity >= 90%, no held-out contradictions), provisional (>= 75%),
weak (< 75%), draft (not yet probed).

## Where to look first
- Why a request went to a particular deployment: `modules/router-selection.md`, "Healthy-deployment
  pipeline" and "Async selection".
- Why a deployment stopped receiving traffic: `modules/failure-handling.md`, "Cooldown decision".
- What happens after a provider error: `00-overview.md` main paths 2 and 3.
- What a setting does and its default: `03-config.md`.
- Every error a caller can receive: `01-interfaces.md`, "Error catalog".

## Re-validating
Run `gate.py specs --repo . --round <n>` from the spec-from-code skill. Stale commit warnings mean the
code moved; re-run extraction with `--update`.
