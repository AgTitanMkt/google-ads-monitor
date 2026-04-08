"""Endpoint que recebe o webhook do Coupler.io após cada importação."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Request, BackgroundTasks
from pydantic import BaseModel

from app.services.monitor import run_monitoring_cycle

logger = logging.getLogger(__name__)
router = APIRouter()


class WebhookResponse(BaseModel):
    status: str
    alerts_count: int
    alerts: list


@router.post("/coupler-webhook", response_model=WebhookResponse)
async def coupler_webhook(request: Request, bg: BackgroundTasks):
    """Recebe POST do Coupler ao finalizar importação.

    O Coupler envia um payload JSON com metadados da importação.
    Não dependemos do payload — usamos como trigger para ler os dados atualizados.
    """
    body: Dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass  # Coupler pode enviar body vazio

    logger.info("Webhook recebido do Coupler. Payload keys: %s", list(body.keys()))

    alerts = run_monitoring_cycle()
    new_alerts = [a for a in alerts if a.get("new", True)]

    return WebhookResponse(
        status="processed",
        alerts_count=len(new_alerts),
        alerts=new_alerts,
    )


@router.get("/health")
async def health():
    return {"status": "ok"}
