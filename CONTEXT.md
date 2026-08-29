# CONTEXT — set-seeker

## What this project is

**set-seeker** is a web-based, cross-platform armor set search tool for classic Monster Hunter
games (generations 2 through "Generations Ultimate"). It is inspired by — and partially derived
from — **Athena's Armor Set Search (ASS)**, a Windows-only C++/CLI WinForms application that was
the reference tool for building armor sets in pre-World Monster Hunter games.

The legacy tool works, but it is Windows-only, freezes or saturates the PC during searches, and
dumps results into an unpaginated text box. set-seeker reimplements the same core purpose —
*the user enters desired armor skills; the tool outputs complete armor sets (pieces + decorations
+ talisman) that activate those skills* — as a web application that runs anywhere, stays
responsive, and is simple to deploy with Docker.

## Domain language

| Term | Meaning |
|------|---------|
| **Armor set** | A combination of 5 armor pieces: head, body, arms, waist, legs. |
| **Skill / ability** | Armor pieces grant points toward *skill trees* (e.g. "Attack"). Reaching a point threshold activates a named *skill* (e.g. "Attack Up (L)" at 20 points). The legacy code calls skill trees "abilities". |
| **Negative / bad skill** | Skill trees can go negative; crossing a negative threshold activates a penalty skill (e.g. "Attack Down (S)"). Searches usually avoid these. |
| **Slots** | Armor pieces, weapons, and talismans have 0–3 decoration sockets ("O--" notation). |
| **Decoration / jewel** | Craftable gems socketed into slots; grant skill points. Sizes 1–3. |
| **Talisman / charm** | An equipment slot (gen 3 onward) with 0–3 slots and up to 2 skill trees. Gen 2 (MHFU) has **no talismans**. |
| **Charm table** | In MH3U/MHP3, the in-game RNG that determines which charms a save file can ever obtain. 17 known tables in MH3U. Gen 4+ models charm legality via per-rarity generation tables (Mystery/Shining/Ancient/etc.). |
| **Torso Inc / Torso Up** | A flag on some armor pieces (often legs or helm, not the chest) that doubles the body's skill points, including body-socketed decorations. The pack's skill-tree name is the UI label (Torso Inc or Torso Up). |
| **Excavated gear** | MH4/MH4U randomized equipment ("relics") the user can register manually. |
| **Charm Up / Skill +2** | MHGU mechanics that double charm skills or add +2 points to all skills. |
| **HR / village★** | Athena **quest-star** gates (not in-game HR 1–999) that filter equipment. Caps are per pack — see below. |
| **Desired skills max** | How many activated skills the search form may request. Athena `Form1.h` `NumSkills` (fixed combo boxes, **no** add/subtract). Per pack — see table. |
| **Hunter type** | Blademaster or Gunner; most armor is type-specific. |
| **Game pack** | Our abstraction: one generation's data (armor, skills, decorations, charm rules) + feature flags, consumed by a single shared search engine. |

### Progression caps (authoritative)

Copied from Athena `nudHR` / `nudElder` maxima and `Form1.h` `NumSkills`.
Use these when writing a pack manifest; do not re-derive from armor rows
(those store sentinel 10 or 99 for “closed path”). Desired-skill count is
Athena’s static combo-box count, not a later add/subtract UI. Full citations:
`docs/specs/data-pack-spec.md`.

| Pack | Village ★ | Guild / HR | Desired skills | Rank band |
|---|---|---|---|---|
| mhfu | 9 | 9 | 5 | G-rank |
| mhp3 | 6 | 6 | 6 | High-rank |
| mh3u | 10 | 8 | 6 | G-rank hub ★8, village 10★ |
| mh4 | 7 | 8 | 6 | High-rank (hub ★8) |
| mh4u | 10 | 12 | 7 | G-rank hub ★9–12 (G1–G4) |
| mhgen | 6 | 8 | 7 | High-rank |
| mhgu | 10 | 13 | 7 | G-rank hub ★9–13 |

## Hard constraints

- **Frontend CSS framework is Bootstrap. Tailwind is banned** — do not introduce it by any means.
- **No JavaScript build step.** Server-rendered HTML (Jinja2) + htmx/Alpine for interactivity.
- **Deployment must stay simple: one Docker container.** No database-as-a-service, no required
  external services. SQLite today; the repository layer must keep a future MariaDB swap cheap.
- **Open source: AGPLv3** (see `LICENSE`), with upstream MIT attribution in `NOTICE`.
- **English UI**; game-data names are stored bilingually (English/Japanese) from day one.
- Mobile browsers are first-class: the UI must be fully usable on a phone.

## Architecture in one paragraph

One Python/FastAPI monolith serves server-rendered pages. Armor set search is modeled as a
constraint-satisfaction problem solved with Google OR-Tools CP-SAT — not a port of the legacy
brute-force loops. Results are produced one solve at a time using iterate-and-exclude (each
"load more" re-solves with prior solutions excluded), ranked by objectives (weakest required
charm first, then defense/spare slots). Game data ships in SQLite, built by an ETL step from the
legacy CSV data packs. Users are anonymous (long-lived session cookie) and can register their
charm inventories per game.

## Where things live

- `sources/` — the six legacy ASS repositories as **local-only** git clones (gitignored, not
  part of this repo; restore instructions in `SOURCES.md`). **Reference only; never modified.**
- `docs/legacy-analysis/` — what the legacy code does and why it is slow (root-cause analysis).
- `docs/specs/` — the contracts future implementation must follow (engine, data packs, DB schema).
- `docs/adr/` — architecture decision records. Decisions there are settled; changing one means
  writing a new ADR, not editing the old one.
- `docs/roadmap.md` — generation rollout order.
- `AGENTS.md` — entry point for AI agents: which docs to read for which task.

## Current state

Phase 0/1 (MHFU) and Phase 2 (MHP3) ship in one image: FastAPI + Jinja2/Bootstrap/htmx,
SQLite via SQLAlchemy Core, CP-SAT search, Advanced Search, charm inventory (MHP3),
multi-stage Dockerfile that ETLs `packs/mhfu/` and `packs/mhp3/`. Next: MHGU
per `docs/roadmap.md`.
