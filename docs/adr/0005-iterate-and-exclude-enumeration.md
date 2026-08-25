# ADR 0005: Iterate-and-exclude result enumeration

- Status: accepted
- Date: 2026-08-24

## Context

The legacy tool streams thousands of raw combinations into a text box (display-capped at 1000,
ingest-capped at 100k). A CP-SAT solver produces solutions differently. Options:

1. **Iterate + exclude**: solve once, render, re-solve with exclusion constraints for
   "load more".
2. **Solution pool**: one solve call returns N feasible sets — simple, but no ranking control
   and a weak pagination story.
3. **Hybrid**: pool of ~50 up front, iterate beyond — more moving parts.

## Decision

Iterate + exclude. Each solve returns one ranked set (objectives: weakest required charm →
spare slots → defense); each "load more" re-solves with prior representative tuples excluded.
Search state (model inputs + exclusion list) is persisted per anonymous session in
`search_states`; htmx posts the search id.

## Consequences

- Natural, ranked pagination with millisecond re-solves on this data size.
- Hard memory bound: we never buffer more than the sets already shown.
- Exclusion lists grow with paging; bounded in practice (users page tens, not thousands) and
  stored as compact representative tuples.
- Equivalence-class expansion happens at render time, so pagination counts *distinct stat
  combinations*, not near-duplicate armor rows.
