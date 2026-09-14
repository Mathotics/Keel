# UI design

The pages Keel serves, the templates behind them, and the JavaScript that enhances the chrome and the board. The rendering decision is recorded in [ADR 009](../adr/ADR-009.md).

Every page is server-rendered with Jinja2 and works without JavaScript. Nothing is loaded from a remote origin, so the interface works offline.

## Chrome

`base.html` carries the shared chrome: the sticky top bar of [ADR 001](../adr/ADR-001.md) with the home icon, and the footer of [ADR 002](../adr/ADR-002.md) with the copyright link and the version read through `keel.version.package_version()`. On a wide viewport the footer stays pinned; on a phone-narrow viewport it sits at the end of the page ([ADR 018](../adr/ADR-018.md)). Styling continues to come from `assets/brand.css` and the palette in [brand colors](../brand-colors.md).

Beside the logo, a nav element holds the top-level section links, Projects, Create, and Users. Create is always reachable and opens a short form for a new issue. Inside a project the same nav also links to that project's board, backlog, sprints, and schedules, and Create preselects that project. Those section buttons can be reordered by dragging them, or with Up and Down when JavaScript has not run; the order is stored in a `keel_nav` cookie for this browser, the same regardless of who is selected in the picker. The home icon, the find field, and the picker stay fixed. Find sits between the section links and the picker: a GET form to `/search` with a required field, so an empty submit does not navigate and the same lookup works without JavaScript. Inside a project the form also posts that project's key so issue and sprint matches stay in that project; projects and users are always searched. The bar also holds the user picker from [ADR 011](../adr/ADR-011.md) — a small form listing users that posts to `/web/user` and returns to the current page.

Choosing a name in the picker switches user immediately: `userpicker.js` submits the form on `change`. The same script submits any form marked `data-keel-autosubmit` — the board filters, the backlog schedule control, and every editable field on the issue page — so those controls take effect without an Apply or Save click. Fallback submit buttons remain in the markup and are hidden by the `data-keel-js` marker, so the forms still work when the script does not run.

Every interactive element in the bar — link, button, select, and the find field alike — carries `keel-topbar__control` and therefore one height, text size, border, and radius. Create is the exception in colour only: it tints the brand blue with white so it reads as the primary action, still using the [brand palette](../brand-colors.md). The home icon keeps its own circular treatment as the brand mark.

## Narrow viewports

The same URLs and pages serve a phone. A wide window keeps the desktop layout with no changes. When the viewport is phone-narrow (including a desktop window squeezed down), [ADR 018](../adr/ADR-018.md) applies:

* The top bar stays sticky and still shows the home icon, section links, Find, and the picker. Those controls wrap onto extra rows and shrink; none are hidden behind a menu.
* The footer is at the end of the page, not pinned over the content. A wide window keeps the pinned footer of [ADR 002](../adr/ADR-002.md).
* Board columns keep a readable card width. Columns that do not fit are reached by swiping sideways. Separate by sprint remains stacked strips of columns, each strip swiped the same way. Status still changes with the existing Move control on a phone even when the board script has run, because dragging is unreliable with a finger.
* Tables keep their columns. Extra columns are reached by swiping sideways inside the table, not by restacking rows into cards.
* Filters and issue or create fields wrap so they stay in the screen width. There are no extra screens or `/m/` paths.

## Pages

| Path | Template | Contents |
| --- | --- | --- |
| `/` | `home.html` | Personal inbox for the picker user: assigned, due or overdue, blocked, active sprint, and series copies waiting this cycle |
| `/create` | `create.html` | Project, type, title, and the other create-time fields; comments and links wait until the issue exists |
| `/projects` | `projects.html` | Project list with a create form |
| `/projects/{key}` | `project.html` | Project summary, rename, sprint cadence, and delete, issue counts by status |
| `/projects/{key}/board` | `board.html` | Kanban columns, type, assignee, and sprint filters, optional rows per sprint, drag-and-drop |
| `/projects/{key}/backlog` | `backlog.html` | Unscheduled unfinished issues, oldest first |
| `/projects/{key}/sprints` | `sprints.html` | Sprints by state, auto-sprint status, create form |
| `/projects/{key}/sprints/{id}` | `sprint_detail.html` | Sprint issues, start or complete |
| `/projects/{key}/schedules` | `schedules.html` | Repeating series list; New series is a tab on the same URL (`?tab=new`) |
| `/projects/{key}/schedules/{id}` | `schedule_detail.html` | Edit, pause, resume, or stop a series |
| `/projects/{key}/issues/new` | — | Redirects to `/create?project={key}` |
| `/issues/{key}-{number}` | `issue_detail.html` | Full issue view; editable fields submit on change; history above comments |
| `/search` | `search.html` | Find results grouped by issues, projects, sprints, and users; exact keys and unique names jump instead |
| `/users` | `users.html` | Add, rename, and remove users |
| `/license` | `license.html` | Existing license page |

Web URLs address issues by key, as `/issues/KEEL-12`; the JSON API addresses them by internal identifier ([ADR 012](../adr/ADR-012.md)).

Every collection sits at its own path, so the project list lives at `/projects` beside `/users` rather than at the site root. `/` is the acting user's inbox ([ADR 022](../adr/ADR-022.md)): five stacked sections that can overlap, scoped to the picker, with unassigned work kept off the page. Empty sections are omitted; when nothing matches, one quiet message is shown, and it links to Projects if there are none yet. `/projects` stays a directory people open on purpose. A status control on each row posts to the same `/web/issues/{id}/status` action as the board and returns here.

## Creation and editing forms

The ordinary forms post to `/web` routes that call the same services as the JSON API and redirect afterwards, so a refresh never resubmits ([API reference](api.md)). Related fields sit in labeled groups, and short fields pair in two columns on a wide window so a long create or recipe form is not one unbroken stack.

| Method | Path | Posted from |
| --- | --- | --- |
| `POST` | `/web/nav` | A dragged section order in the top bar |
| `POST` | `/web/nav/move` | An Up or Down control beside a section link |
| `POST` | `/web/projects` | The project list's create form |
| `POST` | `/web/projects/{project_id}/update` | The project page's settings form |
| `POST` | `/web/projects/{project_id}/delete` | The project page, behind a confirmation naming what goes |
| `POST` | `/web/issues` | The Create page |
| `POST` | `/web/projects/{project_id}/issues` | The same create, when extra fields are posted |
| `POST` | `/web/issues/{issue_id}/title` | The issue page's title |
| `POST` | `/web/issues/{issue_id}/type` | The issue page's type |
| `POST` | `/web/issues/{issue_id}/description` | The issue page's description |
| `POST` | `/web/issues/{issue_id}/parent` | The issue page's parent |
| `POST` | `/web/issues/{issue_id}/children` | Create a child from the issue page |
| `POST` | `/web/issues/{issue_id}/due` | The issue detail page's due date |
| `POST` | `/web/issues/{issue_id}/assignee` | The issue detail page's assignee |
| `POST` | `/web/issues/{issue_id}/estimate` | The issue page's estimate |
| `POST` | `/web/issues/{issue_id}/remaining` | The issue page's remaining time |
| `POST` | `/web/issues/{issue_id}/comments` | The issue page's add-comment form |
| `POST` | `/web/comments/{comment_id}/delete` | A Remove control on a comment |
| `POST` | `/web/issues/{issue_id}/delete` | The issue detail page |
| `POST` | `/web/users` | The users page |
| `POST` | `/web/users/{user_id}/rename` | The users page |
| `POST` | `/web/users/{user_id}/delete` | The users page |
| `POST` | `/web/issues/{issue_id}/status` | A board card's fallback status form, and the issue page |
| `POST` | `/web/projects/{project_id}/sprints` | The sprints page create form |
| `POST` | `/web/sprints/{sprint_id}/update` | The sprint page's settings form |
| `POST` | `/web/sprints/{sprint_id}/delete` | The sprint page |
| `POST` | `/web/projects/{project_id}/schedules` | The schedules page create form |
| `POST` | `/web/schedules/{series_id}/update` | The schedule detail recipe |
| `POST` | `/web/schedules/{series_id}/pause` | Pause a series |
| `POST` | `/web/schedules/{series_id}/resume` | Resume a series |
| `POST` | `/web/schedules/{series_id}/stop` | Stop a series |
| `POST` | `/web/issues/{issue_id}/repeat` | Make this issue repeating |
| `POST` | `/web/issues/{issue_id}/series` | Outlook-scoped recipe edit |
| `POST` | `/web/issues/{issue_id}/dependencies` | The issue page's add-link form |
| `POST` | `/web/dependencies/{dependency_id}/delete` | A Remove control on the issue page |

## Board

Six columns in workflow order — To Do, In Progress, In Review, Blocked, Done, Cancelled — generated from the status enumeration rather than stored ([ADR 013](../adr/ADR-013.md)).

A card shows the issue key, title, type, assignee, its own estimate, and, when it has unresolved blockers, a marker counting them ([ADR 014](../adr/ADR-014.md)). The key is a real link to the issue; it stretches over the card so a click anywhere on it opens that page, including when JavaScript has not run. Dragging still changes status. All three issue types, every assignee, and every sprint appear by default. Filters above the board restrict which types, which assignee, and which sprint are shown; they are applied at query time, not by hiding cards. The assignee filter offers Anyone, Unassigned, or a specific person. The sprint filter offers Any sprint, Unscheduled, or a specific sprint. Separate by sprint stacks a six-column row per sprint, plus Unscheduled; dropping a card onto another sprint's row also schedules it there. Changing a filter submits the form immediately once `userpicker.js` has run; an Apply button remains for when it has not.

Each card also carries a status select and a Move button inside a form posting to `/web/issues/{id}/status`. When `board.js` loads it sets `data-keel-board` on the document root, and CSS hides those controls — so the fallback is visible precisely when the script did not run. The picker and nav scripts use their own markers (`data-keel-js`, `data-keel-nav`) for the same reason: each loads on every page, and must not hide a fallback it did not enable.

## Backlog

A flat table of the project's issues that have no sprint and are not closed, oldest first. There is no manual ordering: [ADR 013](../adr/ADR-013.md) removed backlog rank, so the backlog needs no drag-and-drop. Rows show the key, type, title, status, assignee, and a control to schedule an issue into a planned sprint. Changing that control submits immediately once `userpicker.js` has run; a Schedule button remains for when it has not.

## Sprints

The sprints page lists a project's sprints grouped by state, with a form to plan a new one. When auto-sprint is on it also shows the cadence and the next close date — the last inclusive day of the active sprint ([ADR 019](../adr/ADR-019.md)). The detail page lists the sprint's issues and offers Start (when planned) or Complete (when active). Completing reports how many unfinished issues moved and where they went. An automatic rollover uses the same notice. Sprint settings — name, goal, dates — save with an ordinary button; Start and Complete are actions, not field updates. The start and end date inputs are paired so the picker cannot offer an end before the start; the service still refuses that combination if it is posted without the script.

Project settings on the project page include sprint cadence: off, weekly, every 2 weeks, monthly, or every N days. Saving a cadence other than off opens a sprint immediately if the project has none active.

## Schedules

The schedules page lists a project's repeating series. New series is a second tab on the same URL (`?tab=new`), so the list and the recipe form are not stacked. The tabs are ordinary links and work without JavaScript. A refused create returns to the New series tab with the error. A successful create still opens the series detail page.

## Find

The find field submits GET `/search?q=…`, and `project` when the current page has one. An exact issue key (`KEEL-12`) goes to that issue; otherwise an exact project key goes to that project; otherwise a unique user display name goes to `/users`; otherwise a unique sprint name in scope goes to that sprint. Anything else renders `search.html`: the query repeated, then issues, projects, sprints, and users, about ten of each, with a note when more exist, and a none message when nothing matched. Description, goal, and comment hits open the issue or sprint they belong to, not a comment-only view. Done issues and completed sprints are included. There is no query language and no saved filter. Issue field history is not searched ([ADR 023](../adr/ADR-023.md)).

## Issue detail

The issue's fields, including due date, created-on, and updated-on; its parent and children with the children's statuses; rolled-up estimate, remaining time, and a progress count of descendants done (with cancelled descendants counted separately when any exist) alongside the issue's own values, never replacing them ([ADR 012](../adr/ADR-012.md)); its dependencies grouped as blocks, blocked by, and relates to, with the project named for any issue in a different project; a History list of who changed status, assignee, sprint, estimate, remaining, due date, parent, or type, oldest first, immediately above Comments ([ADR 023](../adr/ADR-023.md)); and the comment thread with a form to add one. Title, type, status, assignee, parent, sprint, due date, estimate, remaining time, and description are inputs on the issue page and submit as soon as they change, with a Save button only as the no-JavaScript fallback. When the issue belongs to a repeating series, a panel shows the cadence and a link to the series; recipe edits on that panel require choosing this occurrence, this and all future, or the entire series, and are not autosubmitted. Delete on a series issue skips that cycle. Description and comment bodies are stored as plain text and shown as Markdown ([ADR 017](../adr/ADR-017.md)): the issue page renders the formatted note and keeps the description source in an Edit control so it still works without JavaScript. There is no separate edit page: `/issues/{key}/edit` redirects to the issue. Created-on, updated-on, key, project, and reporter are metadata: they are shown, never offered as inputs. New issues are created from Create in the menu. That form takes every field that can be set at birth, with the same defaults the issue page would show; title is the only required one. An Epic or Story can also create a child from its own page: a title files a Story under an Epic, or a Subtask under a Story, and the parent page reloads so another can be filed. A Subtask has no such form. Comments and dependency links are added afterwards, because they need an id. Adding a comment or a child is an ordinary submit, not an autosubmit field. History is append-only: there is no remove control, and Find does not search it.

## JavaScript

Three scripts, all vanilla and with no third-party dependency. Each sets a marker on the document root that CSS keys on to hide that script's fallback controls: `data-keel-js` for the picker and the find submit button, `data-keel-nav` for the section order, `data-keel-board` for the board.

`assets/js/userpicker.js` submits the picker form when the dropdown changes, replacing its Switch button. It also submits every `data-keel-autosubmit` form on `change`, replacing those forms' Apply and Save buttons. Paired sprint date fields marked `data-keel-range` keep `min` and `max` in sync so the calendar cannot offer an end before the start.

`assets/js/nav.js` is written against the browser's native HTML Drag and Drop API. It marks the section links draggable, reorders them in the bar on drop, and posts the visible order to `/web/nav`. Up and Down remain in the markup and are hidden only after the script has run. Reordering among the links that are on the page leaves hidden project-scoped slots (Board, Backlog, Sprints) where they were.

`assets/js/board.js` is written against the browser's native HTML Drag and Drop API. It marks cards draggable, handles `dragstart` to record the issue, `dragover` to accept a drop, and `drop` to send a `PATCH` to `/api/v1/issues/{id}` with the column's status, and the sprint when the board is stacked by sprint. On success it moves the card in the DOM; on failure it returns the card to its original column and shows the message from the coded error body ([ADR 010](../adr/ADR-010.md)).

None of the scripts is required. All are loaded with `defer`, hide their fallback controls only once they have run, and no page or action is reachable through JavaScript alone.

## Error presentation

Web routes catch the same domain errors the JSON API returns and re-render the originating page with the message shown near the control that caused it — a refused cycle appears on the issue detail page, a refused sprint start on the sprint page. The user never sees a raw JSON error body or a stack trace.

## Related documents

* [ADR 009: Server-rendered Jinja2 pages with vanilla JavaScript](../adr/ADR-009.md)
* [ADR 001: Persistent top menu bar](../adr/ADR-001.md)
* [ADR 002: Persistent version footer](../adr/ADR-002.md)
* [ADR 011: Ambient identity without authentication](../adr/ADR-011.md)
* [ADR 012: Issue realization](../adr/ADR-012.md)
* [ADR 013: Planning realization](../adr/ADR-013.md)
* [ADR 014: Cross-project dependencies and cycle detection](../adr/ADR-014.md)
* [ADR 016: Find from the top bar by name](../adr/ADR-016.md)
* [ADR 017: Render issue descriptions and comments as Markdown](../adr/ADR-017.md)
* [ADR 018: Phone layout of the existing site](../adr/ADR-018.md)
* [ADR 022: Home page as a personal work inbox](../adr/ADR-022.md)
* [ADR 023: Lightweight per-issue field history](../adr/ADR-023.md)
* [API reference](api.md)
* [Brand colors](../brand-colors.md)
* [Use cases](../architecture/use-cases.md)
