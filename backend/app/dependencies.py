import uuid
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import decode_token
from .database import SessionLocal
from .models import Coach

security = HTTPBearer()


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


async def get_current_coach(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Coach:
    try:
        payload = decode_token(credentials.credentials)
        if payload.get('type') != 'access':
            raise HTTPException(status_code=401, detail='Invalid token type')
        coach_id = payload.get('sub')
    except JWTError:
        raise HTTPException(status_code=401, detail='Invalid token')

    coach = await db.get(Coach, uuid.UUID(coach_id))
    if not coach:
        raise HTTPException(status_code=401, detail='Coach not found')
    return coach
