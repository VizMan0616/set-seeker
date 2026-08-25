# ADR 0001: Single monolith with game packs

- Status: accepted
- Date: 2026-08-24

## Context

set-seeker must serve six Monster Hunter generations whose legacy tools differ in data and
small mechanics, but — per the legacy analysis (`docs/legacy-analysis/overview.md`) — share
one copy-pasted search engine. Options considered:

1. **Single monolith + game packs**: one engine, one app; each generation is data + charm
   rules + feature flags.
2. **Monorepo with per-generation services**: shared engine library, one deployable service
   per game.
3. **Monorepo, single deployable** with service-style internal separation.

## Decision

Single monolith + game packs. One FastAPI application, one Docker image, one deployment.
Generations are game packs (manifest + data + flags) consumed by a shared engine with no
per-game code branches beyond reading flags (`docs/specs/engine-spec.md` §6,
`docs/specs/data-pack-spec.md`).

## Consequences

- Simplest possible deployment (hard constraint: one container).
- Engine fixes and UX improvements land for all games at once.
- Adding a generation = adding a pack, not a service (see `docs/roadmap.md`).
- A per-game bug in shared engine code affects all games; mitigated by the per-pack
  known-query validation suite (`docs/specs/data-pack-spec.md`).
