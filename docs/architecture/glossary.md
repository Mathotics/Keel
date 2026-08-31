# Glossary

Domain terms used across the Keel architecture documents, so later docs share one vocabulary. Relationships between these terms are shown in the [domain model](domain-model.md).

* **Backlog** — the ordered list of a project's issues that are not scheduled in an active sprint. A view over the issue pool, not a separate entity.
* **Board** — a project's Kanban view; presents issues as cards in columns drawn from the shared statuses.
* **Board column** — a lane on a board that surfaces the issues currently in one status.
* **Collaborator** — one of up to two trusted people who share a project with the owner; in v1, equal in ability to the owner.
* **Comment** — a note attached to an issue, capturing discussion and context over time.
* **Dependency** — a directed, typed link between two issues; either *blocks* or *relates-to*.
* **Epic** — the top level of the issue hierarchy; groups related Stories.
* **Estimated time** — the effort a user expects an issue to take.
* **Issue** — the single work entity; typed as an Epic, a Story, or a Subtask.
* **Owner** — the primary user of the tool.
* **Project** — a first-class container that scopes issues, boards, sprints, and a backlog. Multiple projects coexist.
* **Relates-to** — a non-blocking association between two issues.
* **Blocks** — a dependency asserting that one issue must progress before another; *blocks* links may not form a cycle.
* **Sprint** — a time-boxed set of scheduled issues within a project; moves through *planned*, *active*, and *completed*.
* **Status** — a state in the shared, fixed workflow (for example *To Do*, *In Progress*, *Done*).
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
