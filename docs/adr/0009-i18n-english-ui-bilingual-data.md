# ADR 0009: English UI, bilingual data schema

- Status: accepted
- Date: 2026-08-24

## Context

The legacy data files already carry English and Japanese names for armor, skills, and
decorations, plus language overlay folders. Two separable concerns: **data names** and
**UI strings**. The user clarified these are independent — a Japanese UI is not required for
Japanese game-data names to be useful. MHP3 was never officially localized: its English names
are fan translations.

## Decision

- **Schema stores `name_en` and `name_ja` from day one** on all named game entities
  (`docs/specs/database-schema.md`). Adding locales later is a data/overlay job, not a
  migration.
- **v1 UI is English only.** No i18n framework in templates yet; UI strings are plain English.
- **MHP3 English names are marked as fan translations** in the pack manifest
  (`translation: fan`); this is a data-quality caveat, displayed where relevant, not a UI
  language feature.

## Consequences

- Zero i18n engineering cost in v1; no re-ETL needed to add Japanese names later.
- Fan-translation marking sets user expectations for MHP3 naming mismatches vs other sources.
- If a second UI language is ever added, it requires a template-string extraction pass — a
  known, bounded cost accepted by this ADR.
