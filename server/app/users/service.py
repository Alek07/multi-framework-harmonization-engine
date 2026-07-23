from uuid import UUID

from app.core.security import hash_password
from app.users.exceptions import UserAlreadyExistsError, UserNotFoundError
from app.users.models import User
from app.users.repository import UserRepository
from app.users.schemas import UserCreate


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    async def register_user(self, data: UserCreate) -> User:
        if await self.repository.get_by_email(data.email):
            raise UserAlreadyExistsError(data.email)

        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
        )
        return await self.repository.add(user)

    async def get_user(self, user_id: UUID) -> User:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return user

    async def list_users(self, skip: int = 0, limit: int = 100) -> list[User]:
        return await self.repository.list(skip=skip, limit=limit)
