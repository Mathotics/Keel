# Use cases

Goal-level journeys for the v1 features. All journeys are performed by the **owner** or a **collaborator** — in v1 they have the same abilities (see [context](context.md)). Terms are defined in the [glossary](glossary.md).

## Projects

* **Create a project.** A user creates a named project to hold a body of work. Issues, boards, sprints, and the backlog all live inside a project. Multiple projects can exist side by side.
* **Switch project.** A user moves between projects; each has its own issues, board, sprints, and backlog.

## Epics, Stories, Subtasks

* **Group work under an Epic.** A user creates an Epic to represent a large body of work and sees its child Stories and rolled-up progress.
* **Write a Story.** A user creates a Story (optionally under an Epic), gives it a description, assigns it to a person, sets a time estimate, and moves it through statuses.
* **Break a Story into Subtasks.** A user adds Subtasks under a Story; Subtask progress and time estimates roll up to the parent Story.

## Backlog

* **Review the backlog.** A user views all of a project's unscheduled, unfinished work as one list in the order it was created. There is no manual ordering — see [ADR 013](../adr/ADR-013.md), which amends [ADR 005](../adr/ADR-005.md).
* **Refine an item.** A user opens a backlog item to edit its description, estimate, assignee, or parent.

## Sprints

* **Plan a sprint.** A user creates a time-boxed sprint and pulls backlog items into it.
* **Start a sprint.** A user starts the sprint; its issues become the active committed work. Only one sprint per project may be active at a time.
* **Complete a sprint.** A user completes the sprint; unfinished issues move into the next planned sprint, or return to the backlog if there is none.

## Kanban board

* **Work the board.** A user views a project's issues as cards in columns drawn from the shared workflow statuses.
* **Filter the board.** A user restricts the board to chosen issue types, to a chosen assignee including unassigned, and to a chosen sprint including unscheduled.
* **Separate the board by sprint.** A user stacks a row of columns per sprint so cards sit with the sprint they belong to.
* **Advance an issue.** A user moves a card from one column to the next, which changes the issue's status.

## Ticket dependencies

* **Link issues.** A user records that one issue *blocks* another, or that two issues merely *relate*. The two issues may be in different projects — see [ADR 014](../adr/ADR-014.md).
* **See what is blocked.** A user views an issue and sees what it is waiting on and what is waiting on it, and spots unresolved blockers at a glance from a marker on board cards and backlog rows.
* **Avoid contradictions.** When a user tries to create a *blocks* link that would form a cycle, the system refuses it.

## Comments

* **Discuss an issue.** A user adds comments to an issue to capture notes, decisions, and context over time, and reads the existing thread.

## Time estimates

* **Estimate effort.** A user sets an estimated time on an issue and updates the time remaining as work progresses.
* **See rolled-up effort.** A user views a Story or Epic and sees estimated time and remaining time aggregated from its children.

## Related documents

* [Context](context.md)
* [Domain model](domain-model.md)
* [Capabilities](capabilities.md)
* [v1 scope](v1-scope.md)
* [UI design](../design/ui.md)
* [API reference](../design/api.md)
