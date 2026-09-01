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
