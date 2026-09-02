from typing import Any, ClassVar


class KeelError(Exception):
    """Base class for errors Keel raises deliberately."""


class NotFoundError(KeelError):
    """A resource was addressed that does not exist."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DomainError(KeelError):
    """A refused operation, carrying a code clients can branch on."""

    code: ClassVar[str] = "domain.error"
    status_code: ClassVar[int] = 409

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context)

    def as_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "context": self.context,
        }


class DuplicateUserNameError(DomainError):
    code = "user.duplicate_name"


class InvalidUserNameError(DomainError):
    code = "user.invalid_name"
    status_code = 422


class UserInUseError(DomainError):
    code = "user.in_use"


class DuplicateProjectKeyError(DomainError):
    code = "project.duplicate_key"


class InvalidProjectKeyError(DomainError):
    code = "project.invalid_key"
    status_code = 422


class InvalidProjectNameError(DomainError):
    code = "project.invalid_name"
    status_code = 422


class InvalidIssueError(DomainError):
    code = "issue.invalid"
    status_code = 422


class InvalidDurationError(DomainError):
    code = "issue.invalid_duration"
    status_code = 422


class InvalidCommentError(DomainError):
    code = "comment.invalid"
    status_code = 422


class InvalidParentTypeError(DomainError):
    code = "issue.invalid_parent_type"


class InvalidParentError(DomainError):
    code = "issue.invalid_parent"


class ParentCycleError(DomainError):
    code = "issue.parent_cycle"


class IssueHasChildrenError(DomainError):
    code = "issue.has_children"


class InvalidSprintError(DomainError):
    code = "sprint.invalid"
    status_code = 422


class SprintAlreadyActiveError(DomainError):
    code = "sprint.already_active"


class SprintInvalidTransitionError(DomainError):
    code = "sprint.invalid_transition"


class SprintProjectMismatchError(DomainError):
    code = "sprint.project_mismatch"


class DependencyCycleError(DomainError):
    code = "dependency.cycle"


class DependencySelfLinkError(DomainError):
    code = "dependency.self_link"


class DependencyDuplicateError(DomainError):
    code = "dependency.duplicate"
