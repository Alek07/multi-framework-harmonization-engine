from uuid import UUID

from app.core.exceptions import ConflictError, NotFoundError


class UserAlreadyExistsError(ConflictError):
    def __init__(self, email: str):
        super().__init__(detail=f"User with email {email} already exists")


class UserNotFoundError(NotFoundError):
    def __init__(self, user_id: UUID):
        super().__init__(detail=f"User {user_id} not found")
