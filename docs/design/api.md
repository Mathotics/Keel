# API reference

The JSON API served under `/api/v1`, used by the browser's scripts, the `keel` CLI, and any external caller alike ([ADR 010](../adr/ADR-010.md)). Entities and their attributes are defined in the [data model](data-model.md).

Collections are nested under their parent; single resources are flat, so a client holding only an issue identifier can act on it.

## Conventions

* All request and response bodies are JSON. Timestamps are ISO 8601 in UTC.
* Effort is exchanged as whole minutes in `estimate_minutes` and `remaining_minutes`; the shorthand of [ADR 012](../adr/ADR-012.md) is a user-interface concern, not a wire format.
* `PATCH` bodies are partial: only supplied fields change. Sending `null` clears a nullable field.
* The acting user is resolved per [ADR 011](../adr/ADR-011.md) — the `X-Keel-User` header takes precedence, then the `keel_user` cookie, then `KEEL_DEFAULT_USER`, then the seeded default user. It defaults an issue's reporter and a comment's author.
* Enumerated values on the wire are the stored strings: types `epic`, `story`, `subtask`; statuses `todo`, `in_progress`, `in_review`, `blocked`, `done`, `cancelled`; sprint states `planned`, `active`, `completed`; sprint cadences `off`, `weekly`, `two_weeks`, `monthly`, `every_n_days`; series states `active`, `paused`; spawn modes `calendar`, `after_closed`; sprint bases `due_on`, `created_on`; recurrence `daily`, `weekly`, `monthly`, `yearly`; dependency kinds `blocks`, `relates_to`.
* There is no pagination; collections return in full, which is proportional to the scale described in [context](../architecture/context.md).

## Users

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/users` | List users |
| `POST` | `/api/v1/users` | Create a user — `{display_name}` |
| `GET` | `/api/v1/users/{user_id}` | Read a user |
| `PATCH` | `/api/v1/users/{user_id}` | Rename a user |
| `DELETE` | `/api/v1/users/{user_id}` | Delete, refused while referenced |

## Projects

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/projects` | List projects |
| `POST` | `/api/v1/projects` | Create — `{key, name, description}`; also creates the board |
| `GET` | `/api/v1/projects/{project_id}` | Read a project |
| `PATCH` | `/api/v1/projects/{project_id}` | Rename, redescribe, or set sprint cadence; `key` is immutable |
| `DELETE` | `/api/v1/projects/{project_id}` | Delete, cascading its contents |

A project's `sprint_cadence` is `off` (the default), `weekly`, `two_weeks`, `monthly`, or `every_n_days`. `every_n_days` requires `sprint_cadence_days` of at least 1. Turning cadence on opens a sprint immediately if none is active ([ADR 019](../adr/ADR-019.md)).

## Issues

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/projects/{project_id}/issues` | List, filterable |
| `POST` | `/api/v1/projects/{project_id}/issues` | Create; assigns the next per-project number |
| `GET` | `/api/v1/issues/{issue_id}` | Read, including rollup totals |
| `PATCH` | `/api/v1/issues/{issue_id}` | Update any mutable field |
| `DELETE` | `/api/v1/issues/{issue_id}` | Delete, refused when it has children |
| `GET` | `/api/v1/issues/{issue_id}/children` | Direct children |

Filters on the list endpoint: `type`, `status`, `assignee_id`, `sprint_id`, `parent_id`, and `unscheduled` (a boolean selecting issues with no sprint).

Create body:

```json
{
  "type": "story",
  "title": "Rework the onboarding script",
  "description": "",
  "status": "todo",
  "parent_id": null,
  "sprint_id": null,
  "assignee_id": 2,
  "estimate_minutes": 180,
  "due_at": "2026-09-15T17:00:00Z"
}
```

Response body, with the fields the interface needs added:

```json
{
  "id": 41,
  "key": "KEEL-12",
  "project_id": 1,
  "number": 12,
  "type": "story",
  "title": "Rework the onboarding script",
  "description": "",
  "status": "todo",
  "parent_id": null,
  "sprint_id": null,
  "reporter_id": 1,
  "assignee_id": 2,
  "estimate_minutes": 180,
  "remaining_minutes": 180,
  "due_at": "2026-09-15T17:00:00Z",
  "rollup": {
    "estimate_minutes": 420,
    "remaining_minutes": 300,
    "descendants": 4,
    "descendants_done": 1,
    "descendants_cancelled": 0
  },
  "unresolved_blockers": 2,
  "created_at": "2026-08-31T14:02:11Z",
  "updated_at": "2026-08-31T14:02:11Z"
}
```

`rollup` covers the issue and all its descendants ([ADR 012](../adr/ADR-012.md)); the issue's own `estimate_minutes` is never overwritten by it. Progress counts *Done* descendants separately from *Cancelled* ones ([ADR 020](../adr/ADR-020.md)). Moving a card on the board is a `PATCH` of `status`; moving an issue into or out of a sprint is a `PATCH` of `sprint_id`.

## Projections

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/projects/{project_id}/board` | Columns in workflow order, each with its issues |
| `GET` | `/api/v1/projects/{project_id}/backlog` | Unscheduled, unfinished issues, oldest first |

The board accepts a repeated `type` parameter to filter card types, an `assignee` parameter (`unassigned` or a user id) to filter by assignee, and a `sprint` parameter (`unscheduled` or a sprint id) to filter by sprint. The JSON body always includes `lanes` grouping the same cards by sprint, including Unscheduled. All include `unresolved_blockers` per issue so markers render without a second request ([ADR 014](../adr/ADR-014.md)). The HTML board also accepts `by=sprint` to stack a row of columns per lane.

## Sprints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/projects/{project_id}/sprints` | List, filterable by `state` |
| `POST` | `/api/v1/projects/{project_id}/sprints` | Create — `{name, goal, starts_on, ends_on}`, state `planned` |
| `GET` | `/api/v1/sprints/{sprint_id}` | Read, including its issues |
| `PATCH` | `/api/v1/sprints/{sprint_id}` | Update name, goal, or dates |
| `DELETE` | `/api/v1/sprints/{sprint_id}` | Delete; its issues are unscheduled, not deleted |
| `POST` | `/api/v1/sprints/{sprint_id}/start` | `planned` to `active`, refused if another is active |
| `POST` | `/api/v1/sprints/{sprint_id}/complete` | `active` to `completed`, carrying unfinished work forward |

Completion returns what moved:

```json
{
  "sprint": { "id": 7, "state": "completed" },
  "carried_over": 3,
  "carried_to_sprint_id": 8
}
```

`carried_to_sprint_id` is null when no planned sprint remained, meaning the issues returned to the backlog ([ADR 013](../adr/ADR-013.md)).

## Series

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/projects/{project_id}/series` | List repeating series |
| `POST` | `/api/v1/projects/{project_id}/series` | Create a series and spawn copies now |
| `GET` | `/api/v1/series/{series_id}` | Read a series |
| `PATCH` | `/api/v1/series/{series_id}` | Update the recipe or state |
| `POST` | `/api/v1/series/{series_id}/pause` | Pause (no new copies) |
| `POST` | `/api/v1/series/{series_id}/resume` | Resume spawning |
| `DELETE` | `/api/v1/series/{series_id}` | Delete the recipe; existing issues stay |

Issues spawned from a series include `series_id` and `occurrence_on` ([ADR 021](../adr/ADR-021.md)). After the series is deleted those become `null` and the issue keeps `former_series_title` and `former_series_cadence` ([ADR 023](../adr/ADR-023.md)).

## Dependencies

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/issues/{issue_id}/dependencies` | Grouped as `blocks`, `blocked_by`, `relates_to` |
| `POST` | `/api/v1/dependencies` | Create — `{source_id, target_id, kind}` |
| `DELETE` | `/api/v1/dependencies/{dependency_id}` | Remove a link |

Source and target may belong to different projects; each entry carries its issue's project key so the interface can label a cross-project link.

## Comments

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/issues/{issue_id}/comments` | List, oldest first |
| `POST` | `/api/v1/issues/{issue_id}/comments` | Create — `{body}`; author defaults to the acting user |
| `DELETE` | `/api/v1/comments/{comment_id}` | Remove a comment |

## Errors

Missing resources return 404 and request-shape failures return FastAPI's standard 422. Domain rule violations return 409 with a coded body ([ADR 010](../adr/ADR-010.md)):

```json
{
  "detail": {
    "code": "dependency.cycle",
    "message": "KEEL-12 already blocks SITE-4 through an existing chain.",
    "context": { "source_id": 41, "target_id": 88 }
  }
}
```

Codes are stable and append-only; a new rule gets a new code rather than reusing one.

| Code | Status | Raised when |
| --- | --- | --- |
| `project.duplicate_key` | 409 | A project key is already taken |
| `project.invalid_key` | 422 | A project key is not two to ten letters and digits starting with a letter |
| `project.invalid_name` | 422 | A project name is blank |
| `issue.invalid` | 422 | An issue title is blank |
| `issue.invalid_parent_type` | 409 | The parent's type is illegal for the child's type |
| `issue.invalid_parent` | 409 | The parent is in a different project |
| `issue.parent_cycle` | 409 | The assignment would make an issue its own ancestor |
| `issue.has_children` | 409 | Deleting an issue that still has children |
| `issue.invalid_duration` | 422 | Effort shorthand could not be parsed |
| `comment.invalid` | 422 | A comment body is blank |
| `sprint.already_active` | 409 | Starting a sprint while another is active in the project |
| `sprint.invalid_transition` | 409 | A state change other than planned to active or active to completed |
| `sprint.project_mismatch` | 409 | Scheduling an issue into another project's sprint |
| `sprint.invalid` | 422 | A sprint name is blank or its dates are out of order |
| `series.invalid` | 422 | A series recipe could not be saved |
| `series.stopped` | 409 | Stop is no longer a series state; delete the series instead |
| `project.invalid_cadence` | 422 | Auto-sprint is set to every N days without a positive N, or to an unknown cadence |
| `dependency.cycle` | 409 | A `blocks` link would close a cycle |
| `dependency.self_link` | 409 | Source and target are the same issue |
| `dependency.duplicate` | 409 | An identical link already exists |
| `user.in_use` | 409 | Deleting a user still referenced anywhere |
| `user.duplicate_name` | 409 | A display name is already taken |
| `user.invalid_name` | 422 | A display name is blank or over 100 characters |

## Form routes

Non-JavaScript fallbacks post to `/web` routes that redirect rather than returning JSON, since a browser form cannot consume a JSON response ([ADR 009](../adr/ADR-009.md)). They accept form encoding, call the same services, and redirect to the originating page; on a domain error they redirect to that page with the message in an `error` query parameter, so a refresh never resubmits.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/web/user` | Set the `keel_user` cookie from the top-bar picker |
| `POST` | `/web/nav` | Set the `keel_nav` cookie (section keys, dotted) from a dragged order |
| `POST` | `/web/nav/move` | Swap one visible section with its neighbour (no-JavaScript) |
| `POST` | `/web/issues` | The Create page |
| `POST` | `/web/issues/{issue_id}/status` | The board's fallback status change, and the issue page |
| `POST` | `/web/issues/{issue_id}/title` | The issue page's title |
| `POST` | `/web/issues/{issue_id}/type` | The issue page's type |
| `POST` | `/web/issues/{issue_id}/description` | The issue page's description |
| `POST` | `/web/issues/{issue_id}/parent` | The issue page's parent |
| `POST` | `/web/issues/{issue_id}/children` | Create a child Story or Subtask from the issue page |
| `POST` | `/web/issues/{issue_id}/sprint` | Schedule or unschedule an issue |
| `POST` | `/web/projects/{project_id}/sprints` | Create a sprint |
| `POST` | `/web/sprints/{sprint_id}/update` | Update name, goal, or dates |
| `POST` | `/web/sprints/{sprint_id}/delete` | Delete a sprint; its issues return to the backlog |
| `POST` | `/web/sprints/{sprint_id}/start` | Start a sprint |
| `POST` | `/web/sprints/{sprint_id}/complete` | Complete a sprint |
| `POST` | `/web/projects/{project_id}/schedules` | Create a repeating series |
| `POST` | `/web/schedules/{series_id}/update` | Save the recipe |
| `POST` | `/web/schedules/{series_id}/pause` | Pause |
| `POST` | `/web/schedules/{series_id}/resume` | Resume |
| `POST` | `/web/schedules/{series_id}/delete` | Delete the recipe; existing issues remain |
| `POST` | `/web/issues/{issue_id}/repeat` | Make this issue the first occurrence of a series |
| `POST` | `/web/issues/{issue_id}/series` | Outlook-scoped recipe edit from the issue page |
| `POST` | `/web/issues/{issue_id}/dependencies` | Add a blocks, blocked-by, or relates-to link |
| `POST` | `/web/dependencies/{dependency_id}/delete` | Remove a link |
| `POST` | `/web/issues/{issue_id}/estimate` | The issue page's estimate |
| `POST` | `/web/issues/{issue_id}/remaining` | The issue page's remaining time |
| `POST` | `/web/issues/{issue_id}/comments` | Add a comment |
| `POST` | `/web/comments/{comment_id}/delete` | Remove a comment |

Ordinary creation and editing forms post to the resource's own web route and are listed in the [UI design](ui.md).

## Related documents

* [ADR 010: One versioned JSON API with coded domain errors](../adr/ADR-010.md)
* [ADR 011: Ambient identity without authentication](../adr/ADR-011.md)
* [ADR 012: Issue realization](../adr/ADR-012.md)
* [ADR 014: Cross-project dependencies and cycle detection](../adr/ADR-014.md)
* [Data model](data-model.md)
* [UI design](ui.md)
* [Module layout](module-layout.md)
