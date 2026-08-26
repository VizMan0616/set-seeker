# Database schema spec

SQLite today; **MariaDB must be a drop-in replacement later** (`docs/adr/0004`). That
constraint shapes everything below.

## Portability contract (hard rules)

1. **All access goes through a repository layer** (DAO pattern). No SQL outside repositories;
   no ORM entities leak into the solver or templates.
2. **SQLAlchemy Core** (not the ORM's lazy-loading patterns) with the connection URL from
   config (`DATABASE_URL`, default `sqlite:///data/setseeker.db`). Swapping to MariaDB is a
   config change (`mysql+pymysql://…`), not a code change.
3. **Portable column types only**: `Integer`, `BigInteger`, `String(n)`, `Text`, `Boolean`,
   `DateTime`, `ForeignKey`. No SQLite-specific types, no `AUTOINCREMENT` keyword, no
   `INSERT OR REPLACE` — use SQLAlchemy upsert helpers.
4. **Migrations via Alembic** from the first schema; ETL rebuilds game-data tables through
   migrations' downgrade/upgrade, never ad-hoc DDL.
5. Two logical data groups, one database file: **game data** (read-only at runtime, rebuilt by
   ETL) and **user data** (sessions, charm inventories — never touched by ETL).

## Schema

### Game data (ETL-owned)

```sql
games (
  id            INTEGER PRIMARY KEY,
  code          String(8)   NOT NULL UNIQUE,      -- mhfu, mhp3, mh3u, mh4, mh4u, mhgen, mhgu
  name          String(64)  NOT NULL,
  generation    Integer     NOT NULL,
  features      Text        NOT NULL              -- JSON feature-flag blob from the pack manifest
);

skill_trees (
  id            INTEGER PRIMARY KEY,
  game_id       INTEGER NOT NULL REFERENCES games(id),
  name_en       String(64)  NOT NULL,
  name_ja       String(64),
  category_tag  String(32)                        -- from tags.txt
);

skills (                                          -- threshold rows: "Attack Up (L)" = 20 pts
  id            INTEGER PRIMARY KEY,
  tree_id       INTEGER NOT NULL REFERENCES skill_trees(id),
  name_en       String(64)  NOT NULL,
  name_ja       String(64),
  points        Integer     NOT NULL,             -- signed; negative = bad skill
  is_negative   Boolean     NOT NULL DEFAULT 0
);

armor_pieces (
  id            INTEGER PRIMARY KEY,
  game_id       INTEGER NOT NULL REFERENCES games(id),
  slot          Integer     NOT NULL,             -- 0=head 1=body 2=arms 3=waist 4=legs
  name_en       String(96)  NOT NULL,
  name_ja       String(96),
  rarity        Integer     NOT NULL,
  slots         Integer     NOT NULL,             -- 0..3
  gender        Integer     NOT NULL,             -- 0=m 1=f 2=both
  hunter_type   Integer     NOT NULL,             -- 0=blade 1=gun 2=both
  hr_required   Integer     NOT NULL DEFAULT 0,
  village_stars Integer     NOT NULL DEFAULT 0,
  defense       Integer     NOT NULL,
  max_defense   Integer     NOT NULL,
  res_fire      Integer NOT NULL, res_water Integer NOT NULL, res_ice Integer NOT NULL,
  res_thunder   Integer NOT NULL, res_dragon Integer NOT NULL,
  torso_inc     Boolean     NOT NULL DEFAULT 0,
  is_event      Boolean     NOT NULL DEFAULT 0
);

armor_skills (
  armor_id      INTEGER NOT NULL REFERENCES armor_pieces(id),
  tree_id       INTEGER NOT NULL REFERENCES skill_trees(id),
  points        Integer NOT NULL,
  PRIMARY KEY (armor_id, tree_id)
);

decorations (
  id            INTEGER PRIMARY KEY,
  game_id       INTEGER NOT NULL REFERENCES games(id),
  name_en       String(96)  NOT NULL,
  name_ja       String(96),
  rarity        Integer NOT NULL,
  size          Integer NOT NULL,                 -- 1..3 slots consumed
  hr_required   Integer NOT NULL DEFAULT 0,
  village_stars Integer NOT NULL DEFAULT 0,       -- second progression path (migration 0002)
  is_event      Boolean NOT NULL DEFAULT 0
);

decoration_skills (
  decoration_id INTEGER NOT NULL REFERENCES decorations(id),
  tree_id       INTEGER NOT NULL REFERENCES skill_trees(id),
  points        Integer NOT NULL,                 -- negative allowed (dual-skill jewels)
  PRIMARY KEY (decoration_id, tree_id)
);

charm_types (                                     -- gen4+ charm generation tables
  id            INTEGER PRIMARY KEY,
  game_id       INTEGER NOT NULL REFERENCES games(id),
  code          String(16) NOT NULL,              -- mystery, shining, ancient, ...
  max_slots     Integer NOT NULL
);

charm_skill_ranges (                              -- legal point ranges per type/tree
  charm_type_id INTEGER NOT NULL REFERENCES charm_types(id),
  tree_id       INTEGER NOT NULL REFERENCES skill_trees(id),
  skill_slot    Integer NOT NULL,                 -- 1 or 2 (first/second charm skill)
  min_points    Integer NOT NULL,
  max_points    Integer NOT NULL,
  PRIMARY KEY (charm_type_id, tree_id, skill_slot)
);

charm_slot_thresholds (                           -- *_slots.csv
  charm_type_id INTEGER NOT NULL REFERENCES charm_types(id),
  fulfillment   Integer NOT NULL,
  slots         Integer NOT NULL,                 -- 1..3
  PRIMARY KEY (charm_type_id, fulfillment)
);

mh3u_charm_tables (                               -- extracted from hardcoded C++ (gen 3)
  id            INTEGER PRIMARY KEY,
  game_id       INTEGER NOT NULL REFERENCES games(id),
  table_index   Integer NOT NULL,                 -- 1..17
  tree_id       INTEGER NOT NULL REFERENCES skill_trees(id),
  skill_slot    Integer NOT NULL,
  max_points    Integer NOT NULL
);
```

### User data (runtime-owned, never ETL'd)

```sql
sessions (
  id            TEXT PRIMARY KEY,                 -- uuid, issued as long-lived cookie
  created_at    DateTime NOT NULL,
  last_seen_at  DateTime NOT NULL
);

user_charms (
  id            INTEGER PRIMARY KEY,
  session_id    TEXT NOT NULL REFERENCES sessions(id),
  game_id       INTEGER NOT NULL REFERENCES games(id),
  slots         Integer NOT NULL,                 -- 0..3
  skill1_tree   INTEGER REFERENCES skill_trees(id),
  skill1_points Integer,
  skill2_tree   INTEGER REFERENCES skill_trees(id),
  skill2_points Integer,
  note          String(128)
);

search_states (                                 -- iterate+exclude pagination state
  id            TEXT PRIMARY KEY,                 -- search id used by htmx "load more"
  session_id    TEXT NOT NULL REFERENCES sessions(id),
  game_id       INTEGER NOT NULL REFERENCES games(id),
  query_json    Text NOT NULL,
  exclusions    Text NOT NULL DEFAULT '[]',       -- JSON list of shown representative tuples
  created_at    DateTime NOT NULL
);
```

## Indexes

| Table | Index | Why |
|---|---|---|
| `armor_pieces` | `(game_id, slot, hunter_type, gender)` | domain pruning per query |
| `armor_pieces` | `(game_id, hr_required)` | progression filter |
| `armor_skills` | `(tree_id, armor_id)` | "pieces granting tree X" lookup during pruning |
| `skills` | `(tree_id, points)` | threshold resolution |
| `decorations` | `(game_id, size)` | slot-bucket fill |
| `decoration_skills` | `(tree_id, decoration_id)` | relevant-jewel lookup |
| `charm_skill_ranges` | `(charm_type_id, tree_id)` | legal-charm generation |
| `user_charms` | `(session_id, game_id)` | inventory per user per game |
| `search_states` | `(session_id, created_at)` | session cleanup |

The solver never queries these tables in its hot path: pack data is loaded into immutable
in-memory structures at startup (the full corpus is ≤2.5 MB per game). The relational schema
serves the browsing UI, ETL, and user data.

## MariaDB swap checklist (when the time comes)

1. Set `DATABASE_URL=mysql+pymysql://…`; run `alembic upgrade head`.
2. Re-run ETL against MariaDB (same code path, idempotent).
3. Revisit `search_states.exclusions` (JSON text) if size becomes an issue — portable either way.
4. Only then consider MariaDB-specific tuning (engines, collations for Japanese names —
   `utf8mb4` required).
