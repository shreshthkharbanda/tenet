# Research basis

Each rule in this skill traces to a published result or a documented practice. Knowing why a rule exists
lets you apply it with judgment rather than by rote.

| Rule in this skill | Source | What it found |
|---|---|---|
| Hierarchical spec (short overview, exhaustive leaves); verify by reconstruction | PROOF, "From Reading Code to Reading Spec" (arXiv 2609.06383) | Codebases can be managed through a hierarchical natural-language spec; semantic equivalence is shown by rebuilding from the spec alone |
| Blind reimplementation as the fidelity oracle; iterative refinement; specs constrain what, not how | AfterVibe (Paltenghi and Chandra, arXiv 2607.09900) | 72 projects; mean regeneration score 5.06/6, 5.74 after refinement; strong specs are abstract about implementation and precise about behavior |
| Code-derived probes answered from the spec alone; held-out set; contradiction vs gap; repair regression; observability rule | Fidelity Probes (AWS AI Labs, arXiv 2605.17246) | Fidelity rose 0.59 to 0.89 over revisions on a 12k-line system; fixes can regress other probes, so score a fixed held-out set |
| confirmed / inferred / gap on every claim; traceability matrices; questions and gaps as first-class outputs | Reversa (arXiv 2605.18684) | 517 claims on a legacy system; explicit confidence stops fragile inferences from reading as facts |
| Language-neutral spec covering behavior, identifiers, control flow, conditions, side effects, data dependencies, intent; AST-derived grounding | Code2Text2Code (arXiv 2605.25232) | Direct code-to-code translation drifts; a neutral textual spec in the middle preserves semantics and traceability |
| Round-trip (code -> text -> code) as the equivalence primitive | Round-Trip Correctness (Allamanis et al., arXiv 2402.08699) | Semantic equivalence after a round trip tracks model quality without human labels |
| Three-level verification: agent report vs log vs files; mechanical checks over written instructions; passing tests is not proof | Rebuild Dossier (Fawcett, arXiv 2608.23616) | A rule-following agent failed a held-back test while a rule-breaking one passed everything; automated checks, not instructions, produced compliance |
| Agent-neutral, self-contained, retrieval-friendly specs | Specification Portability (arXiv 2608.21208) | The same spec fed to different agents produced wildly different quality (one cross-agent case near zero); retrieval-based ingestion was on every agent's Pareto frontier |
| Implicit-decisions checklist; rebuild test | Augment Code, "The Spec as Source of Truth" (2026) | Regeneration divergences trace to implicit decisions: error codes, caching, library choices, auth formats |
| Short index entry point; structured docs as system of record; mechanical freshness and cross-link checks | OpenAI, "Harness engineering" (Feb 2026) | One large blob rots; an index plus structured docs with mechanical checks for coverage, freshness, and links stays current |
| Spec sufficient for an agent to implement, with no code shipped | StrongDM Attractor NLSpec (Feb 2026); Monperrus, "The Specification Is the Program" (IEEE Software 2026) | A 35k-word spec with no code yields working implementations; equivalence defined as passing the same tests |
| Make specs more specific to improve regeneration repeatability; separate functional from technical design; beware model-driven-development overhead | Fowler site, SDD tools comparison (Oct 2025) | Regeneration from one spec varied; specificity helped; spec-as-source risks MDD's rigidity plus LLM non-determinism |
| Precision ladder: literals, ordered checks, tables, predicates before prose | Dijkstra EWD667 (1978); Brooker, "Natural language programming" (Dec 2025) | Prose is ambiguous (a common Paxos bug comes from it); use formal constructs where exactness matters and prose as the interface |
| Existing docs are evidence for inferred, not confirmed | Civic Innovations legacy case (Mar 2026); Fidelity Probes | Documentation quality dominated spec quality, and documentation drifts from code |
