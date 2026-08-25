# Skills — installed, authored, and recommended

Purpose: record which Cursor agent skills this project uses, why, and what each saves in
tokens. Project skills live in `.cursor/skills/` and are committed — they are part of the
knowledge base.

## Project skills (authored, committed in `.cursor/skills/`)

Each skill points at the specs instead of duplicating them — the agent loads one short skill
file instead of re-deriving workflows from three specs.

| Skill | Trigger | Token saving |
|---|---|---|
| `add-game-pack` | "add support for MH4U", "create the mhgu pack", starting a roadmap phase | Encodes the phase checklist + manifest format + "no per-game engine branches" rule; agent skips re-reading three specs to start |
| `extend-solver-model` | "add Charm Up to the solver", "model excavated weapons", "search results look wrong" | Encodes the variable/constraint/objective contract and the banned legacy patterns; prevents re-reading the whole legacy analysis |
| `run-etl` | "rebuild the database", "mhp3 data looks wrong", Docker build data steps | Encodes the per-pack column-map rule (the most likely agent error) and the validation gate |
| `legacy-oracle` | "is this result correct?", "how did Athena's tool do X?" | The file:line index into six C++/CLI repos; agents stop bulk-searching `sources/` |

Maintenance rules:

1. A skill points at specs/ADRs; it never duplicates their content (single source of truth).
2. When an ADR is superseded, update any skill referencing it in the same commit.
3. Keep each `SKILL.md` under 500 lines; detailed content belongs in the specs, one link deep.

## Already installed (user-level) and relevant

| Skill | Use here |
|---|---|
| `grill-me` | Stress-test future design rounds (solver edge cases, UI flows) before implementation. |
| `improve-codebase-architecture` | Reads `CONTEXT.md` + `docs/adr/` — which this repo now provides — to find deepening opportunities once code exists. |
| `create-skill` | Maintaining the project skills above. |

## External skills — evaluated, with concrete recommendations

Reviewed the full [anthropics/skills](https://github.com/anthropics/skills) catalog
(Apache-2.0 examples + source-available document skills). Most are irrelevant to this project
(docx/pdf/pptx/xlsx, Slack, brand/comms). Three are worth attention:

| Skill | Link | Verdict |
|---|---|---|
| **webapp-testing** | https://github.com/anthropics/skills/tree/main/skills/webapp-testing | **Install when Phase 0 UI exists.** Playwright-based testing of a running web app — directly applicable to verifying the FastAPI + htmx UI (search submit, "load more" swaps, mobile viewports). Highest external value for this codebase. |
| **frontend-design** | https://github.com/anthropics/skills/tree/main/skills/frontend-design | **Optional, install when styling the UI.** Design guidance for web interfaces; useful when building the Bootstrap layout. Note: it is framework-agnostic — our ADR 0003 constraints (Bootstrap only, no Tailwind, no build step) still override any suggestion it makes. |
| **skill-creator** | https://github.com/anthropics/skills/tree/main/skills/skill-creator | **Skip.** Redundant with Cursor's built-in `create-skill` skill, which we already used to author the project skills. |

Install location for externals: user-level (`~/.cursor/skills/`), not committed — they are
generic tooling, not project knowledge.

Re-evaluate the ecosystem when implementation starts (e.g. a reputable FastAPI or SQLAlchemy
skill, should one appear); the project-local skills above carry most of the value because they
encode *this* repo's decisions.
