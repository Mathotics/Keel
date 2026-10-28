# v1 scope

What Keel v1 includes, what it defers, and why. Scope is kept proportional to a **personal tool for one owner plus up to two collaborators** — not a department. Enterprise-scale complexity is avoided unless it genuinely serves 1–3 users.

## In scope

**User-requested core** (the reason v1 exists):

* **Epics, Stories, Subtasks** as one typed issue with a parent/child hierarchy and progress rollup ([ADR 003](../adr/unified-issue-model.md)).
* **Backlog** — a per-project list of unscheduled, unfinished issues in creation order ([ADR 005](../adr/boards-sprints-and-backlog.md), amended by [ADR 013](../adr/planning-realization.md)).
* **Sprints** — time-boxed issue sets moving through *planned → active → completed*, one active per project, with an optional per-project cadence that opens and closes those windows automatically and may keep upcoming windows planned ([ADR 005](../adr/boards-sprints-and-backlog.md), [ADR 013](../adr/planning-realization.md), [ADR 019](../adr/auto-sprint-cadence.md), [Auto-sprint lookahead](../adr/auto-sprint-lookahead.md)).
* **Month, week, and day calendar** — `/calendar` shows the acting user's unfinished issues that have a start or due date, across projects, as a month, a Monday–Sunday week, or a single day. Inside a project, `/projects/{key}/calendar` shows that project's unfinished dated issues the same way. A bar runs from the start day through the due day ([Calendar of assigned work](../adr/month-calendar.md)).
* **Kanban board** — one per project, columns derived from shared statuses ([ADR 005](../adr/boards-sprints-and-backlog.md)). A master board at `/board` shows current work from every project ([ADR 032](../adr/ADR-032.md)). A completed sprint does not appear ([Completed sprints off the board](../adr/completed-sprints-off-the-board.md)). Story and Subtask cards show a parent key when they have a parent. Epic, Story, and Subtask are colored distinctly wherever type is shown ([ADR 027](../adr/ADR-027.md)).
* **Ticket dependencies** — directed *blocks* / *relates-to* links with cycle prevention, permitted across projects ([ADR 006](../adr/ticket-dependencies.md), [ADR 014](../adr/cross-project-dependencies.md)).

**Architect-proposed additions, confirmed for v1** (minimal glue that makes the core coherent):

* **Projects** — a first-class container; issues, boards, sprints, and backlog are scoped to a project. Multiple projects are supported from the start.
* **Shared fixed workflow** — a single small status set shared across projects ([ADR 004](../adr/shared-fixed-workflow.md)).
* **Users** — people for assignee and reporter, each with a username and password ([Password login](../adr/password-login.md)).
* **Comments** — notes on issues; descriptions and comments render as Markdown on the issue page ([ADR 017](../adr/markdown-descriptions-and-comments.md)).
* **Lightweight issue history** — a short per-issue changelog of status, assignee, sprint, estimate, remaining, due date, parent, type, title, description, priority, and labels ([ADR 025](../adr/ADR-025.md), [ADR 030](../adr/ADR-030.md), [ADR 031](../adr/ADR-031.md)).
* **Time-based estimates** — estimated time and time remaining on issues, with rollup.
* **Priority** — a required five-level rank on every issue so urgency is visible on cards and lists ([ADR 030](../adr/ADR-030.md)).
* **Find** — a field in the top bar that jumps to an exact key or unique name, or lists a short page of matches ([ADR 016](../adr/find-from-the-top-bar.md)).
* **Repeating work** — a per-project Schedules page of series recipes that spawn ordinary issues on a cadence, each copy taking the recipe's priority ([ADR 021](../adr/repeating-work-scheduling-manager.md), [Series recipe priority](../adr/series-recipe-priority.md)).
* **Labels** — free-form tags on issues, filterable on the board and issue list ([ADR 031](../adr/ADR-031.md)).

## Deferred beyond v1

Each of these is deliberately out of scope for v1 and can be revisited later.

| Deferred item | Reasoning |
| --- | --- |
| **SSO** | Login is username and password plus personal API tokens ([Password login](../adr/password-login.md)). External identity providers stay deferred. Global roles are in [Role-based access](../adr/role-based-access.md). Project route checks follow in KEEL-105. |
| **Configurable / per-project workflows** | A fixed shared workflow is proportional to a personal tool ([ADR 004](../adr/shared-fixed-workflow.md)). Custom statuses, transitions, and swimlanes other than sprint are deferred. |
| **Components, releases/versions** | Extra classification beyond issue type, parent, and labels is not needed for 1–3 users yet. Labels are in v1 ([ADR 031](../adr/ADR-031.md)). |
| **Attachments** | File handling adds storage and lifecycle concerns beyond v1's core. |
| **Burndown / velocity / reporting** | Time estimates are captured in v1, but charts and analytics on top of them are deferred. |
| **Notifications** | No email or external messaging; the tool is local and low-volume. |
| **Activity history / audit log** | A product-wide, searchable compliance trail is not required for a small, trusted group. Reconstructive per-issue field history is in v1 ([ADR 025](../adr/ADR-025.md)). |
| **Advanced search & saved filters** | A find field in the bar covers lookup ([ADR 016](../adr/find-from-the-top-bar.md)). Saved filters, operators, and a query language stay deferred. |
| **Third-party integrations & webhooks** | Out of the personal-tool boundary described in [context](context.md). |
| **Manual backlog ordering** | Removed rather than deferred. Ranking served a prioritization workflow the owner does not use, so the backlog is ordered by creation date ([ADR 013](../adr/planning-realization.md)). |

## Resolved since

The persistence technology choice was deferred here as "a low-level detail below the system level." It is now settled in [ADR 007](../adr/sqlite-sqlalchemy-alembic.md), with the resulting schema in the [data model](../design/data-model.md). The remaining implementation-level decisions are recorded in [ADR 008](../adr/layered-module-structure.md) through [ADR 032](../adr/ADR-032.md). Hosting and automated deploy onto the owner's Raspberry Pi are recorded in [ADR 026](../adr/ADR-026.md). Other environments run the same app from the container image recorded in [Docker container](../adr/docker-container.md). Global roles and permissions are recorded in [Role-based access](../adr/role-based-access.md).

## Related documents

* [Context](context.md)
* [Use cases](use-cases.md)
* [Domain model](domain-model.md)
* [Capabilities](capabilities.md)
* [Glossary](glossary.md)
* [Implementation plan](../design/implementation-plan.md)
* [API reference](../design/api.md)
* [UI design](../design/ui.md)
