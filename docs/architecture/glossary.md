# Glossary

Domain terms used across the Keel architecture documents, so later docs share one vocabulary. Relationships between these terms are shown in the [domain model](domain-model.md).

* **Backlog** — the list of a project's issues that have no sprint assigned and are not closed (*Done* or *Cancelled*), in creation order. A view over the issue pool, not a separate entity, and not manually ordered ([ADR 013](../adr/ADR-013.md)).
* **Blocked** — a workflow status a person sets by hand. Keel never applies it automatically, since dependency-driven status changes are out of scope ([ADR 006](../adr/ADR-006.md)); unresolved blockers surface as a marker instead.
* **Cancelled** — a closed workflow status for work that will not be done. Distinct from *Done*: it leaves the backlog and does not carry over on sprint complete, but it does not clear blockers and does not count as done in parent progress ([ADR 020](../adr/ADR-020.md)).
* **Board** — a project's Kanban view; presents issues as cards in columns drawn from the shared statuses.
* **Board column** — a lane on a board that surfaces the issues currently in one status.
* **Collaborator** — one of up to two trusted people who share a project with the owner; in v1, equal in ability to the owner.
* **Comment** — a note attached to an issue, capturing discussion and context over time.
* **Issue history** — an append-only trail on an issue of who changed status, assignee, sprint, estimate, remaining, due date, parent, or type, from what to what ([ADR 023](../adr/ADR-023.md)).
* **Dependency** — a directed, typed link between two issues; either *blocks* or *relates-to*.
* **Epic** — the top level of the issue hierarchy; groups related Stories.
* **Estimated time** — the effort a user expects an issue to take.
* **Issue** — the single work entity; typed as an Epic, a Story, or a Subtask.
* **Issue key** — a project's key with the issue's per-project number, such as `KEEL-12`; how an issue is named in the interface and in conversation ([ADR 012](../adr/ADR-012.md)).
* **Owner** — the primary user of the tool.
* **Project** — a first-class container that scopes issues, boards, sprints, and a backlog. Multiple projects coexist.
* **Project key** — a short uppercase identifier for a project, used to prefix its issue numbers.
* **Relates-to** — a non-blocking association between two issues.
* **Blocks** — a dependency asserting that one issue must progress before another; *blocks* links may not form a cycle.
* **Sprint** — a time-boxed set of scheduled issues within a project; moves through *planned*, *active*, and *completed*. At most one sprint per project is active at a time. A project may opt into a cadence so those windows open and close automatically ([ADR 019](../adr/ADR-019.md)).
* **Series** — a repeating recipe that spawns ordinary issues on a cadence. The recipe is not a board card ([ADR 021](../adr/ADR-021.md)).
* **Auto-sprint** — a per-project cadence (weekly, every two weeks, monthly, or every N days) that completes the active sprint after its last inclusive day and opens the next window.
* **Status** — a state in the shared, fixed workflow: *To Do*, *In Progress*, *In Review*, *Blocked*, *Done*, or *Cancelled*. *Done* and *Cancelled* are closed; only *Done* is completed ([ADR 020](../adr/ADR-020.md)).
* **Story** — a deliverable unit of work; may belong to an Epic and may contain Subtasks.
* **Subtask** — a small unit of work beneath a Story.
* **Time remaining** — the effort a user expects an issue still needs; updated as work progresses.
* **Workflow** — the ordered set of shared statuses an issue moves through; fixed and shared across projects in v1.

## Related documents

* [Context](context.md)
* [Use cases](use-cases.md)
* [Domain model](domain-model.md)
* [Capabilities](capabilities.md)
* [v1 scope](v1-scope.md)
* [Data model](../design/data-model.md)
