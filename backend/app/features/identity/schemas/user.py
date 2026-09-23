"""Pydantic schemas for admin user-management endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr

Role = Literal["user", "staff", "admin"]


class UserCreate(BaseModel):
    email: EmailStr
    role: Role = "user"
    display_name: str | None = None
    password: str


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: Role | None = None
    password: str | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    displayName: str
    role: Role
    avatarUrl: str | None = None
    isActive: bool
    createdAt: datetime


class UserCreateResponse(BaseModel):
    user: UserResponse


class UserListResponse(BaseModel):
    data: list[UserResponse]
    total: int
