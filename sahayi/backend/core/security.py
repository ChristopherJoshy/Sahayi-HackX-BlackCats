"""Simple shared-token auth for the SAHAYI MVP dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException, WebSocket, status

from core.config import get_settings

# Dummy doctor payload used when Firebase auth is bypassed (MVP mode).
_DUMMY_DOCTOR: dict[str, Any] = {"uid": "mvp-doctor-001", "email": "doctor@sahayi.local"}


async def require_doctor(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Authorize a doctor request via the shared dashboard token.

    Args:
        authorization: Incoming Authorization header.
    Returns:
        Dummy doctor payload when the token matches.
    Agent:
        Platform
    """

    settings = get_settings()
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token and token == settings.dashboard_shared_token:
        return _DUMMY_DOCTOR
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing dashboard token",
    )


async def require_doctor_socket(websocket: WebSocket) -> dict[str, Any]:
    """Authorize a doctor WebSocket connection via query-param token.

    Args:
        websocket: Incoming FastAPI WebSocket instance.
    Returns:
        Dummy doctor payload when the token matches.
    Agent:
        Platform
    """

    settings = get_settings()
    token = websocket.query_params.get("token")
    if token and token == settings.dashboard_shared_token:
        return _DUMMY_DOCTOR
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing dashboard token",
    )
