# Data dictionary

Software terms used in Keel: what each one means, which other terms it hangs on, and how it behaves when behavior is part of the term. Short definitions for the architecture set also live in the [glossary](glossary.md). Entities are drawn in the [domain model](domain-model.md). Columns, checks, and indexes are in the [data model](../design/data-model.md). Decisions stay in the ADRs linked from each entry.

Stored tokens below are the lowercase values on the database and the JSON API. The interface shows the label.

## Work

### Issue

**Definition.** The single work entity. A board card, a backlog row, a calendar bar, and a Gantt row are all the same issue.

**Relates to.** [Project](#project), [Issue key](#issue-key), [Issue type](#issue-type), [Status](#status), [Priority](#priority), [Sprint](#sprint), [Parent](#parent), [Label](#label), [Comment](#comment), [Dependency](#dependency), [Series](#series).

**How it works.** An issue belongs to one project. It starts in *To Do* at priority *P4 — Minor*. Creating one takes the next number from that project's counter in the same transaction; the number is never reused. A parent, when set, must be in the same project and must be the legal type for the child. Description, definition of done, and location are blank until someone writes them. Estimate, remaining time, the three cost amounts, start, due, sprint, and assignee stay unset until set. Deleting an issue that still has children is refused. Deleting a childless issue removes its comments, field history, label links, and every dependency that names it.

### Issue key

**Definition.** The name of an issue in the interface, in conversation, and in web URLs: the project key, a hyphen, and the issue's per-project number, such as `KEEL-12`.

**Relates to.** [Project key](#project-key), [Issue](#issue).

**How it works.** The JSON API addresses an issue by its numeric id. The key is derived from the project and the number. Two issues in one project never share a number.

### Issue type

**Definition.** Which level of the hierarchy an issue occupies: Epic, Story, or Subtask. Stored as `epic`, `story`, or `subtask`.

**Relates to.** [Epic](#epic), [Story](#story), [Subtask](#subtask), [Parent](#parent).

**How it works.** Type is required. Changing type is refused when the issue already has children that cannot sit under the new type. Recurrence is not a type; repeating work is a [series](#series) that spawns ordinary issues.

### Epic

**Definition.** The top level of the issue hierarchy. It groups related stories.

**Relates to.** [Story](#story), [Issue type](#issue-type).

**How it works.** An epic never has a parent. Stories may sit under it. A series may use an epic as the root of a spawned tree.

### Story

**Definition.** A deliverable unit of work. It may belong to an epic and may contain subtasks.

**Relates to.** [Epic](#epic), [Subtask](#subtask), [Parent](#parent).

**How it works.** A story's parent, when it has one, is an epic in the same project. Having no parent is allowed. Only subtasks may sit directly under a story.

### Subtask

**Definition.** A small unit of work beneath a story.

**Relates to.** [Story](#story), [Parent](#parent).

**How it works.** A subtask's parent, when it has one, is a story in the same project. A subtask has no children of its own.

### Parent

**Definition.** The optional issue directly above this one in the hierarchy.

**Relates to.** [Epic](#epic), [Story](#story), [Subtask](#subtask), [Rollup](#rollup).

**How it works.** The only legal pairs are story under epic, and subtask under story. Parent and child must share a project. A parent that would make the issue its own ancestor is refused. Effort, cost, and progress shown on a parent include the parent and the issues under it. The parent's own stored amounts stay as typed.

### Description

**Definition.** Free-text Markdown on an issue, a comment body, or a series recipe, capturing what the work is.

**Relates to.** [Issue](#issue), [Comment](#comment), [Definition of done](#definition-of-done).

**How it works.** On an issue the field is optional and defaults to blank. The issue page renders it as Markdown. A change is recorded in [issue history](#issue-history). A series copies its description onto each new occurrence; later edits of one occurrence do not rewrite the others unless the edit scope says so.

### Definition of done

**Definition.** Free-text Markdown on an issue naming what has to be true before that issue may move to *Done*.

**Relates to.** [Description](#description), [Done](#done), [Issue](#issue).

**How it works.** The field is optional. Nothing reads it to block a status change. It is Description's twin on the issue page and has its own history line. A series recipe does not carry a definition of done; spawned issues start with it blank.

### Location

**Definition.** An optional short text on an issue naming where the work will happen.

**Relates to.** [Issue](#issue).

**How it works.** Blank until set, at most 300 characters, and shown as typed. A change is a history line. A series recipe does not copy a location onto new issues.

### Comment

**Definition.** A note attached to an issue, capturing discussion over time.

**Relates to.** [Issue](#issue), [User](#user).

**How it works.** A comment has a body and the time it was written, and one author. Bodies render as Markdown on the issue page. Comments are not part of issue history and are not copied onto the next occurrence of a series. Deleting the issue deletes its comments. Who may write or delete a comment is a [permission](#permission).

### Issue history

**Definition.** An append-only trail on one issue of who changed a tracked field, from what, to what, and when.

**Relates to.** [Issue](#issue), [User](#user).

**How it works.** The tracked fields are status, assignee, sprint, estimate, remaining, due date, parent, type, title, description, definition of done, priority, labels, location, planned value, earned value, and actual cost. Who, from, and to are snapshotted labels, so a later rename does not rewrite old lines. It is the changelog of one issue, not a log of every HTTP request. That log is the [request log](#request-log).

### Label

**Definition.** A reusable free-form tag. The catalog is shared across projects.

**Relates to.** [Issue](#issue), [Series](#series).

**How it works.** A name is stored lowercase, unique, and 1–40 characters. An issue may carry many labels. A series stores labels on its recipe and on each series item, and copies them onto issues it spawns. Deleting an issue drops its links and leaves the catalog row. The board and the issue list can be filtered by one label. Adding or removing labels on an issue writes one history line.

### Priority

**Definition.** A required rank on every issue, from *P1 — Blocker* down to *P5 — Trivial*. Stored as `p1` through `p5`. The default is `p4`.

**Relates to.** [Issue](#issue), [Series](#series), [Blocked](#blocked).

**How it works.** Declaration order is rank: P1 is highest, P5 is lowest. The word Blocker in the P1 label is the rank name. It does not set the *Blocked* status and it does not create a blocks link. A series stores a priority on the root and on each series item and copies it onto spawned issues. A change on an issue is a history line.

### Client key

**Definition.** An optional token the caller sends when creating an issue so a repeated submit returns the issue already created.

**Relates to.** [Issue](#issue).

**How it works.** The key is 16 to 64 letters, digits, hyphens, or underscores, and unique across issues. A second create with the same key, same project, and same reporter returns the original issue. The same key with a different project or reporter is refused. A create without a key always inserts. The phone offline queue uses this so a retry does not duplicate the card.

## Workflow

### Status

**Definition.** A state in the shared, fixed workflow. Stored as `todo`, `in_progress`, `in_review`, `blocked`, `done`, or `cancelled`.

**Relates to.** [Workflow](#workflow), [Board column](#board-column), [Closed](#closed), [Done](#done), [Cancelled](#cancelled), [Blocked](#blocked).

**How it works.** Every project uses this same set, in that order. A person moves an issue by changing its status; moving a card on the board is that change. New issues start at *To Do*. *In Progress* and *In Review* are open states with no extra rule of their own. The set is an enumeration in code. Board columns are generated from it and are not stored.

### Workflow

**Definition.** The ordered set of shared statuses an issue moves through.

**Relates to.** [Status](#status), [Board](#board).

**How it works.** The order is *To Do*, *In Progress*, *In Review*, *Blocked*, *Done*, *Cancelled*. It is fixed for every project. There is no per-project workflow to configure.

### Blocked

**Definition.** A workflow status a person sets by hand when work cannot proceed.

**Relates to.** [Status](#status), [Unresolved blocker](#unresolved-blocker), [Blocks](#blocks).

**How it works.** Keel does not set this status from a dependency. An issue can sit in *To Do* and still show an unresolved-blocker count, and an issue can be *Blocked* with no dependency at all. Stored as `blocked`.

### Done

**Definition.** The closed status for work that is finished. Stored as `done`.

**Relates to.** [Closed](#closed), [Cancelled](#cancelled), [Rollup](#rollup), [Unresolved blocker](#unresolved-blocker).

**How it works.** *Done* is the only status that counts as completed. A parent's progress counts descendants in *Done*. A blocks link whose source is *Done* no longer counts as an unresolved blocker. Definition of done is not checked on the way here.

### Cancelled

**Definition.** The closed status for work that will not be done. Stored as `cancelled`.

**Relates to.** [Closed](#closed), [Done](#done), [Rollup](#rollup), [Unresolved blocker](#unresolved-blocker).

**How it works.** A cancelled issue leaves the backlog and does not carry over when its sprint is completed. It does not count as done in parent progress. It does not clear a blocks link: a cancelled source is still an unresolved blocker. Cancelled descendants stay in the estimate total and in the cost totals, and drop out of time remaining.

### Closed

**Definition.** An issue whose status is *Done* or *Cancelled*.

**Relates to.** [Done](#done), [Cancelled](#cancelled), [Backlog](#backlog), [Sprint](#sprint).

**How it works.** Closed issues are off the backlog. On sprint completion they stay with the sprint that just finished. Open issues move to the earliest remaining planned sprint in the project, or back to the backlog when no planned sprint remains. Only *Done* is completed; *Cancelled* is closed and not completed.

## Planning

### Project

**Definition.** A container that scopes issues, one board, sprints, a backlog, and repeating series. Many projects coexist.

**Relates to.** [Project key](#project-key), [Issue](#issue), [Board](#board), [Sprint](#sprint), [Backlog](#backlog), [Series](#series), [Currency](#currency).

**How it works.** A project has a name, a short description, a key, and a currency (`USD` until changed). It may opt into an auto-sprint cadence. Deleting a project deletes its issues, sprints, and board, and through those issues their comments, history, and dependency links, including a link whose other end is in another project.

### Project key

**Definition.** A short uppercase identifier that prefixes the project's issue numbers.

**Relates to.** [Project](#project), [Issue key](#issue-key).

**How it works.** The key is unique, 2 to 10 characters, and starts with a letter. It is the left half of every issue key in that project. Web routes for one project use the key, such as `/projects/KEEL/board`.

### Board

**Definition.** A Kanban view of issues as cards in columns, one column per status.

**Relates to.** [Board column](#board-column), [Status](#status), [Project](#project), [Master board](#master-board).

**How it works.** Each project has one stored board, created with the project. The board does not own issues; it shows the project's issues in their current status. Completed sprints are omitted from the project board's sprint lanes.

### Master board

**Definition.** The board at `/board` that shows issues from every project the person can see.

**Relates to.** [Board](#board), [Project](#project).

**How it works.** It uses the same status columns as a project board and belongs to no single project. Cards still carry their own project and issue key.

### Board column

**Definition.** A lane on a board that surfaces the issues currently in one status.

**Relates to.** [Board](#board), [Status](#status).

**How it works.** Columns are generated by walking the status enumeration in workflow order. They are not rows in the database, and they are not reordered per project.

### Backlog

**Definition.** The list of a project's issues that have no sprint and are not closed, in creation order, oldest first.

**Relates to.** [Issue](#issue), [Sprint](#sprint), [Closed](#closed), [Project](#project).

**How it works.** The backlog is a view, not a stored list and not a rank. Assigning an issue to any sprint, including a planned one, removes it from the backlog immediately. *Done* and *Cancelled* are excluded. There is no manual drag order.

### Sprint

**Definition.** A time-boxed set of issues inside one project. An issue is in at most one sprint.

**Relates to.** [Project](#project), [Backlog](#backlog), [Auto-sprint](#auto-sprint), [Closed](#closed).

**How it works.** State is `planned`, `active`, or `completed`, and that is the only lifecycle. At most one sprint per project is active. A sprint has a name, an optional goal, and optional start and end dates; the end is not before the start. Completing a sprint leaves closed issues where they are and moves every other issue into the earliest remaining planned sprint, or unschedules it so it returns to the backlog. Deleting a sprint unschedules its issues and does not delete them. Sprint menus list active and planned sprints and omit completed ones.

### Auto-sprint

**Definition.** A per-project cadence that completes the active sprint after its last inclusive day and opens the next window.

**Relates to.** [Sprint](#sprint), [Project](#project).

**How it works.** Cadence is `off` until the project opts in, then `weekly`, `two_weeks`, `monthly`, or `every_n_days`. *Every N days* stores N in `sprint_cadence_days`. `sprint_ahead` is how many upcoming sprints stay planned, from 0 to 12. Zero means the next window is created at rollover. The last automatic open or close message is kept on the project for the sprints page. A series cadence and the project cadence are independent: a daily series can live in a weekly sprint.

### Calendar

**Definition.** A month, week, or day view of unfinished issues that have a start or a due date, drawn as a bar from the start day through the due day.

**Relates to.** [Issue](#issue), [Start](#start), [Due](#due), [Gantt](#gantt).

**How it works.** `/calendar` is the signed-in user's unfinished dated issues across projects. `/projects/{key}/calendar` is that project's unfinished dated issues.

### Gantt

**Definition.** A timeline of dated issues, one row each, with a bar from the start day through the due day.

**Relates to.** [Issue](#issue), [Parent](#parent), [Dependency](#dependency), [Calendar](#calendar).

**How it works.** `/gantt` is the signed-in user's issues across projects, including *Done* and *Cancelled*. `/projects/{key}/gantt` is that project's dated issues. Month is days, quarter is weeks, and year is months. A child sits under its parent when the parent is on the page. A blocks link between two rows is an arrow. A relates-to link is a dashed line. The phone app opens the same chart from its menu.

### Start

**Definition.** The optional instant when work on an issue is meant to begin.

**Relates to.** [Due](#due), [Issue](#issue), [Series](#series).

**How it works.** Stored as a timestamp. When due is also set, start must not be after due. On a series recipe the start is an offset: days before the occurrence date, plus a minute of the day. Both parts are set together, or both are unset, and an unset pair means the copy has no start.

### Due

**Definition.** The optional instant when work on an issue is meant to be finished.

**Relates to.** [Start](#start), [Issue](#issue), [Sprint basis](#sprint-basis).

**How it works.** Stored as a timestamp, and not before start when both are set. A change is a history line. On a series recipe the due is days after the occurrence date, plus a minute of the day, under the same both-or-neither rule as start. When both offsets are set, the resulting start is not after the resulting due.

## Repeating work

### Series

**Definition.** A repeating recipe that spawns ordinary issues on a cadence. The schedules pages call it a schedule. The recipe itself is off the board.

**Relates to.** [Occurrence](#occurrence), [Series item](#series-item), [Spawn mode](#spawn-mode), [Sprint basis](#sprint-basis), [Look-ahead](#look-ahead), [Project](#project).

**How it works.** A series belongs to one project and stores a title, description, issue type, priority, labels, an optional assignee, and an optional parent for the root. Cadence is daily, weekly, monthly, or yearly, with an interval of at least 1, a start date, and an optional end by date or by count. State is `active`, `paused`, or `stopped`. Pause creates nothing further. Resume continues. Delete removes the recipe and leaves spawned issues in place. Leftover `stopped` rows are treated as deleted. Priority and labels are copied onto each new issue. Cost, definition of done, location, comments, and dependency links are not copied; new issues start with those unset.

### Series item

**Definition.** One child recipe in a schedule's tree. The series row itself is the root recipe.

**Relates to.** [Series](#series), [Occurrence](#occurrence), [Parent](#parent).

**How it works.** Each item has its own title, type, description, priority, labels, assignee, and start and due offsets. Items follow the same parent rules as issues: a story under an epic, a subtask under a story. The schedule still has one cadence, one spawn mode, one sprint basis, and one look-ahead for the whole tree. A schedule with no child items behaves as a single-issue schedule. Saving the schedule page updates the template for occurrences that do not exist yet and leaves issues that already exist alone. Removing the root is not offered; ending the recipe is deleting the series.

### Occurrence

**Definition.** One spawned issue, or one spawned tree, for a single cycle date of a series.

**Relates to.** [Series](#series), [Series item](#series-item), [Edit scope](#edit-scope).

**How it works.** The root issue of the cycle stores the series and the occurrence date. A child issue also stores the series item it came from. A date is spawned at most once for a given root, and at most once for a given item. Deleting the root issue of an occurrence removes that occurrence's scheduled tree and skips the date so calendar mode does not recreate it. Deleting one child removes only that item from the occurrence. When the series is deleted, each spawned issue keeps the recipe title and a cadence summary as a former-series note and drops the live link.

### Spawn mode

**Definition.** When the next occurrence is created. Stored as `calendar` or `after_closed`.

**Relates to.** [Series](#series), [Look-ahead](#look-ahead), [Closed](#closed).

**How it works.** *On the calendar* creates each occurrence inside the current look-ahead even if an older root is still open. *After the previous copy is closed* waits until the previous root is *Done* or *Cancelled*, then creates the next scheduled occurrence from now. Open children do not hold the next tree back. Missed dates are not backfilled. Reopening a closed root does not retract a tree already created.

### Sprint basis

**Definition.** Which date of an occurrence is used to choose its sprint. Stored as `due_on`, `start_on`, or `created_on`.

**Relates to.** [Series](#series), [Sprint](#sprint), [Look-ahead](#look-ahead).

**How it works.** The copy is placed in the planned or active sprint that overlaps that date. Completed sprints are never used. Each series item uses the schedule's basis with that item's own dates, so items in one occurrence can land in different sprints. An item whose basis date is blank is left unscheduled. When no sprint overlaps, look-ahead still limits how many occurrences exist.

### Look-ahead

**Definition.** How many upcoming occurrences a series keeps created. Stored as `look_ahead_n`, at least 1.

**Relates to.** [Series](#series), [Spawn mode](#spawn-mode), [Sprint basis](#sprint-basis).

**How it works.** The count is occurrences, and one occurrence is one full tree. The series does not materialize a year of issues ahead of that count. Opening a new auto-sprint window does not duplicate a cycle that already exists.

### Series skip

**Definition.** A record that a cycle date was deleted, so calendar mode does not recreate that occurrence.

**Relates to.** [Series](#series), [Occurrence](#occurrence).

**How it works.** Deleting this occurrence writes the skip for that date. The series continues on later dates.

### Edit scope

**Definition.** How far a change to a repeating issue reaches. Stored as `this`, `future`, or `series`, and labeled *This occurrence*, *This and all future*, and *Entire series*.

**Relates to.** [Occurrence](#occurrence), [Series item](#series-item).

**How it works.** The choice applies to one item at a time. *This occurrence* changes that issue only. An add in that scope creates an issue on this occurrence and does not add a repeating item. A remove takes that issue off this occurrence only. *This and all future* and *Entire series* update the template and apply the same add, remove, or field change on open copies in range. Closed copies stay as they are, including for the entire series. Status changes are this occurrence only.

## Dependencies

### Dependency

**Definition.** A directed, typed link between two issues. The kind is *blocks* or *relates-to*. Stored as `blocks` or `relates_to`.

**Relates to.** [Blocks](#blocks), [Relates-to](#relates-to), [Issue](#issue).

**How it works.** The link has one source issue and one target issue. The two ends may be in different projects. A link from an issue to itself is refused, and the same source, target, and kind cannot be stored twice. Dependencies are separate from the parent hierarchy. Deleting either issue deletes the link.

### Blocks

**Definition.** A dependency asserting that the source issue must be *Done* before the target can proceed.

**Relates to.** [Dependency](#dependency), [Unresolved blocker](#unresolved-blocker), [Blocked](#blocked).

**How it works.** The source is the blocker and the target is the issue that waits. *Blocks* links may not form a cycle anywhere in the global graph, including a cycle that leaves one project and re-enters it. On a Gantt chart a blocks link between two visible rows is an arrow. Keel does not change either issue's status because of the link.

### Relates-to

**Definition.** A non-blocking association between two issues.

**Relates to.** [Dependency](#dependency), [Blocks](#blocks).

**How it works.** The link is stored with a source and a target, and the issue page shows it from either end. It does not affect blocker counts, backlog membership, or status. On a Gantt chart it is a dashed line between two visible rows. Cycles are allowed for this kind.

### Unresolved blocker

**Definition.** A count of *blocks* links into an issue whose source is not *Done*.

**Relates to.** [Blocks](#blocks), [Blocked](#blocked), [Done](#done), [Cancelled](#cancelled).

**How it works.** The count is attached to the target. A source in *Cancelled* still counts, because only *Done* clears a blocker. The count is a marker on board cards, backlog rows, and the home inbox. It does not set the *Blocked* status.

## Effort and cost

### Estimated time

**Definition.** The effort a person expects an issue to take, stored as whole minutes.

**Relates to.** [Time remaining](#time-remaining), [Rollup](#rollup), [Issue](#issue).

**How it works.** Unset is different from zero. Unset contributes nothing to a sum. An explicit zero is stored and does contribute. A parent shows its own estimate beside the subtree total. Cancelled descendants stay in that total. A change is a history line. Nothing requires an estimate before an issue can be done.

### Time remaining

**Definition.** The effort a person expects an issue still needs, stored as whole minutes.

**Relates to.** [Estimated time](#estimated-time), [Rollup](#rollup), [Cancelled](#cancelled).

**How it works.** The same unset-versus-zero rule as estimated time applies. The subtree remaining total omits cancelled descendants and includes every other descendant that has a remaining value, plus the issue's own remaining. A change is a history line.

### Rollup

**Definition.** The subtree totals shown on an issue: effort, cost, and progress, computed when the issue is read.

**Relates to.** [Parent](#parent), [Estimated time](#estimated-time), [Time remaining](#time-remaining), [Planned value](#planned-value), [Earned value](#earned-value), [Actual cost](#actual-cost).

**How it works.** The walk starts at the issue and includes every descendant. Nothing is cached. List responses leave rollup null. Progress counts descendants in *Done*, and counts cancelled descendants separately. The issue's own stored numbers are not replaced by the totals.

### Planned value

**Definition.** What the issue was planned to be worth, stored as whole non-negative cents. Also called PV or BCWS.

**Relates to.** [Earned value](#earned-value), [Actual cost](#actual-cost), [Currency](#currency), [Budget at completion](#budget-at-completion).

**How it works.** Null means unset. The page accepts an amount in the project currency, such as `12`, `12.50`, or `$1,234.56 USD`, and refuses a negative amount or a symbol for a different currency. The JSON API exchanges cents. A parent shows its own amount and a subtree sum that includes cancelled descendants. A change is a history line labeled in the project currency then in effect, with `none` when unset. Spawned issues start with it unset.

### Earned value

**Definition.** What has been earned on the issue, stored as whole non-negative cents. Also called EV or BCWP.

**Relates to.** [Planned value](#planned-value), [Actual cost](#actual-cost), [Schedule performance index](#schedule-performance-index).

**How it works.** The same storage, entry, rollup, and history rules as planned value. It is an input to estimate at completion and to both performance indexes. It is not computed from status.

### Actual cost

**Definition.** What has been spent on the issue, stored as whole non-negative cents. Also called AC or ACWP.

**Relates to.** [Planned value](#planned-value), [Earned value](#earned-value), [Cost performance index](#cost-performance-index).

**How it works.** The same storage, entry, rollup, and history rules as planned value. Cancelled work stays in the sum, so a cancelled child's spend still raises the parent's actual cost.

### Currency

**Definition.** The ISO code a project uses to label cost amounts. Stored as three uppercase letters, `USD` until changed.

**Relates to.** [Project](#project), [Planned value](#planned-value), [Earned value](#earned-value), [Actual cost](#actual-cost).

**How it works.** One currency covers every cost on every issue in the project. Amounts are stored as cents of that unit. Changing the code relabels those digits. It does not convert them. There is no per-issue currency and no exchange rate.

### Budget at completion

**Definition.** The rolled-up planned value of an issue and its descendants. Also called BAC.

**Relates to.** [Planned value](#planned-value), [Rollup](#rollup).

**How it works.** It is calculated, not stored, and not accepted on create or update. It is null when no planned value is set in the subtree. It is the planned-value total of the work recorded so far, not a separately entered project budget.

### Estimate at completion

**Definition.** Actual cost plus the planned value still unearned: actual + (budget at completion − earned value). Also called EAC.

**Relates to.** [Budget at completion](#budget-at-completion), [Earned value](#earned-value), [Actual cost](#actual-cost).

**How it works.** Calculated from the subtree totals. Null unless planned, earned, and actual totals are all present. Past spend stays. Remaining budgeted work is priced at the original plan. It does not assume the current cost index continues.

### Schedule performance index

**Definition.** Earned value divided by planned value, using the subtree totals. Also called SPI.

**Relates to.** [Earned value](#earned-value), [Planned value](#planned-value), [Rollup](#rollup).

**How it works.** Calculated, not stored. Null when planned value is missing or zero. Otherwise rounded half up to four decimal places. A parent does not average its children's indexes.

### Cost performance index

**Definition.** Earned value divided by actual cost, using the subtree totals. Also called CPI.

**Relates to.** [Earned value](#earned-value), [Actual cost](#actual-cost), [Rollup](#rollup).

**How it works.** Calculated, not stored. Null when actual cost is missing or zero. Otherwise rounded half up to four decimal places.

## People and access

### Collaborator

**Definition.** A person other than the primary user who works in Keel. Architecture documents use this word for that person.

**Relates to.** [User](#user), [Owner](#owner), [Role](#role), [Grant](#grant).

**How it works.** Each collaborator is a user account. What they can open and change is their global role, their project role, and any direct grants, as listed in the [RBAC catalog](../design/rbac-catalog.md).

### User

**Definition.** A person who can sign in. The account has a unique username, a unique display name, and a password hash once a password is set.

**Relates to.** [Role](#role), [Permission](#permission), [Issue](#issue), [Comment](#comment).

**How it works.** Email, first name, last name, and date of birth are optional profile fields. Email, when set, is unique. A person signs in with a username and password, or with an API token. A session cookie lasts 14 days; the database stores the token's hash. An API token's secret is returned once, at creation, and a revoked token no longer authenticates. A person cannot be deleted while they are a reporter, an assignee, or a comment author, and cannot delete their own user. Profile, own password, own API tokens, home layout, sign out, and Help stay available to every signed-in person.

### Owner

**Definition.** The global role with unrestricted access on the server and inside every project.

**Relates to.** [Role](#role), [User](#user), [Permission](#permission).

**How it works.** More than one Owner is allowed. Only an Owner can grant or revoke Owner. The last Owner cannot be removed. Owner bypasses the permission list. An Owner is not also stored as Editor, Member, Custom, or No Access. This is the access role. It is separate from the project role *Project Owner*, which is unrestricted inside one project and still needs the global permissions a project action requires.

### Role

**Definition.** A named bundle of permissions. Every person has one global role. A person has at most one project role per project.

**Relates to.** [Permission](#permission), [Grant](#grant), [User](#user), [Owner](#owner).

**How it works.** Global roles are Owner, Admin, Editor, Member, Custom, and No Access. Member is the default. Project roles are Project Owner, Contributor, and Viewer. The bundles and the rule that one permission requires another are listed in the [RBAC catalog](../design/rbac-catalog.md). Selecting a global role replaces the roles that catalog says it replaces. A person's access is the union of their roles and their direct grants. Admin can see project names and keys and can create or delete projects and users; opening a project still requires a project role or a direct project grant.

### Permission

**Definition.** A single allowed action, either global or inside one project.

**Relates to.** [Role](#role), [Grant](#grant).

**How it works.** Saving a grant adds any permission it depends on. Removing a permission also removes the grants that depend on it. A global permission is necessary for the matching project action and is not enough by itself: creating an issue needs both the global create-issues permission and the project create-issues permission. The full list, including which role holds which permission, is the [RBAC catalog](../design/rbac-catalog.md). A missing permission is a forbidden page on the site and 403 on the API.

### Grant

**Definition.** A permission given directly to one person, or to everyone on a project, in addition to the permissions that come from a role.

**Relates to.** [Permission](#permission), [Role](#role), [Project](#project).

**How it works.** Direct grants use the same permission list as roles. A project may also name one project role, and extra project permissions, for every signed-in person. A person's own role and grants are added to that everyone grant. No Access does not receive it. A project with an everyone role or everyone permission is listed for people who otherwise only see projects they belong to.

### Request log

**Definition.** One row per signed-in HTTP request, shown in the log tracker.

**Relates to.** [User](#user), [Issue history](#issue-history).

**How it works.** The row stores the actor's display name at the time, the method, the path without the query string, the status code, the time, and a short change note on a successful write. Secrets, bodies, and query strings are not stored. The actor name is a snapshot, so a later rename does not rewrite the line. Opening the log tracker requires the view-log-tracker permission. This is separate from issue history, which records field changes on one issue.

## Related documents

* [Glossary](glossary.md)
* [Domain model](domain-model.md)
* [Data model](../design/data-model.md)
* [Capabilities](capabilities.md)
* [RBAC catalog](../design/rbac-catalog.md)
* [Use cases](use-cases.md)
