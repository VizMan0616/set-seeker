# Orchestrator prompt (copy everything below the line)

Use this in **one** new chat with Multitask / subagents enabled. You are the parent.
You do **not** implement. You launch children and you own the waits.

---

```
GENERATION: <mhfu|mhp3|mh3u|mh4|mh4u|mhgen|mhgu>
SKIP_ENGINE_UI: <yes|no>   # yes = pack adds no new engine flag; skip steps 4–5
NOTES:
```

## Your job

Run the generation pipeline. Launch **exactly one** child at a time (or a
fix-child after a review). Never start `engine-ui` until `etl` is merged and
its reviewer has **Verdict: approve**. Never start two implementers in parallel.

Each child is a fresh Task/subagent. Its entire user prompt is:

1. The filled [implement.md](implement.md) or [review.md](review.md) template
   (same `GENERATION`, the `SCOPE` for that step).
2. If a reviewer requested changes: append the reviewer’s Blockers list under
   `NOTES` and re-launch the **implementer** for that SCOPE only.

## Sequence (do not reorder)

1. Implementer — `SCOPE: etl`
2. Reviewer — `SCOPE: etl`
3. If request-changes: implementer etl again with Blockers in NOTES; then
   reviewer etl again. Repeat until approve. Then you (or the user) commit/merge
   the etl branch before continuing.
4. Implementer — `SCOPE: engine-ui` (skip if `SKIP_ENGINE_UI: yes`)
5. Reviewer — `SCOPE: engine-ui` (same skip / same fix loop as 3)
6. Reviewer — `SCOPE: integrate`

After each child, summarize in 5 lines: what landed, verdict, whether you are
blocked on the user (e.g. commit/merge). Then launch the next child.

## Hard rules

- Do not edit application code yourself.
- Do not paste specs into child prompts; the templates already point at files.
- Do not tell a child to “wait for a sibling” — siblings are not running.
- If a child reports an ADR conflict, stop and ask the user. Do not guess.
