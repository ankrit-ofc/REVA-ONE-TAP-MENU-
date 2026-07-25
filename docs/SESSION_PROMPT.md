# SESSION_PROMPT.md — Reusable Claude Code session starter

Paste everything below the line into a fresh Claude Code session, replace the
TASK line, and go. It encodes this project's rules so every session behaves
like the good ones.

---

You are working in the root of REVA — my multi-tenant restaurant QR-ordering
+ POS SaaS (FastAPI + React TS + Postgres 17, docker compose). Before doing
anything, read CLAUDE.md (binding invariants), docs/HANDOVER.md (workflow +
current state), and any docs they point to that are relevant to the task.

TASK: <describe what you want built/fixed/investigated here>

WORKFLOW — follow exactly:
1. Confirm the task's scope and out-of-scope back to me in one line before
   starting.
2. Start from a green, up-to-date main (git checkout main && git pull), then
   create a branch: feat/<name>, fix/<name>, test/<name>, or chore/<name>.
3. Build only what the task names. If the task needs a DB schema change, show
   me the Alembic migration (next revision after current head) and WAIT for
   approval before applying; prove downgrade/upgrade reversibility.
4. Extend the test suite in backend/tests/ to cover the change — including
   the security angles (tenancy isolation, RBAC, forged input → 422) where
   they apply. Run the FULL suite and show the real output; everything green.
5. Frontend changes: tsc --noEmit and eslint must pass; verify the change in
   the running docker compose stack and tell me what you observed.
6. Commit with a conventional message, push the branch, give me the PR link,
   and STOP before merging.

HARD RULES (violating any is a build failure):
- All CLAUDE.md §3 invariants: tenant scoping on every query, RBAC before
  every write, Decimal money, soft-delete only, snapshot immutability, audit
  logs on privileged writes, extra="forbid" on schemas, transactions +
  row locks on multi-step operations.
- Never print, commit, or weaken secrets. backend/.env and frontend/.env are
  gitignored and must stay untracked.
- Never run `docker compose down -v` unless I explicitly ask (it destroys
  data volumes). Never run `git clean` in a working tree that holds .env.
- No new dependencies (runtime or dev) without listing exact pinned versions
  and getting my approval first (CLAUDE.md §6).
- Ask before: schema changes beyond the task, auth/token changes, public API
  contract changes, anything touching money/payment calculation, destructive
  migrations. When unsure, ask — state the ambiguity and the options.
- If a test or investigation reveals a real bug outside the task's scope,
  STOP and report it with a proposed fix plan — do not fix it inline.
- If anything in these instructions conflicts with what you find in the repo,
  say so instead of silently picking one.

At the end: summarize commits (hashes + messages), files changed, test count
before/after, and anything I need to do manually.
