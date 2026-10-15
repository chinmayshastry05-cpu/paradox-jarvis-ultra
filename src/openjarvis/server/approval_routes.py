"""REST endpoints for the proactive-agent approval queue + tool approvals.

Tool approvals (``/v1/approvals/tool``) are the server side of the
central confirmation gate: a client grants an approval for ONE exact
(tool, arguments) pair, and the next agent turn's ToolExecutor consumes
it (single-use) via ``ConfirmationGate.consume_matching``. The token
returned by the grant is only needed to revoke the approval before it
is consumed. Approvals expire (default 5 minutes, max 1 hour) and are
in-memory only — a server restart invalidates all of them.

There is no blanket/auto approval endpoint: every grant binds to exact
arguments.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from openjarvis.security.confirmation import ConfirmationGate
from openjarvis.tools.approval_store import (
    STATUS_APPROVED,
    STATUS_DENIED,
    ApprovalStore,
    PendingAction,
)

try:
    from fastapi import APIRouter, HTTPException, Request
except ImportError:
    raise ImportError("fastapi is required for approval routes")

logger = logging.getLogger(__name__)

router = APIRouter()

# Singleton that shares the same DB file as ProactiveAgent (WAL mode is safe)
_store: Optional[ApprovalStore] = None

# Fallback gate used when no app-state gate is available (e.g. the
# endpoint is called without an app, or in tests). Production routes
# share the gate on ``app.state.confirmation_gate`` so grants reach the
# executors running the agents.
_gate: Optional[ConfirmationGate] = None


def _get_store() -> ApprovalStore:
    global _store
    if _store is None:
        _store = ApprovalStore()
    return _store


def _get_gate(request: Optional[Request] = None) -> ConfirmationGate:
    global _gate
    if request is not None:
        app_gate = getattr(getattr(request, "app", None), "state", None)
        if app_gate is not None:
            shared = getattr(app_gate, "confirmation_gate", None)
            if isinstance(shared, ConfirmationGate):
                return shared
    if _gate is None:
        _gate = ConfirmationGate()
    return _gate


def _serialize(action: PendingAction) -> Dict[str, Any]:
    return {
        "id": action.id,
        "action_type": action.action_type,
        "description": action.description,
        "payload": action.payload,
        "permission_key": action.permission_key,
        "tier": action.tier,
        "status": action.status,
        "created_at": action.created_at,
        "expires_at": action.expires_at,
    }


# -- Tool approvals (central confirmation gate) ------------------------------
# Defined before the {action_id} routes so /v1/approvals/tool/* is never
# captured as an action id.


@router.post("/v1/approvals/tool")
async def grant_tool_approval(body: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Grant a single-use approval for one exact (tool, arguments) pair.

    Body: ``{"tool_name": str, "arguments": dict, "ttl_seconds"?: number}``.
    Returns ``{"token", "tool_name", "expires_at"}``. The token is only
    needed to revoke; execution consumes the grant by exact match.
    """
    gate = _get_gate(request)
    tool_name = body.get("tool_name")
    arguments = body.get("arguments")
    if not isinstance(tool_name, str) or not tool_name:
        raise HTTPException(
            status_code=422, detail="tool_name must be a non-empty string"
        )
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=422, detail="arguments must be a JSON object")
    ttl = body.get("ttl_seconds", 300)
    try:
        ttl = float(ttl)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422, detail="ttl_seconds must be a number"
        ) from None
    try:
        approval = gate.grant(tool_name, arguments, ttl_seconds=ttl)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    logger.info("Tool approval granted via API for tool %s", tool_name)
    return {
        "token": approval.token,
        "tool_name": approval.tool_name,
        "expires_at": datetime.fromtimestamp(
            approval.expires_at, tz=timezone.utc
        ).isoformat(),
    }


@router.post("/v1/approvals/tool/revoke")
async def revoke_tool_approval(
    body: Dict[str, Any], request: Request
) -> Dict[str, Any]:
    """Revoke a previously granted tool approval. Body: ``{"token": str}``."""
    gate = _get_gate(request)
    token = body.get("token")
    if not isinstance(token, str) or not token:
        raise HTTPException(status_code=422, detail="token must be a non-empty string")
    revoked = gate.revoke(token)
    if not revoked:
        raise HTTPException(status_code=404, detail="Approval not found")
    logger.info("Tool approval revoked via API")
    return {"status": "revoked"}


# -- Proactive-agent approval queue (unchanged) ------------------------------


@router.get("/v1/approvals/pending")
async def list_pending_approvals() -> Dict[str, Any]:
    store = _get_store()
    store.expire_stale()
    actions = store.list_pending()
    return {"actions": [_serialize(a) for a in actions], "count": len(actions)}


@router.post("/v1/approvals/{action_id}/approve")
async def approve_action(action_id: str) -> Dict[str, Any]:
    store = _get_store()
    action = store.get_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    store.update_status(action_id, STATUS_APPROVED)
    logger.info("Action %s approved via UI", action_id)
    return {"status": "approved", "id": action_id}


@router.post("/v1/approvals/{action_id}/deny")
async def deny_action(action_id: str) -> Dict[str, Any]:
    store = _get_store()
    action = store.get_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    store.update_status(action_id, STATUS_DENIED)
    logger.info("Action %s denied via UI", action_id)
    return {"status": "denied", "id": action_id}


__all__ = ["router"]
