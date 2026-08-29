# Legacy analysis — overview and root causes

Analysis of the six vendored Athena's ASS repositories (`sources/`). Per-repo deep dives:
[MHFU](MHFU-ASS.md) · [MHP3](MHP3-ASS.md) · [MH3U](MH3U-ASS.md) · [MH4](MH4-ASS.md) ·
[MH4U](MH4U-ASS.md) · [MHGen](MHGen-ASS.md) · [MHGU](MHGU-ASS.md).

## What the legacy tools actually are

- **C++/CLI WinForms** (managed C++: `ref struct`, `gcnew`, `System::Windows::Forms`) — *not* C#.
  .NET Framework 2.0 (MHFU) through 4.5 (MHGU); VS2008–VS2017 toolsets.
- **MIT licensed**, Copyright (c) 2017 AthenaADP. Reuse of code and data is permitted with
  attribution (see `NOTICE`).
- **One engine, forked per game.** Same class names (`Query`, `Solution`, `ThreadSearchData`,
  `CharmDatabase`, `LoadedData`), same worker structure, same UI patterns across all repos.
  Per-game differences are: the dataset, charm rules, and small mechanics (MH4/4U excavated
  gear + weapon loop, MHGU Charm Up / Skill +2). This is the single strongest argument for
  set-seeker's **one engine + game packs** architecture (see `docs/adr/0001`).

## The shared search pipeline

Every repo implements the same five steps:

1. **Formulate query** — up to `NumSkills` desired skills (5 in MHFU, 6 in MHP3/MH3U/MH4,
   7 in MH4U/MHGen/MHGU; static combo boxes), HR/village★, gender, hunter type, weapon
   slots, options (event gear, bad skills, piercings/arena, charm mode).
2. **Relevance + dominance pruning** (`LoadedData::GetRelevantData`) — keep only armor and
   decorations that grant requested skills or top-tier slots; drop pieces strictly dominated
   by another piece on all relevant skills + slots. *This is the real pruning.* Athena keeps
   both `inf_*` (relevant) and `rel_*` (skyline) for Advanced Search; set-seeker does the
   same — see `docs/specs/engine-spec.md` §1.
3. **Fan out workers** — one `BackgroundWorker` per head-equivalence (MHFU) or per charm
   template (MHP3 onward); up to `ProcessorCount` run concurrently.
4. **Brute-force enumeration** — 5 nested loops over head×body×arms×waist×legs (MH4/4U add a
   6th over weapons). Each combo allocates a `Solution` and runs `MatchesQuery`: sum skill
   points (with Torso Inc multiplier), then **greedy decoration fill** (3-slot → 2-slot →
   1-slot jewels), then threshold check, optional bad-skill fix and charm reduction.
5. **Dump results** — dedupe via a weak hash, store up to 100k solutions (MH4+), render into a
   single monolithic TextBox/RichTextBox, display-capped at 1000.

## Root causes of the freezes and slowdowns

Ranked by impact. Citations use `repo/path:lines`.

1. **Combinatorial enumeration with no mid-tree pruning.**
   The nested loops enumerate the full cartesian product of the pruned lists, once *per charm
   template*. Effective cost is O(C · H·B·A·W·L) with C charm templates; each candidate pays a
   greedy decoration pass. There is no branch-and-bound: a partial combo that can never reach
   the skill thresholds is never cut early.
   - `MHFU-ASS/MH Armor/Form1.h:1353-1418` (4-deep over equivalence classes + 5-deep expansion)
   - `MHP3-ASS/Form1.h:1874-1926` (full 5-deep, no equivalence classes)
   - `MH4U-ASS/Form1.h:2490-2553`, `MHGU-ASS/Form1.h:~2779+` (5–6 deep)

2. **Result caps disabled or set absurdly high.**
   - MHP3's per-worker early exit at `MAX_LIMIT` is **commented out**
     (`MHP3-ASS/Form1.h:1916-1921`) — the search always exhausts the space.
   - MH4/4U/Gen/GU keep ingesting up to `MaxSolutions = 100000` while the display only ever
     shows 1000 (`MH4U-ASS/Form1.h:81,2051-2057`). CPU and memory are spent on results no one
     will see.

3. **Monolithic result rendering.**
   All results are concatenated into one giant `StringBuilder` and assigned to a single
   TextBox/RichTextBox (`MHFU-ASS/Form1.h:1198-1282`, `MH3U-ASS/Form1.h:1789-1936`,
   `MH4U-ASS/Form1.h:~2019-2200`). The "showing first 1000" message does not truncate the
   string being built (`MHFU-ASS/Form1.h:1271-1278`). This — not the search threads — is what
   visibly freezes the UI.

4. **Allocation pressure in the hot loop.**
   `gcnew Solution` (and in MHFU `gcnew EquivalenceSolution`) for **every candidate combo**
   (`MHFU-ASS/Form1.h:1381,1400`, `MH4U-ASS/Form1.h:2522-2529`) — millions of short-lived
   managed objects, constant GC.

5. **Weak progress reporting and cancellation.**
   Progress only updates at the head×body level (`MH4U-ASS/Form1.h:2494-2507`), so the UI can
   sit silent for minutes. Cancellation is `CancelAsync` + a flag checked at one loop level;
   in-flight workers finish their current charm template regardless. `MessageBox::Show` is
   called from worker threads (`MH3U-ASS/Form1.h:2190-2193`, `MH4U-ASS/Form1.h:2545-2548`),
   which can deadlock the UI.

6. **Per-game aggravating factors.**
   - MHP3/MH3U: charm table RNG simulation at startup (`CharmDatabase::GenerateCharmTable`).
   - MHGU: ~1150–1240 armor pieces per slot — roughly double MHGen — with the same algorithm.
   - MHFU: dominance pruning is O(n²) list scans (`LoadedData.cpp:137-159`); equivalence
     classes are built on the UI thread before workers start (`Form1.h:1047`).

## Patterns to never repeat in set-seeker

| Legacy pattern | Our rule |
|---|---|
| Enumerate full cartesian products | Model as CP-SAT; the solver prunes infeasible partial assignments natively (`docs/specs/engine-spec.md`) |
| One worker per charm template, unbounded | Charm is a decision variable (or a small bounded set of template solves), not a fan-out dimension |
| Search first, cap later | Hard per-request budgets: solver time limit + max solutions, set *before* solving |
| Buffer all results, render one text blob | Iterate + exclude pagination; render one page of structured HTML at a time |
| `gcnew` per candidate | Solver works on immutable in-memory pack data; no per-candidate allocation |
| Cancel via a flag checked occasionally | Solver time limits + request-scoped cancellation |
| Greedy decoration fill inside the match check | Decorations are solver variables with slot-capacity constraints |
| UI-thread work before/during search | All search happens in the solver, off the request path, with streaming responses |

## What is worth keeping

- **Relevance + dominance pruning** before solving: shrinking the variable domains is still the
  biggest single win, and it is cheap. Port the *idea* (drop pieces dominated on relevant
  skills + slots), not the O(n²) implementation.
- **MHFU's equivalence classes** (armor pieces identical on slots + relevant skills collapse
  into one): equivalent to choosing a *representative* per class in the solver model and
  expanding afterwards. Documented in `docs/specs/engine-spec.md`.
- **Charm legality data**: the RNG table knowledge (hardcoded in MH3U, CSV in MH4+) is the
  product of years of community datamining. We reuse the data, not the simulation code.
- **The data files themselves**: complete, community-verified datasets for six games — the seed
  for our ETL (`docs/specs/data-pack-spec.md`).
