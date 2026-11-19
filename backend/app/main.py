"""Aplicación FastAPI. Desarrollo: ``uvicorn app.main:app --reload``"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .db import init_db
from .routers import auth, cases, cohorts, model_registry, users


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="EcoAudit",
        version=__version__,
        description="Prototipo de investigación. No es un dispositivo médico.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (auth, users, cases, model_registry, cohorts):
        app.include_router(module.router)

    @app.get("/api/health", tags=["health"])
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
