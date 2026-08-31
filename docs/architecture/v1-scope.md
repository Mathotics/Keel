# v1 scope

What Keel v1 includes, what it defers, and why. Scope is kept proportional to a **personal tool for one owner plus up to two collaborators** — not a department. Enterprise-scale complexity is avoided unless it genuinely serves 1–3 users.

## In scope

**User-requested core** (the reason v1 exists):

* **Epics, Stories, Subtasks** as one typed issue with a parent/child hierarchy and progress rollup ([ADR 003](../adr/ADR-003.md)).
* **Backlog** — a per-project ranked list of unscheduled issues ([ADR 005](../adr/ADR-005.md)).
* **Sprints** — time-boxed issue sets moving through *planned → active → completed* ([ADR 005](../adr/ADR-005.md)).
* **Kanban board** — one per project, columns derived from shared statuses ([ADR 005](../adr/ADR-005.md)).
* **Ticket dependencies** — directed *blocks* / *relates-to* links with cycle prevention ([ADR 006](../adr/ADR-006.md)).

**Architect-proposed additions, confirmed for v1** (minimal glue that makes the core coherent):

* **Projects** — a first-class container; issues, boards, sprints, and backlog are scoped to a project. Multiple projects are supported from the start.
* **Shared fixed workflow** — a single small status set shared across projects ([ADR 004](../adr/ADR-004.md)).
* **Users** — a minimal notion of people for assignee/reporter, with no authentication (see below).
* **Comments** — notes on issues.
* **Time-based estimates** — estimated time and time remaining on issues, with rollup.

## Deferred beyond v1

Each of these is deliberately out of scope for v1 and can be revisited later.

| Deferred item | Reasoning |
| --- | --- |
| **Authentication & identity** | v1 assumes a trusted local/small-group context. No login, roles, permission matrices, or SSO. To be designed in a later version. |
| **Persistence technology choice** | *That* entities persist is in scope; *how* is a low-level detail below the system level. Left to the component/blueprint stage or its own future ADR. |
| **Configurable / per-project workflows** | A fixed shared workflow is proportional to a personal tool ([ADR 004](../adr/ADR-004.md)). Custom statuses, transitions, and swimlanes are deferred. |
| **Labels, components, releases/versions** | Extra classification beyond the Epic/Story/Subtask hierarchy is not needed for 1–3 users yet. |
| **Attachments** | File handling adds storage and lifecycle concerns beyond v1's core. |
| **Burndown / velocity / reporting** | Time estimates are captured in v1, but charts and analytics on top of them are deferred. |
| **Notifications** | No email or external messaging; the tool is local and low-volume. |
| **Activity history / audit log** | Not required for a small, trusted group in v1. |
| **Advanced search & saved filters** | Basic per-project navigation suffices at this scale. |
| **Third-party integrations & webhooks** | Out of the personal-tool boundary described in [context](context.md). |

## Related documents

* [Context](context.md)
* [Use cases](use-cases.md)
* [Domain model](domain-model.md)
* [Capabilities](capabilities.md)
* [Glossary](glossary.md)
