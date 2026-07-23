from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.users.models import User
from app.users.repository import UserRepository
from app.users.schemas import UserCreate, UserRead
from app.users.service import UserService

router = APIRouter()


def get_user_service(db: Annotated[AsyncSession, Depends(get_db)]) -> UserService:
    return UserService(repository=UserRepository(db))


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, service: UserServiceDep) -> User:
    return await service.register_user(data)


@router.get("/{user_id}", response_model=UserRead)
async def read_user(user_id: UUID, service: UserServiceDep) -> User:
    return await service.get_user(user_id)


@router.get("/", response_model=list[UserRead])
async def list_users(service: UserServiceDep, skip: int = 0, limit: int = 100) -> list[User]:
    return await service.list_users(skip=skip, limit=limit)
