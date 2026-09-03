# Live Jira snapshot — removing the "prepare an agenda by hand" limit

## Why (real call, 3 сен 07:54)

> «Я протестил на звонке и есть сложность что у него контекст ограничен и
> как будто нужно всегда заранее адженду разговора создавать иначе он не
> понимает о чём речь»

Not a bug in the matcher — it's the original, still-unimplemented item from
the initial handoff list (29 авг): `snapshot.py` — переписать: сейчас
работает вручную через MCP в чате, нужен HTTP-вариант с токеном. Every
`run_*.py` still hardcodes `load_sprint("fixtures/sprint.json")` — a human
has to hand-build a JSON snapshot before every single call, or the matcher
has nothing real to match speech against and correctly stays silent (`при
сомнении молчим`). Removing that means fetching the current sprint from
real Jira automatically at launch, no manual step per call.

## Research (done live, this session — see chat for full findings + sources)

- The old `GET /rest/api/3/search` is fully removed. Current endpoint:
  `POST /rest/api/3/search/jql`, body `{jql, fields, maxResults}`, response
  `{issues: [...], isLast: bool, nextPageToken?: str}` — paginate by
  passing `nextPageToken` back in the next request body until `isLast` (or
  no token).
- Auth: HTTP Basic, `(email, api_token)` — an Atlassian API token, not
  OAuth. Confirmed against this exact pattern already working in a sibling
  project's `jira_client.py` on this machine: `requests.post(
  f"{base_url}/rest/api/3/issue", json=payload, auth=(email, api_token))`
  for ticket creation — same base URL shape, same auth shape, real prior
  art against what's presumably the same real Jira instance. That file
  *writes* tickets — ours must not; see the invariant below.
- Field shapes (`fields.summary`, `fields.assignee.displayName`,
  `fields.status.name` + `fields.status.statusCategory.key`,
  `fields.updated`, `fields.created`, `fields.priority.name`,
  `fields.labels`) match exactly what was already confirmed live off a real
  second-screen render in this project's memory (29 авг, "Модель данных
  подтверждена вживую") — no guessing needed for the mapping to `Task`.
- **No real Jira credentials exist on this machine for either project** —
  `~/.credentials/` has no `jira_credentials.env`. This can only be
  built and verified against mocked HTTP responses (TDD), not a live call.
  Flagged honestly, same as every other credential-gated feature in this
  project (OpenRouter/Speechmatics were the same story until someone
  actually ran it).

## Invariant that must not move (the original techspec, rule 8)

«В Jira ничего не изменено» — this client is read-only. `jira_client.py`
here gets exactly one write-shaped capability: none. Only
`POST /rest/api/3/search/jql` (a search, despite the HTTP verb) is called.
No issue-update, no comment, no transition. Worth a comment in the code
itself, not just here — an easy invariant to accidentally break later.

## Design

- `jira_client.py` (new) — `search_issues()` (raw paginated fetch) +
  `fetch_sprint_tasks()` (maps to `Task`, same shape `sprint_snapshot.Task`
  already has — no changes needed downstream in `agenda.py`/`facts.py`).
- `sprint_snapshot.load_current_sprint(fixture_path, fallback_team,
  credentials_path=...) -> (list[Task], list[str])` — the one function every
  `run_*.py` calls instead of `load_sprint(fixture_path)` directly:
  - No `jira_credentials.env` on disk → today's fixture + the caller's
    hardcoded `TEAM`, byte-for-byte unchanged (nobody without Jira set up
    is affected, including this repo's own tests/demo).
  - Credentials present but the fetch raises (network, auth, bad JQL) →
    same graceful fallback, with a clear stderr message — never crashes the
    app, matching `hints.py`'s existing degrade-on-error philosophy.
  - Credentials present and the fetch succeeds → real live `Task`s, and a
    real team list from a new `JIRA_TEAM` credential key (comma-separated
    display names) instead of the hardcoded synthetic `TEAM` constant —
    without this, a real Jira's real assignee names would never match the
    placeholder names in `TEAM` and the agenda would come back empty.
- New credential keys in `~/.credentials/jira_credentials.env`:
  `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` (same three keys
  `meeting_copilot` already uses — one shared file works for both projects),
  plus `JIRA_JQL` (full query, e.g. `project = X AND sprint in
  openSprints()`) or `JIRA_PROJECT_KEY` (falls back to a default JQL built
  from it), plus optional `JIRA_TEAM`.
- All four `run_*.py` (`run_second_screen.py`, `run_column.py`,
  `run_polosa_replay.py`, `run_app.py`) switch their
  `load_sprint("fixtures/sprint.json")` + hardcoded `TEAM` call site to
  `load_current_sprint("fixtures/sprint.json", TEAM)`.

## Verification plan

- TDD throughout — mocked `requests.post` responses shaped exactly like the
  confirmed-live field set, including pagination (2+ pages) and the
  null-assignee/null-priority edge cases Jira allows.
- Full test suite must stay green.
- Cannot be verified against a real Jira instance in this session (no
  token). Documented as an open item, to close by actually setting
  `~/.credentials/jira_credentials.env` and running it once against a real
  sprint.
