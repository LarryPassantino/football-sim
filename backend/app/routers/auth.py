from fastapi import APIRouter, Depends, HTTPException
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import (
    create_access_token, create_refresh_token,
    decode_token, hash_password, verify_password,
)
from ..dependencies import get_current_coach, get_db
from ..models import Coach
from ..schemas import FcmTokenRequest, LoginRequest, RefreshRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix='/auth', tags=['auth'])


@router.post('/register', response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Coach).where(Coach.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail='Email already registered')

    coach = Coach(
        email=body.email,
        hashed_password=hash_password(body.password),
        display_name=body.display_name,
    )
    db.add(coach)
    await db.flush()

    access  = create_access_token(str(coach.id))
    refresh = create_refresh_token(str(coach.id))
    coach.refresh_token_hash = hash_password(refresh)

    await db.commit()
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post('/login', response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Coach).where(Coach.email == body.email))
    coach  = result.scalar_one_or_none()
    if not coach or not verify_password(body.password, coach.hashed_password):
        raise HTTPException(status_code=401, detail='Invalid credentials')

    access  = create_access_token(str(coach.id))
    refresh = create_refresh_token(str(coach.id))
    coach.refresh_token_hash = hash_password(refresh)

    await db.commit()
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post('/refresh', response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get('type') != 'refresh':
            raise HTTPException(status_code=401, detail='Invalid token type')
        coach_id = payload.get('sub')
    except JWTError:
        raise HTTPException(status_code=401, detail='Invalid token')

    import uuid
    coach = await db.get(Coach, uuid.UUID(coach_id))
    if not coach or not coach.refresh_token_hash:
        raise HTTPException(status_code=401, detail='Session expired')

    access  = create_access_token(str(coach.id))
    refresh = create_refresh_token(str(coach.id))
    coach.refresh_token_hash = hash_password(refresh)

    await db.commit()
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post('/fcm-token', status_code=204)
async def register_fcm_token(
    body: FcmTokenRequest,
    coach: Coach = Depends(get_current_coach),
    db: AsyncSession = Depends(get_db),
):
    coach.fcm_token = body.token
    await db.commit()
