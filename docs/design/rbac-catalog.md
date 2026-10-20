# RBAC catalog

Roles, permissions, and the dependencies between permissions. This is the map for [Role-based access](../adr/role-based-access.md).

A direct grant uses the same permissions as a role. Saving a grant adds anything it depends on. Removing a permission also removes the grants that depend on it. A person's access is the union of their roles and direct grants. Owner bypasses the list.

## Global roles

* **Owner.** Unrestricted on the whole server and inside every project. More than one Owner is allowed. Only an Owner can grant or revoke Owner. The last Owner cannot be removed. An Owner is not also stored as Editor, Member, or Custom.
* **Admin.** Every global permission. No project permission. An Admin can see project names and keys, and can create or delete projects and users. Opening a project still requires a project role or a direct project grant. An Admin is not also stored as Editor, Member, or Custom.
* **Editor.** View projects, and the global create, edit, and delete permissions for issues, schedules, and sprints, plus Create comments and Delete comments. Comments are created and deleted; there is no separate edit-comment permission. Creating and deleting projects and users stay with Admin, as do renaming users, resetting passwords, and the Admin menu. Work in a project still needs that project's role. Selecting Editor replaces Member and Custom.
* **Member.** View projects, the global create and edit permissions for issues and schedules, and the global Create comments permission. Not delete, not sprints, and not Delete comments. Work in a project still needs that project's role. This is the default global role.
* **Custom.** No permissions of its own. The person's global access is only the permissions granted to that person, each one chosen for them. Selecting Custom replaces Member.

Every person has a global role. A person may hold Owner and Admin together. Member is the role when Owner, Admin, Editor, and Custom are all clear. The global page shows Member in that case, Editor when Editor is selected, and Custom when Custom is selected. Selecting Owner or Admin clears Editor, Member, and Custom. Clearing Owner and Admin assigns Member again, unless Editor or Custom is selected.

## Project roles

One project role per person per project, plus any direct grants.

* **Viewer.** View issues, backlog, board, calendar, sprints, and schedules.
* **Contributor.** Viewer, plus create issues, edit issues, update issues, comment, delete own comments, and manage dependencies. Delete own comments applies only to comments that person wrote. Commenting also needs the global Create comments permission. Deleting a comment also needs the global Delete comments permission. Member holds the first and not the second, so a Member who is a Contributor can comment and cannot delete comments.
* **Project Owner.** Every project permission.

Several Project Owners are allowed. A Project Owner cannot remove the last Project Owner of that project. A global Owner can.

## Global permissions

* **View projects.** See every project name and key. Without it, the project list includes only projects where the person holds a project role or a direct project grant. Member holds this permission.
* **Create projects.** Requires View projects. The creator becomes Project Owner of the new project.
* **Delete projects.** Requires View projects. Deletes any project.
* **Display Admin menu.** Shows the Admin control in the top bar.
* **View Log Tracker.** Requires Display Admin menu.
* **View global RBAC page.** Requires Display Admin menu.
* **Manage global RBAC.** Requires View global RBAC page. An Admin cannot change Owner membership.
* **View users.** The Users link under the Admin menu. It does not require Display Admin menu. When it is the only Admin item that person can open, the Admin menu still appears. The people directory used for assignees stays available to every signed-in person.
* **Create users.** Requires View users. A new person is Member.
* **Delete users.** Requires View users. A person still cannot delete their own user. Deleting an Owner follows the Owner rules above.
* **Rename users.** Requires View users.
* **Reset another user's password.** Requires View users. It does not change the signed-in person's own password.
* **Create issues.** Requires View projects. Necessary before creating an issue in a project. It does not create issues in every project.
* **Edit issues.** Requires View projects. Necessary before editing issue fields in a project. It does not edit issues in every project. Updating status, assignee, or sprint placement is a separate project permission and has no global gate.
* **Delete issues.** Requires View projects. Necessary before deleting an issue in a project. It does not delete issues in every project.
* **Create comments.** Requires View projects. Necessary before commenting in a project. It does not allow comments in every project.
* **Delete comments.** Requires View projects. Necessary before deleting one's own comments or anyone's comments in a project. It does not delete comments in every project.
* **Create schedules.** Requires View projects. Necessary before creating a schedule in a project. It does not create schedules in every project.
* **Edit schedules.** Requires View projects. Necessary before editing a schedule in a project, including pause and resume. It does not edit schedules in every project.
* **Delete schedules.** Requires View projects. Necessary before deleting a schedule in a project. It does not delete schedules in every project.
* **Create sprints.** Requires View projects. Necessary before creating a sprint in a project. It does not create sprints in every project.
* **Edit sprints.** Requires View projects. Necessary before editing a sprint in a project. It does not edit sprints in every project.
* **Delete sprints.** Requires View projects. Necessary before deleting a sprint in a project. It does not delete sprints in every project. Starting or completing a sprint has no global gate.

Admin holds every global permission. Editor holds View projects and the global create, edit, and delete permissions for issues, schedules, and sprints, plus Create comments and Delete comments. Member holds View projects, Create issues, Edit issues, Create comments, Create schedules, and Edit schedules. Custom holds none. Owner bypasses them.

## Project permissions

View:

* **View issues.** The project issue list and an issue page, including history.
* **View backlog.** Requires View issues.
* **View board.** Requires View issues.
* **View calendar.** Requires View issues.
* **View sprints.** Does not require View issues.
* **View schedules.** Does not require View issues.

Issue work:

* **Create issues in a project.** Requires View issues, and the global Create issues permission. The global permission is necessary and is not sufficient on its own.
* **Edit issues in a project.** Requires View issues, and the global Edit issues permission. Title, description, type, priority, dates, estimates, labels, and parent or child links.
* **Update issues.** Requires View issues. Status, assignee, and which existing sprint the issue is on. No global gate.
* **Delete issues in a project.** Requires View issues, and the global Delete issues permission.
* **Comment on issues.** Requires View issues, and the global Create comments permission. The global permission is necessary and is not sufficient on its own.
* **Delete own comments.** Requires Comment on issues, and the global Delete comments permission. Applies only to comments that person wrote.
* **Delete any comment.** Requires Delete own comments, and the global Delete comments permission. Includes comments written by other people.
* **Manage dependencies.** Requires View issues.

Sprints:

* **Create sprints in a project.** Requires View sprints, and the global Create sprints permission.
* **Edit sprints in a project.** Requires View sprints, and the global Edit sprints permission. Name and dates.
* **Delete sprints in a project.** Requires View sprints, and the global Delete sprints permission.
* **Start or complete sprints.** Requires View sprints. No global gate.

Schedules:

* **Create schedules in a project.** Requires View schedules, and the global Create schedules permission.
* **Edit schedules in a project.** Requires View schedules, and the global Edit schedules permission. Includes pause and resume.
* **Delete schedules in a project.** Requires View schedules, and the global Delete schedules permission.

Project administration:

* **Change project settings.** Requires View issues. Name, description, sprint cadence, cadence length, and lookahead.
* **Delete this project.** Requires View issues. This project only.
* **View project RBAC page.** Requires View issues.
* **Manage project RBAC.** Requires View project RBAC page.

Project route checks for these permissions are KEEL-105. The rows and the role bundles exist now.

## Always allowed

Every signed-in person can open their profile, change their own password, manage their own API tokens, arrange home and nav, sign out, and open Help, License, `/docs`, and `/redoc`. `GET /health`, `/login`, and `/assets/` stay public. Server CLI backup, restore, `keel users set-password`, and `keel users create-token` stay operator actions on the machine.

## Signed-in but not allowed

A signed-in person who opens a global page they cannot use sees a forbidden page in the normal shell. The API returns 403. They are not sent to `/login`.

## Day-one assignments

Stored by the upgrade. Project checks that would enforce them ship with KEEL-105.

* **jacob_hootman:** Owner, and Project Owner on BOAT, HOUSE, KEEL, and PERSONAL.
* **Cursor:** Member, and Contributor on KEEL.
* **danielle_hootman:** Member, and Contributor on HOUSE.
* **Anyone else with no global role:** Member.

If jacob_hootman is missing and the server has no Owner, the earliest user becomes Owner.
