from fastapi import FastAPI

from app.api.v1.agent import router as agent_router
from app.api.v1.chat import router as chat_router
from app.api.v1.health import router as health_router
from app.api.v1.intent import router as intent_router
from app.api.v1.kb import router as kb_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.prompt import router as prompt_router
from app.api.v1.task import router as task_router
from app.api.v1.workflow import router as workflow_router
from app.bootstrap import lifespan
from app.middleware.auth import auth_middleware
from app.middleware.exception import exception_handler_middleware
from app.middleware.metrics import metrics_middleware
from app.middleware.rate_limit import rate_limit_middleware
from app.middleware.trace import TraceMiddleware

app = FastAPI(
    title="Python AI Template",
    version="0.1.0",
    description="General-purpose Python AI platform template",
    lifespan=lifespan,
)

# Middleware registration order: last registered = outermost = executes first.
# Desired execution: TraceMiddleware → auth → rate_limit → exception → metrics → handler
app.middleware("http")(metrics_middleware)
app.middleware("http")(exception_handler_middleware)
app.middleware("http")(rate_limit_middleware)
app.middleware("http")(auth_middleware)
app.add_middleware(TraceMiddleware)

app.include_router(health_router)
app.include_router(task_router)
app.include_router(agent_router)
app.include_router(workflow_router)
app.include_router(chat_router)
app.include_router(kb_router)
app.include_router(intent_router)
app.include_router(prompt_router)
app.include_router(metrics_router)
