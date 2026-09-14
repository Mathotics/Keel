# Use cases

Goal-level journeys for the v1 features. All journeys are performed by the **owner** or a **collaborator** — in v1 they have the same abilities (see [context](context.md)). Terms are defined in the [glossary](glossary.md).

## Home

* **Start the day.** A user opens `/` or the home icon and sees work assigned to them across projects: everything unfinished on them, what is due today or overdue, what is blocked, what sits in an active sprint (including closed items in that commitment), and repeating copies waiting this cycle. The same issue may appear in more than one list. Status can be changed from a row. With more than one project, Projects remains a directory rather than the starting point ([ADR 022](../adr/ADR-022.md)).
* **Switch who I am.** Changing the picker reloads `/` for that person; unassigned work never appears there.

## Projects

* **Create a project.** A user creates a named project to hold a body of work. Issues, boards, sprints, and the backlog all live inside a project. Multiple projects can exist side by side.
* **Switch project.** A user moves between projects; each has its own issues, board, sprints, and backlog.

## Epics, Stories, Subtasks

* **Group work under an Epic.** A user creates an Epic to represent a large body of work, files Stories from that Epic, and sees its child Stories and rolled-up progress.
* **Write a Story.** A user creates a Story (optionally under an Epic), gives it a description, assigns it to a person, sets a time estimate, and moves it through statuses.
* **File an issue quickly.** A user opens Create from the menu, picks a project and type, types a title, and lands on the new issue to fill in the rest.
* **Find work by name.** A user types an issue key, a title, or other text in the menu and jumps to that item, or sees a short list of matches, without scanning the board.
* **Break a Story into Subtasks.** A user creates Subtasks from the Story's page; Subtask progress and time estimates roll up to the parent Story.

## Backlog

* **Review the backlog.** A user views all of a project's unscheduled, unfinished work as one list in the order it was created. There is no manual ordering — see [ADR 013](../adr/ADR-013.md), which amends [ADR 005](../adr/ADR-005.md).
* **Refine an item.** A user opens a backlog item to edit its description, estimate, assignee, or parent.

## Sprints

* **Plan a sprint.** A user creates a time-boxed sprint and pulls backlog items into it.
* **Start a sprint.** A user starts the sprint; its issues become the active committed work. Only one sprint per project may be active at a time.
* **Complete a sprint.** A user completes the sprint; unfinished issues move into the next planned sprint, or return to the backlog if there is none.
* **Run sprints on a cadence.** A user turns on auto-sprint for a project (weekly, every two weeks, monthly, or every N days). Keel keeps one sprint active, completing the current window after its last day and starting the next planned sprint — or creating one when none is planned ([ADR 019](../adr/ADR-019.md)).

## Repeating work

* **Schedule a repeating job.** A user opens New series on the project Schedules page (type, default title and description, cadence, when to spawn, which date picks the sprint). Copies appear as ordinary issues.
* **Work this occurrence.** A user edits this month's copy without changing last month's notes. Recipe edits ask this occurrence, this and all future, or the entire series.
* **Skip or abandon a cycle.** A user deletes this issue so that date does not come back, or marks it Cancelled so the record stays and the next copy can still appear.

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

* **Discuss an issue.** A user adds comments to an issue to capture notes, decisions, and context over time, and reads the existing thread. Descriptions and comments may use Markdown; the issue page renders it ([ADR 017](../adr/ADR-017.md)).

## Issue history

* **See how an issue got here.** A user opens an issue and reads a short trail of status, assignee, sprint, estimate, remaining, due date, parent, type, title, and description changes — who, when, from → to — without relying on comments ([ADR 023](../adr/ADR-023.md)).

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
