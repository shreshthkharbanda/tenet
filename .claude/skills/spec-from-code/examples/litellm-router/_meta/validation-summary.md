# Validation report (round 2)

Fidelity = share of probes whose spec-only answer agrees with the code-derived reference answer.
Held-out probes are never shown to spec writers; revision probes drive fixes. No-spec control is the share answered correctly with no spec at all (prior knowledge); lift is overall fidelity minus that. Low lift means the probes test what a model already knows, not the spec. Status: validated >= 0.90 held-out fidelity with zero held-out contradictions; provisional >= 0.75; weak otherwise.

| Module | Probes | Revision fidelity | Held-out fidelity | Held-out contradictions | Gaps | Invalid probes | Status | Delta vs prev | No-spec control | Lift |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| affinity-checks | 25 | 100% | 90% (9/10, 95% lower 60%) | 0 | 1 | 0 | validated | +20% | 0% | +96% |
| deployment-limits | 25 | 100% | 90% (9/10, 95% lower 60%) | 1 | 0 | 0 | provisional | -10% | 8% | +88% |
| failure-handling | 25 | 100% | 90% (9/10, 95% lower 60%) | 0 | 1 | 0 | validated | -10% | 16% | +80% |
| request-targets | 25 | 100% | 100% (10/10, 95% lower 72%) | 0 | 0 | 0 | validated | +10% | 20% | +80% |
| router-calls | 25 | 100% | 100% (10/10, 95% lower 72%) | 0 | 0 | 0 | validated | +10% | 40% | +60% |
| router-deployments | 25 | 93% | 100% (10/10, 95% lower 72%) | 0 | 0 | 0 | validated | +0% | 44% | +52% |
| router-dispatch | 25 | 100% | 100% (10/10, 95% lower 72%) | 0 | 0 | 0 | validated | +0% | 25% | +75% |
| router-selection | 25 | 100% | 90% (9/10, 95% lower 60%) | 0 | 1 | 0 | validated | +0% | 16% | +80% |
| router-setup | 25 | 100% | 100% (10/10, 95% lower 72%) | 0 | 0 | 0 | validated | +0% | 40% | +60% |
| routing-contracts | 25 | 100% | 100% (10/10, 95% lower 72%) | 0 | 0 | 0 | validated | +10% | 0% | +100% |
