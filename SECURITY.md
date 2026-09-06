# Security policy

## Supported versions

| Version | Supported |
|---------|-----------|
| Latest release | Yes |
| Older releases | No — upgrade to the latest tagged release |

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report security issues privately using one of:

1. **[GitHub Security Advisories](https://github.com/VizMan0616/set-seeker/security/advisories/new)**
   (preferred — allows coordinated disclosure)
2. Email the maintainer at **josevizcaya0616@proton.me** with subject
   `set-seeker security`

Include:

- Description of the vulnerability and potential impact
- Steps to reproduce (proof of concept if available)
- Affected version or commit hash
- Your suggested fix, if any

## Response timeline

- **Acknowledgment** within 72 hours
- **Initial assessment** within 7 days
- **Fix and advisory** as soon as a patch is ready; critical issues may trigger
  an out-of-band [hotfix release](CONTRIBUTING.md#hotfix-policy)

## Scope

In scope:

- set-seeker application code (`app/`)
- Deployment configuration shipped in this repository
- Data handling (sessions, charm inventories, SQLite storage)

Out of scope:

- Upstream Athena's ASS repositories (report to upstream maintainers)
- Third-party CDN assets (Bootstrap, htmx, Alpine — report to respective projects)
- Social engineering or physical attacks

## Safe harbor

We support good-faith security research. Do not access data belonging to others,
perform denial-of-service attacks, or disrupt production services. Test against
your own local or staging instance.
