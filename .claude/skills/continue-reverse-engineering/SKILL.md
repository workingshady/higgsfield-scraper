---
name: continue-reverse-engineering
description: Use when asked to continue or resume reverse engineering of Higgsfield.ai, to check whether Higgsfield changed (new frontend build, price table, job types, feature flags), or to update the Higgsfield findings and docs from where the last session stopped.
---

# Continue reverse-engineering Higgsfield

Two docs hold everything: **state** in `.claude/docs/higgsfield-re-checkpoint.md`, **method** in
`.claude/docs/higgsfield-re-playbook.md`. Rules: GET only, no bot-protection bypass, never print tokens/cookies or read
`.env`, ~1 req/s, low RAM (grep, don't beautify).

1. **Check for changes:** `set PYTHONIOENCODING=utf-8` then `.venv\Scripts\python scripts\re_check_changes.py`
   (exit 0 unchanged, 1 changed, 2 fetch failed). For each reported change, follow playbook stage A.
2. **Read the checkpoint** (status table, IN PROGRESS rows, open questions, backlog) and the playbook's ground rules
   and pitfalls. Run `git status --short` / `git log --oneline -20`; leave files another agent is editing alone.
3. **Pick work:** the change from step 1, the user's request, or the top backlog item that is not in progress.
4. **Do it by the playbook stages:** B map the surface → C JS bundle analysis → D replay minimal GETs →
   E document (doc map + confidence labels) → F scraper (`docs/ADDING_A_SCRAPER.md`, `scrape-spider` skill).
5. **Update the checkpoint:** header values, status, findings, unknowns, backlog, and a changelog row. Then
   `.venv\Scripts\python scripts\re_check_changes.py --save`.
6. **Gates (playbook stage G):** no unintended deletions (`git diff --name-status HEAD`), `python -m pytest -q`,
   `python scripts/check_pricing_identity.py`, secrets/username scan, explicit `git add <paths>`, new docs listed in
   `docs/README.md`. Commit only when the user asks.
