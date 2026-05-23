import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'


class RefreshRequest(BaseModel):
    refresh_token: str


class LeagueCreateRequest(BaseModel):
    name: str


class LeagueResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    created_at: datetime

    model_config = {'from_attributes': True}


class TeamResponse(BaseModel):
    id: uuid.UUID
    name: str
    conference: str
    division: str
    is_cpu: bool

    model_config = {'from_attributes': True}


class GameResponse(BaseModel):
    id: uuid.UUID
    week: int
    home_team_id: uuid.UUID
    away_team_id: uuid.UUID
    home_score: int | None
    away_score: int | None
    status: str

    model_config = {'from_attributes': True}
