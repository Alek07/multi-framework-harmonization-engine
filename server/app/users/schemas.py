from uuid import UUID

from pydantic import EmailStr

from app.core.schemas import ORMBase


class UserBase(ORMBase):
    email: EmailStr
    full_name: str | None = None


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: UUID
    is_active: bool
