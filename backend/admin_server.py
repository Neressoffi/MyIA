"""Serveur dedie au dashboard administrateur (port separe de JARVIS).

JARVIS principal (chat) : port 8765 par defaut
Dashboard admin          : port 8767 par defaut

Les deux partagent le fichier donnees/analytics.json.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.responses import JSONResponse

from . import analytics, config

app = FastAPI(title="JARVIS - Dashboard administrateur")

_origines = [
    f"http://127.0.0.1:{config.ADMIN_PORT}",
    f"http://localhost:{config.ADMIN_PORT}",
]
if config.DEMO_MODE:
    _origines.append("*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origines,
    allow_credentials=config.DEMO_MODE is False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


class AdminLoginRequest(BaseModel):
    mot_de_passe: str


_ROUTES_PUBLIQUES = {"/api/admin/login", "/api/admin/status"}


@app.middleware("http")
async def protection_admin(request, call_next):
    path = request.url.path
    if path.startswith("/api/admin/") and path not in _ROUTES_PUBLIQUES:
        token = analytics.extraire_token_admin(request.headers.get("authorization"))
        if not analytics.admin_session_valide(token):
            return JSONResponse({"detail": "Acces admin refuse."}, status_code=401)

    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response


@app.get("/api/admin/status")
async def admin_status():
    return {
        "configure": analytics.admin_configure(),
        "analytics": config.ANALYTICS_ENABLED,
        "port_jarvis": config.PORT,
        "port_dashboard": config.ADMIN_PORT,
    }


@app.post("/api/admin/login")
async def admin_login(req: AdminLoginRequest):
    try:
        token = analytics.admin_connecter(req.mot_de_passe)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"ok": True, "token": token}


@app.get("/api/admin/rapport")
async def admin_rapport(authorization: Optional[str] = Header(None)):
    token = analytics.extraire_token_admin(authorization)
    if not analytics.admin_session_valide(token):
        raise HTTPException(status_code=401, detail="Acces admin refuse.")
    return analytics.rapport()


@app.get("/api/admin/conversation/{conv_id}")
async def admin_conversation(conv_id: str, authorization: Optional[str] = Header(None)):
    token = analytics.extraire_token_admin(authorization)
    if not analytics.admin_session_valide(token):
        raise HTTPException(status_code=401, detail="Acces admin refuse.")
    conv = analytics.conversation_par_id(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation introuvable.")
    return conv


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "dashboard"}


_dashboard = Path(__file__).resolve().parent.parent / "dashboard"
if _dashboard.exists():
    app.mount("/", StaticFiles(directory=str(_dashboard), html=True), name="dashboard")
