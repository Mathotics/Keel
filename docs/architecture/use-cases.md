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

* **Rank the backlog.** A user views all of a project's unscheduled work as one ordered list and reorders it so the most important items are on top.
* **Refine an item.** A user opens a backlog item to edit its description, estimate, assignee, or parent.

## Sprints

* **Plan a sprint.** A user creates a time-boxed sprint and pulls ranked backlog items into it.
* **Start a sprint.** A user starts the sprint; its issues become the active committed work.
* **Complete a sprint.** A user completes the sprint; unfinished issues return to the backlog for re-ranking.

## Kanban board

* **Work the board.** A user views a project's issues as cards in columns drawn from the shared workflow statuses.
* **Advance an issue.** A user moves a card from one column to the next, which changes the issue's status.

## Ticket dependencies

* **Link issues.** A user records that one issue *blocks* another, or that two issues merely *relate*.
* **See what is blocked.** A user views an issue and sees what it is waiting on and what is waiting on it.
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
