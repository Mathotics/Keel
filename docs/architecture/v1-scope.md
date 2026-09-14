# v1 scope

What Keel v1 includes, what it defers, and why. Scope is kept proportional to a **personal tool for one owner plus up to two collaborators** — not a department. Enterprise-scale complexity is avoided unless it genuinely serves 1–3 users.

## In scope

**User-requested core** (the reason v1 exists):

* **Epics, Stories, Subtasks** as one typed issue with a parent/child hierarchy and progress rollup ([ADR 003](../adr/ADR-003.md)).
* **Backlog** — a per-project list of unscheduled, unfinished issues in creation order ([ADR 005](../adr/ADR-005.md), amended by [ADR 013](../adr/ADR-013.md)).
* **Sprints** — time-boxed issue sets moving through *planned → active → completed*, one active per project, with an optional per-project cadence that opens and closes those windows automatically ([ADR 005](../adr/ADR-005.md), [ADR 013](../adr/ADR-013.md), [ADR 019](../adr/ADR-019.md)).
* **Kanban board** — one per project, columns derived from shared statuses ([ADR 005](../adr/ADR-005.md)).
* **Ticket dependencies** — directed *blocks* / *relates-to* links with cycle prevention, permitted across projects ([ADR 006](../adr/ADR-006.md), [ADR 014](../adr/ADR-014.md)).

**Architect-proposed additions, confirmed for v1** (minimal glue that makes the core coherent):

* **Projects** — a first-class container; issues, boards, sprints, and backlog are scoped to a project. Multiple projects are supported from the start.
* **Shared fixed workflow** — a single small status set shared across projects ([ADR 004](../adr/ADR-004.md)).
* **Users** — a minimal notion of people for assignee/reporter, with no authentication (see below).
* **Comments** — notes on issues; descriptions and comments render as Markdown on the issue page ([ADR 017](../adr/ADR-017.md)).
* **Lightweight issue history** — a short per-issue changelog of status, assignee, sprint, estimate, remaining, due date, parent, type, title, and description ([ADR 024](../adr/ADR-024.md)).
* **Time-based estimates** — estimated time and time remaining on issues, with rollup.
* **Find** — a field in the top bar that jumps to an exact key or unique name, or lists a short page of matches ([ADR 016](../adr/ADR-016.md)).
* **Repeating work** — a per-project Schedules page of series recipes that spawn ordinary issues on a cadence ([ADR 021](../adr/ADR-021.md)).

## Deferred beyond v1

Each of these is deliberately out of scope for v1 and can be revisited later.

| Deferred item | Reasoning |
| --- | --- |
| **Authentication & identity** | v1 assumes a trusted local/small-group context. No login, roles, permission matrices, or SSO. Users are still recorded for attribution, with identity declared rather than verified ([ADR 011](../adr/ADR-011.md)). To be designed in a later version. |
| **Configurable / per-project workflows** | A fixed shared workflow is proportional to a personal tool ([ADR 004](../adr/ADR-004.md)). Custom statuses, transitions, and swimlanes other than sprint are deferred. |
| **Labels, components, releases/versions** | Extra classification beyond the Epic/Story/Subtask hierarchy is not needed for 1–3 users yet. |
| **Attachments** | File handling adds storage and lifecycle concerns beyond v1's core. |
| **Burndown / velocity / reporting** | Time estimates are captured in v1, but charts and analytics on top of them are deferred. |
| **Notifications** | No email or external messaging; the tool is local and low-volume. |
| **Activity history / audit log** | A product-wide, searchable compliance trail is not required for a small, trusted group. Reconstructive per-issue field history is in v1 ([ADR 024](../adr/ADR-024.md)). |
| **Advanced search & saved filters** | A find field in the bar covers lookup ([ADR 016](../adr/ADR-016.md)). Saved filters, operators, and a query language stay deferred. |
| **Third-party integrations & webhooks** | Out of the personal-tool boundary described in [context](context.md). |
| **Manual backlog ordering** | Removed rather than deferred. Ranking served a prioritization workflow the owner does not use, so the backlog is ordered by creation date ([ADR 013](../adr/ADR-013.md)). |

## Resolved since

The persistence technology choice was deferred here as "a low-level detail below the system level." It is now settled in [ADR 007](../adr/ADR-007.md), with the resulting schema in the [data model](../design/data-model.md). The remaining implementation-level decisions are recorded in [ADR 008](../adr/ADR-008.md) through [ADR 024](../adr/ADR-024.md).

## Related documents

* [Context](context.md)
* [Use cases](use-cases.md)
* [Domain model](domain-model.md)
* [Capabilities](capabilities.md)
* [Glossary](glossary.md)
* [Implementation plan](../design/implementation-plan.md)
* [API reference](../design/api.md)
* [UI design](../design/ui.md)
