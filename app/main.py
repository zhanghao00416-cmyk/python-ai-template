from fastapi import FastAPI

from app.bootstrap import lifespan
from app.api.v1.health import router as health_router

app = FastAPI(
    title="Python AI Template",
    version="0.1.0",
    description="General-purpose Python AI platform template",
    lifespan=lifespan,
)

app.include_router(health_router)