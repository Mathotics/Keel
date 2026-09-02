from datetime import datetime

from pydantic import BaseModel, ConfigDict

from keel.db.models import Comment


class CommentCreate(BaseModel):
    body: str


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    issue_id: int
    author_id: int | None
    body: str
    created_at: datetime

    @classmethod
    def of(cls, comment: Comment) -> "CommentRead":
        return cls.model_validate(comment)
