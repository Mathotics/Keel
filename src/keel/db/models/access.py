from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from keel.db.base import Base


class PermissionRow(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("code"),
        CheckConstraint(
            "scope in ('global', 'project')",
            name="ck_permissions_scope",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64))
    scope: Mapped[str] = mapped_column(String(16))


class PermissionDependency(Base):
    __tablename__ = "permission_dependencies"

    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    requires_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("code"),
        CheckConstraint(
            "scope in ('global', 'project')",
            name="ck_roles_scope",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32))
    scope: Mapped[str] = mapped_column(String(16))
    bypass: Mapped[bool] = mapped_column(Boolean, default=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        Index(
            "uq_user_roles_global",
            "user_id",
            "role_id",
            unique=True,
            sqlite_where=text("project_id IS NULL"),
        ),
        Index(
            "uq_user_roles_project",
            "user_id",
            "project_id",
            unique=True,
            sqlite_where=text("project_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        default=None,
    )


class UserPermission(Base):
    __tablename__ = "user_permissions"
    __table_args__ = (
        Index(
            "uq_user_permissions_global",
            "user_id",
            "permission_id",
            unique=True,
            sqlite_where=text("project_id IS NULL"),
        ),
        Index(
            "uq_user_permissions_project",
            "user_id",
            "permission_id",
            "project_id",
            unique=True,
            sqlite_where=text("project_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"),
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        default=None,
    )
