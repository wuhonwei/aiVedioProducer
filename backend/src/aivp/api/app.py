from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from aivp.api.routes_bible import router as bible_router
from aivp.api.routes_health import router as health_router
from aivp.api.routes_jobs import router as jobs_router
from aivp.api.routes_projects import router as projects_router
from aivp.config import Settings
from aivp.db import Base
from aivp.llm.ollama_client import OllamaClient


def _error_body(code: str, message: str, details=None) -> dict:
    body = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return body


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    app = FastAPI(title="AIVP Text Layer")
    app.state.settings = settings
    app.state.SessionLocal = SessionLocal
    app.state.llm = OllamaClient(settings.ollama_base_url, settings.ollama_model)
    app.state.run_jobs_inline = False

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        details = exc.detail if not isinstance(exc.detail, str) else None
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        code = {
            404: "not_found",
            400: "bad_request",
            409: "conflict",
            422: "validation_error",
        }.get(exc.status_code, "http_error")
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code, message, details if details != message else None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=_error_body("validation_error", "Request validation failed", exc.errors()),
        )

    app.include_router(projects_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(bible_router, prefix="/api")
    app.include_router(health_router, prefix="/api")
    return app
