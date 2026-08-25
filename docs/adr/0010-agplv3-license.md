# ADR 0010: AGPLv3 license

- Status: accepted
- Date: 2026-08-24

## Context

The project is open source. Upstream (Athena's ASS) is MIT, which permits reuse in any
license provided the copyright notice is preserved. Options:

1. **MIT**: maximally permissive; anyone may host a closed, improved fork and share nothing.
2. **GPLv3**: copyleft, but triggers on *distribution* — hosting a web app is not
   distribution, so it behaves like MIT for our deployment model.
3. **AGPLv3**: copyleft extended to network use — anyone hosting a modified version must offer
   its source to users of the service. Standard for open-source self-hosted web apps
   (Grafana, Mastodon, Nextcloud).

## Decision

AGPLv3 (`LICENSE`). It is the only option whose copyleft actually applies to a hosted web
application. Upstream attribution is preserved in `NOTICE` and in the vendored
`sources/*/LICENSE` files; derived game data remains under the upstream MIT terms.

## Consequences

- Improvements hosted by anyone must be published — the project's open nature is protected.
- Commercial/closed reuse is effectively blocked without a separate arrangement; accepted.
- All contributions are understood to be AGPLv3; a DCO or CLA can be added later if needed.
- Capcom owns the underlying game data/trademarks; `NOTICE` carries the fan-project
  disclaimer.
