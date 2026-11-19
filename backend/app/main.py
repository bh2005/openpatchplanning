"""OpenPatchPlanning – FastAPI-Anwendung."""
from __future__ import annotations

import logging

import anyio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import auth
from .config import settings
from .routers import accounts, imports, masterdata, overview
from .static import find_static_dir, register_static

logger = logging.getLogger("opp")

app = FastAPI(
    title="OpenPatchPlanning API",
    version="0.1.0",
    description="Verwaltung und Planung von Verkabelung/Patchungen – Stammdaten, Import, Aufträge.",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

if settings.cors_origins.strip():
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                       allow_methods=["*"], allow_headers=["*"])

app.include_router(accounts.router)
app.include_router(masterdata.router)
app.include_router(imports.router)
app.include_router(overview.router)


@app.on_event("startup")
async def startup() -> None:
    generated = auth.init()
    if generated:
        logger.warning("Start-Admin '%s' angelegt mit generiertem Passwort: %s (bitte nach der Anmeldung ändern)",
                       settings.admin_username, generated)
    # Sync-Routen laufen in einem Thread-Pool; die Obergrenze verhindert, dass viele parallele Anfragen eine kleine VM überlasten.
    anyio.to_thread.current_default_thread_limiter().total_tokens = 8


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "version": app.version}


# Muss zuletzt stehen: liefert die Oberfläche (falls gebaut) für alle Pfade außerhalb der API
register_static(app, find_static_dir(settings.static_dir))
