# ADR 0006: Charm feature scope — inventory + generated legal charms; save decryption deferred per generation

- Status: accepted
- Date: 2026-08-24

## Context

Legacy charm features span three tiers:

1. **User charm inventory** (`mycharms.txt` + Manage Charms UI) — how players actually search.
2. **Generated legal charms** from the in-game RNG tables (hardcoded in MH3U, CSV in gen 4+)
   — "what charm would I need?" mode.
3. **Save-file decryption import** (PSP crypto in MHP3, Blowfish in MH4U, `SaveData` in
   Gen/GU) — large, platform-specific, per-game work.

## Decision

v1 includes tiers 1 and 2: manual charm inventory per game (persisted server-side per
anonymous session) and solver-side legal-charm generation driven by pack data, with
"weakest legal charm" as the primary objective (`docs/specs/engine-spec.md` §3).

Tier 3 (save decryption) is **deferred and scoped per generation**: it is implemented, if at
all, when that generation's pack ships — not before, not globally. Each generation's roadmap
entry (`docs/roadmap.md`) carries an explicit save-import line item.

## Consequences

- No crypto code in v1; the largest scope risk is removed from the critical path.
- Charm legality data (RNG tables) must be ETL'd — including extracting MH3U/MHP3's hardcoded
  C++ tables into data (`docs/specs/data-pack-spec.md`).
- Users of games without save import type their charms manually; the inventory UI must
  therefore be fast on mobile (add charm in seconds).
