from fastapi import FastAPI

from app.bootstrap import lifespan
from app.api.v1.health import router as health_router
from app.api.v1.task import router as task_router
from app.middleware.trace import TraceMiddleware
from app.middleware.exception import exception_handler_middleware

app = FastAPI(
    title="Python AI Template",
    version="0.1.0",
    description="General-purpose Python AI platform template",
    lifespan=lifespan,
)

app.add_middleware(TraceMiddleware)
app.middleware("http")(exception_handler_middleware)

app.include_router(health_router)
app.include_router(task_router)