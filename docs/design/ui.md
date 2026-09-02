# UI design

The pages Keel serves, the templates behind them, and the JavaScript that enhances the board. The rendering decision is recorded in [ADR 009](../adr/ADR-009.md).

Every page is server-rendered with Jinja2 and works without JavaScript. Nothing is loaded from a remote origin, so the interface works offline.

## Chrome

`base.html` carries the shared chrome: the sticky top bar of [ADR 001](../adr/ADR-001.md) with the home icon, and the sticky footer of [ADR 002](../adr/ADR-002.md) with the copyright link and the version read through `keel.version.package_version()`. Styling continues to come from `assets/brand.css` and the palette in [brand colors](../brand-colors.md).

Beside the logo, a nav element holds the top-level section links, Projects and Users. Inside a project the same nav also links to that project's board, and later its backlog and sprints. The bar also holds the user picker from [ADR 011](../adr/ADR-011.md) — a small form listing users that posts to `/web/user` and returns to the current page.

Choosing a name in the picker switches user immediately: `userpicker.js` submits the form on `change`. The same script submits any form marked `data-keel-autosubmit` — the board filters and the issue page's status, assignee, and due date — so those controls take effect without an Apply or Save click. Fallback submit buttons remain in the markup and are hidden by the `data-keel-js` marker, so the forms still work when the script does not run.

Every interactive element in the bar — link, button, and select alike — carries `keel-topbar__control` and therefore one height, text size, border, and radius. The home icon keeps its own circular treatment as the brand mark.

## Pages

| Path | Template | Contents |
| --- | --- | --- |
| `/` | — | The entry point; redirects to `/projects` |
| `/projects` | `projects.html` | Project list with a create form |
| `/projects/{key}` | `project.html` | Project summary, rename and delete, issue counts by status |
| `/projects/{key}/board` | `board.html` | Kanban columns, type and assignee filters, drag-and-drop |
| `/projects/{key}/backlog` | `backlog.html` | Unscheduled unfinished issues, oldest first |
| `/projects/{key}/sprints` | `sprints.html` | Sprints by state, create form |
| `/projects/{key}/sprints/{id}` | `sprint_detail.html` | Sprint issues, start or complete |
| `/projects/{key}/issues/new` | `issue_form.html` | Create an issue |
| `/issues/{key}-{number}` | `issue_detail.html` | Full issue view |
| `/issues/{key}-{number}/edit` | `issue_form.html` | Edit an issue |
| `/users` | `users.html` | Add, rename, and remove users |
| `/license` | `license.html` | Existing license page |

Web URLs address issues by key, as `/issues/KEEL-12`; the JSON API addresses them by internal identifier ([ADR 012](../adr/ADR-012.md)).

Every collection sits at its own path, so the project list lives at `/projects` beside `/users` rather than at the site root. That keeps what the application opens on separate from what it lists: `/` is only an entry point, and it redirects. The redirect is temporary rather than permanent so that browsers do not cache it beyond the day `/` has something of its own to show, such as a dashboard. Nothing in [v1 scope](../architecture/v1-scope.md) requires one, and an empty placeholder would be worse than a redirect.

## Creation and editing forms

The ordinary forms post to `/web` routes that call the same services as the JSON API and redirect afterwards, so a refresh never resubmits ([API reference](api.md)).

| Method | Path | Posted from |
| --- | --- | --- |
| `POST` | `/web/projects` | The project list's create form |
| `POST` | `/web/projects/{project_id}/update` | The project page's settings form |
| `POST` | `/web/projects/{project_id}/delete` | The project page, behind a confirmation naming what goes |
| `POST` | `/web/projects/{project_id}/issues` | The new issue form |
| `POST` | `/web/issues/{issue_id}/update` | The edit issue form |
| `POST` | `/web/issues/{issue_id}/due` | The issue detail page's due date |
| `POST` | `/web/issues/{issue_id}/assignee` | The issue detail page's assignee |
| `POST` | `/web/issues/{issue_id}/delete` | The issue detail page |
| `POST` | `/web/users` | The users page |
| `POST` | `/web/users/{user_id}/rename` | The users page |
| `POST` | `/web/users/{user_id}/delete` | The users page |
| `POST` | `/web/issues/{issue_id}/status` | A board card's fallback status form, and the issue page |

## Board

Five columns in workflow order — To Do, In Progress, In Review, Blocked, Done — generated from the status enumeration rather than stored ([ADR 013](../adr/ADR-013.md)).

A card shows the issue key, title, type, assignee, its own estimate, and, when it has unresolved blockers, a marker counting them ([ADR 014](../adr/ADR-014.md)). All three issue types and every assignee appear by default. Filters above the board restrict which types and which assignee are shown; both are applied at query time, not by hiding cards. The assignee filter offers Anyone, Unassigned, or a specific person. Changing a filter submits the form immediately once `userpicker.js` has run; an Apply button remains for when it has not.

Each card also carries a status select and a Move button inside a form posting to `/web/issues/{id}/status`. When `board.js` loads it sets `data-keel-board` on the document root, and CSS hides those controls — so the fallback is visible precisely when the script did not run. The picker script uses its own marker (`data-keel-js`) for the same reason: it loads on every page, and must not hide a board fallback it did not enable.

## Backlog

A flat table of the project's issues that have no sprint and are not Done, oldest first. There is no manual ordering: [ADR 013](../adr/ADR-013.md) removed backlog rank, so the backlog needs no drag-and-drop. Rows show the key, type, title, status, assignee, estimate, and the blocker marker, with a control to schedule an issue into a planned sprint.

## Issue detail

The issue's fields, including due date, created-on, and updated-on; its parent and children with the children's statuses; rolled-up estimate, remaining time, and a progress count of descendants done alongside the issue's own values, never replacing them ([ADR 012](../adr/ADR-012.md)); its dependencies grouped as blocks, blocked by, and relates to, with the project named for any issue in a different project; and the comment thread with a form to add one. Status, assignee, and due date are inputs on the issue page and on the create/edit form. On the issue page they submit as soon as they change, with a Save button only as the no-JavaScript fallback. Created-on and updated-on are metadata: they are shown, never offered as inputs.

## JavaScript

Two scripts, both vanilla and with no third-party dependency. Each sets a marker on the document root that CSS keys on to hide that script's fallback controls: `data-keel-js` for the picker, `data-keel-board` for the board.

`assets/js/userpicker.js` submits the picker form when the dropdown changes, replacing its Switch button. It also submits every `data-keel-autosubmit` form on `change`, replacing those forms' Apply and Save buttons.

`assets/js/board.js` is written against the browser's native HTML Drag and Drop API. It marks cards draggable, handles `dragstart` to record the issue, `dragover` to accept a drop, and `drop` to send a `PATCH` to `/api/v1/issues/{id}` with the column's status. On success it moves the card in the DOM; on failure it returns the card to its original column and shows the message from the coded error body ([ADR 010](../adr/ADR-010.md)).

Neither script is required. Both are loaded with `defer`, hide their fallback controls only once they have run, and no page or action is reachable through JavaScript alone.

## Error presentation

Web routes catch the same domain errors the JSON API returns and re-render the originating page with the message shown near the control that caused it — a refused cycle appears on the issue detail page, a refused sprint start on the sprint page. The user never sees a raw JSON error body or a stack trace.

## Related documents

* [ADR 009: Server-rendered Jinja2 pages with vanilla JavaScript](../adr/ADR-009.md)
* [ADR 001: Persistent top menu bar](../adr/ADR-001.md)
* [ADR 002: Persistent version footer](../adr/ADR-002.md)
* [ADR 011: Ambient identity without authentication](../adr/ADR-011.md)
* [ADR 013: Planning realization](../adr/ADR-013.md)
* [API reference](api.md)
* [Brand colors](../brand-colors.md)
* [Use cases](../architecture/use-cases.md)
