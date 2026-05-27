from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import health, papers, ideas, agent, usage, auth, jobs
from .database import init_db
from .config import settings, parse_cors_allowed_origins
from .services.job_worker import job_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await job_worker.start()
    yield
    await job_worker.stop()


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_cors_allowed_origins(settings.CORS_ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(health.router)
app.include_router(papers.router)
app.include_router(ideas.router)
app.include_router(agent.router)
app.include_router(usage.router)
app.include_router(jobs.router)


@app.get("/")
async def root():
    return {"message": "Research Paper Assistant API", "version": settings.APP_VERSION}
