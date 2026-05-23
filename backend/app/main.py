from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI

from .routers import auth, leagues


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title='Football Sim API', lifespan=lifespan)

app.include_router(auth.router)
app.include_router(leagues.router)


@app.get('/health')
async def health():
    return {'status': 'ok'}
