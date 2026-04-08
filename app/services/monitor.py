"""Compara snapshots e detecta eventos de alerta."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone, date
from typing import List, Dict, Any, Optional

from sqlalchemy import select, desc

from app.config import get_settings
from app.database.connection import get_session
from app.models.campaign import CampaignSnapshot, AlertLog
from app.services.coupler_reader import read_latest_campaigns

logger = logging.getLogger(__name__)


# ---------- ORQUESTRADOR PRINCIPAL -------------------------------------------

def run_monitoring_cycle() -> List[Dict[str, str]]:
    """Executa um ciclo completo: lê dados, salva snapshot, detecta eventos.

    Retorna lista de alertas gerados.
    """
    batch_id = _make_batch_id()
    campaigns = read_latest_campaigns()

    if not campaigns:
        logger.warning("Nenhum dado de campanha recebido do Coupler.")
        return []

    # Checa duplicidade — se este batch já foi processado, pula
    if _batch_already_processed(batch_id, campaigns):
        logger.info("Batch %s já processado (idempotência). Pulando.", batch_id)
        return []

    _save_snapshots(campaigns, batch_id)

    alerts = _detect_events(campaigns, batch_id)

    for alert in alerts:
        send_alert(alert["message"])

    return alerts


# ---------- SNAPSHOTS --------------------------------------------------------

def _make_batch_id() -> str:
    """Gera um ID de batch baseado no timestamp (minuto)."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%d_%H%M")


def _batch_already_processed(batch_id: str, campaigns: List[Dict]) -> bool:
    """Verifica idempotência comparando hash do conteúdo."""
    content_hash = _hash_campaigns(campaigns)
    combined_key = f"{batch_id}_{content_hash}"

    with get_session() as session:
        existing = session.execute(
            select(CampaignSnapshot)
            .where(CampaignSnapshot.batch_id == combined_key)
            .limit(1)
        ).scalar_one_or_none()
        return existing is not None


def _hash_campaigns(campaigns: List[Dict]) -> str:
    raw = str(sorted([str(sorted(c.items())) for c in campaigns]))
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _save_snapshots(campaigns: List[Dict], batch_id: str):
    content_hash = _hash_campaigns(campaigns)
    combined_key = f"{batch_id}_{content_hash}"

    with get_session() as session:
        for c in campaigns:
            session.add(CampaignSnapshot(
                campaign_id=str(c["campaign_id"]),
                campaign_name=c.get("campaign_name", ""),
                status=c.get("status", "UNKNOWN"),
                impressions=float(c.get("impressions", 0)),
                cost=float(c.get("cost", 0)),
                report_date=str(c.get("report_date", "")),
                batch_id=combined_key,
            ))
    logger.info("Snapshot salvo: batch=%s, campanhas=%d", combined_key, len(campaigns))


# ---------- DETECÇÃO DE EVENTOS ----------------------------------------------

def _detect_events(campaigns: List[Dict], batch_id: str) -> List[Dict[str, str]]:
    alerts: List[Dict[str, str]] = []
    settings = get_settings()

    # Agrupa por campaign_id para comparar today vs yesterday
    by_campaign: Dict[str, Dict[str, Dict]] = {}
    for c in campaigns:
        cid = str(c["campaign_id"])
        rd = str(c.get("report_date", ""))
        by_campaign.setdefault(cid, {})[rd] = c

    for cid, dates in by_campaign.items():
        today_data = _pick_today(dates)
        yesterday_data = _pick_yesterday(dates)

        if not today_data:
            continue

        name = today_data.get("campaign_name", cid)

        # 1. Campanha parou (impressions hoje=0, ontem>0)
        imp_today = float(today_data.get("impressions", 0))
        imp_yesterday = float(yesterday_data.get("impressions", 0)) if yesterday_data else 0

        if imp_today == 0 and imp_yesterday > 0:
            alerts.append(_create_alert(
                "campaign_stopped", cid, batch_id,
                f"🚨 Campanha PAROU: '{name}' (id={cid}) — "
                f"impressions hoje=0, ontem={imp_yesterday:.0f}",
            ))

        # 2. Spend zerou
        cost_today = float(today_data.get("cost", 0))
        cost_yesterday = float(yesterday_data.get("cost", 0)) if yesterday_data else 0

        if cost_today == 0 and cost_yesterday > settings.spend_threshold:
            alerts.append(_create_alert(
                "spend_zeroed", cid, batch_id,
                f"💰 Spend ZEROU: '{name}' (id={cid}) — "
                f"cost hoje=0, ontem={cost_yesterday:.2f}",
            ))

        # 3. Status mudou
        if yesterday_data:
            status_today = today_data.get("status", "")
            status_yesterday = yesterday_data.get("status", "")
            if status_today and status_yesterday and status_today != status_yesterday:
                alerts.append(_create_alert(
                    "status_changed", cid, batch_id,
                    f"🔄 Status MUDOU: '{name}' (id={cid}) — "
                    f"{status_yesterday} → {status_today}",
                ))

    return alerts


def _pick_today(dates: Dict[str, Dict]) -> Optional[Dict]:
    today_str = date.today().isoformat()
    return dates.get(today_str) or dates.get("today") or dates.get(
        sorted(dates.keys())[-1]  # fallback: data mais recente
    )


def _pick_yesterday(dates: Dict[str, Dict]) -> Optional[Dict]:
    from datetime import timedelta
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    return dates.get(yesterday_str) or dates.get("yesterday") or (
        dates.get(sorted(dates.keys())[0]) if len(dates) > 1 else None
    )


# ---------- ALERTAS ----------------------------------------------------------

def _create_alert(
    alert_type: str, campaign_id: str, batch_id: str, message: str
) -> Dict[str, str]:
    """Cria alerta com idempotência — mesmo evento não dispara duas vezes no dia."""
    today_str = date.today().isoformat()
    alert_key = f"{alert_type}:{campaign_id}:{today_str}"

    with get_session() as session:
        existing = session.execute(
            select(AlertLog).where(AlertLog.alert_key == alert_key).limit(1)
        ).scalar_one_or_none()

        if existing:
            logger.info("Alerta já disparado hoje: %s", alert_key)
            return {"type": alert_type, "campaign_id": campaign_id,
                    "message": f"[DUPLICADO] {message}", "new": False}

        session.add(AlertLog(
            alert_key=alert_key,
            alert_type=alert_type,
            campaign_id=campaign_id,
            message=message,
        ))

    return {"type": alert_type, "campaign_id": campaign_id,
            "message": message, "new": True}


def send_alert(message: str):
    """Dispara alerta. Atualmente loga; troque por Slack/email em produção."""
    logger.warning("🔔 ALERTA: %s", message)
