# One create per submit

* **Status:** Accepted
* **Date:** 2026-11-02

## Background

Creating an issue is a POST that assigns the next project number and inserts a row ([ADR 012](issue-realization.md)). The Create form, Add child, the JSON create route, and the phone's offline queue all call that insert. Nothing on the request says "this is the same attempt as the one already in flight." KEEL-130 records that a person sometimes ends up with two identical issues from one create. On the production server, HOUSE-191 and HOUSE-192 ("Planning for Visit to Sarah's Place") were filed 2.4 seconds apart with the same type, description, reporter, and sprint, and neither belongs to a series.

Repeating series already refuse a second copy of the same occurrence ([Repeating work via Scheduling Manager](repeating-work-scheduling-manager.md)). Those copies share a title on purpose and are not this bug.

## Problem Statement

A second submit can leave the browser or the phone before the first response arrives: a double click while the page is still up, a second tap before the button locks, or a queue retry after the server saved the issue and the response was lost. Each of those calls inserts a new issue. The two rows look the same, and the person has to notice and delete one.

## Objective(s)

- One create attempt files one issue, including when the same attempt is delivered twice.
- A person can still file two issues that happen to share a title.
- Series copies for different days keep being filed together.

## Scope and Deliverables

### In-Scope

* A nullable `client_key` on an issue, unique when set.
* The Create form and the Add child form each carry a fresh key and ignore a second submit in the browser.
* The JSON create body accepts the same key.
* The phone queue stores one key per create and sends it on every retry, and a second tap does not queue a second create.
* A repeated key for the same project and reporter returns the issue the first call filed.

### Out-of-Scope

* Merging issues that were already duplicated before this change.
* Refusing two issues with the same title. That remains a normal create.
* A key on series copies. Those inserts do not send one, and the occurrence constraint stays the guard.
* Changing a key after the issue exists.

### Deliverables

* This ADR as the behavior source of truth.
* The column, Alembic revision, service rule, web forms, JSON field, and phone queue.

## Technical Requirements

* **Must** store `client_key` as a nullable string of at most 64 characters, with a unique constraint. Several nulls are allowed, so older issues, series copies, and creates that omit a key do not collide.
* **Must** accept a key of 16 to 64 letters, digits, hyphens, or underscores, and **Must** treat a blank key as omitted.
* **Must** refuse a shorter or otherwise malformed key with `issue.invalid`.
* **Must** return the existing issue when a create repeats a key for the same project and the same reporter, and **Must Not** apply the second payload, burn another issue number, or insert a second row.
* **Must** refuse a key that already belongs to a different project or reporter with `issue.duplicate_submit`, and **Must Not** return that other issue.
* **Must** put a new key on the Create form and on Add child, and **Must** keep both forms working without JavaScript. The script **May** ignore a second submit; the key is what makes the repeat safe.
* **Must** send a stable key from the phone for one queued create, including a retry of that same queue item, and **Must** ignore a second tap while that create is still being filed.
* **Must Not** require a key. Two creates without one still file two issues, even when the titles match.
* **Must Not** copy a key onto a series occurrence.

## Consequences

* **Good:** A double click, a repeated post of the same form, and a lost-response retry each leave one issue.
* **Good:** Two chores with the same title still both exist, because each form load and each phone tap that is actually a new create gets its own key.
* **Bad:** Backing up to the create form and posting it again opens the issue that was already filed, instead of filing a second one. A new issue from that screen means loading Create again.
* **Risk:** A key that collides across people would be refused rather than filed. The keys are long random tokens, so that collision is not a practical case. Accepted.
* **Risk:** Two creates that reach the database in the same moment can both miss the "already filed" read. The unique constraint makes the loser return the winner's issue instead of inserting. A number can be skipped in that race. Numbers already skip when an issue is deleted. Accepted.

## System Design

### Technical Stack and Architecture

`create_issue` is the only insert. It trims the key, returns the earlier issue when the project and reporter match, and otherwise inserts with the key set. The insert runs in a savepoint so a unique collision rolls back that insert alone and the read is tried again. The web forms generate the key with `new_client_key` on each render. `assets/js/submit-once.js` sets `data-keel-once` and ignores a second `submit` on `[data-keel-submit-once]`. The phone generates a 32-character hex key once per queued create and puts it on the JSON body. The button guard is a ref set before the first await, so a second tap does not queue another create.

### UML Diagrams

```mermaid
sequenceDiagram
  actor Person
  participant Form
  participant Create as create_issue
  participant DB
  Person->>Form: Create issue
  Form->>Create: POST client_key=K
  Create->>DB: insert issue K
  DB-->>Create: KEEL-1
  Person->>Form: Create issue again
  Form->>Create: POST client_key=K
  Create->>DB: select client_key=K
  DB-->>Create: KEEL-1
  Create-->>Form: KEEL-1
```

## Supporting Documentation

* [Data model](../design/data-model.md)
* [API reference](../design/api.md)
* [UI design](../design/ui.md)
* [Use cases](../architecture/use-cases.md)
