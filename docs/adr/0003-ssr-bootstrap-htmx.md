# ADR 0003: Server-rendered UI with Bootstrap + htmx

- Status: accepted
- Date: 2026-08-24

## Context

The UI must work well on desktop and mobile browsers, stay simple to deploy, and — a hard
constraint — **use Bootstrap and never Tailwind**. Options:

1. **Server-rendered Jinja2 + Bootstrap + htmx/Alpine**: no JS build step.
2. **Vue/React SPA + JSON API**: richer interactivity, adds a node build pipeline and a
   second app to maintain.
3. **Server-rendered + vanilla JS only**: zero deps, more manual work for dynamic fragments.

## Decision

Server-rendered Jinja2 templates with Bootstrap (vendored or CDN) and htmx for dynamic
fragments (search submit, "load more" result pages, charm inventory edits); Alpine.js for
small client-side state. No Tailwind, no npm, no bundler.

## Consequences

- One process serves everything; the Docker image stays trivial.
- Mobile support comes from Bootstrap's responsive grid, not a separate app.
- Search pagination maps onto htmx partial swaps keyed by `search_states.id`
  (`docs/specs/database-schema.md`).
- Highly interactive future features (e.g. drag-and-drop charm managers) may strain htmx;
  revisit with a new ADR if that becomes real.
