"""Endpoints do dashboard — campanhas, alertas, snapshots, métricas."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Query
from sqlalchemy import select, func, desc, distinct

from app.database.connection import get_session
from app.models.campaign import CampaignSnapshot, AlertLog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/campaigns")
def list_campaigns():
    """Retorna o estado mais recente de cada campanha."""
    with get_session() as session:
        # Pega o batch mais recente
        latest_batch = session.execute(
            select(CampaignSnapshot.batch_id)
            .order_by(desc(CampaignSnapshot.ingested_at))
            .limit(1)
        ).scalar_one_or_none()

        if not latest_batch:
            return {"campaigns": [], "last_update": None}

        rows = session.execute(
            select(CampaignSnapshot)
            .where(CampaignSnapshot.batch_id == latest_batch)
            .order_by(CampaignSnapshot.campaign_name)
        ).scalars().all()

        campaigns = {}
        for r in rows:
            cid = r.campaign_id
            if cid not in campaigns:
                campaigns[cid] = {
                    "campaign_id": cid,
                    "campaign_name": r.campaign_name,
                    "status": r.status,
                    "today": {},
                    "yesterday": {},
                }
            date_key = "today" if r.report_date in ("today", _today_str()) else "yesterday"
            campaigns[cid][date_key] = {
                "impressions": r.impressions,
                "cost": r.cost,
                "report_date": r.report_date,
            }

        return {
            "campaigns": list(campaigns.values()),
            "last_update": rows[0].ingested_at.isoformat() if rows else None,
        }


@router.get("/alerts")
def list_alerts(
    limit: int = Query(50, ge=1, le=200),
    alert_type: Optional[str] = Query(None),
):
    """Lista alertas recentes."""
    with get_session() as session:
        q = select(AlertLog).order_by(desc(AlertLog.created_at)).limit(limit)
        if alert_type:
            q = q.where(AlertLog.alert_type == alert_type)
        rows = session.execute(q).scalars().all()

        return {
            "alerts": [
                {
                    "id": r.id,
                    "alert_type": r.alert_type,
                    "campaign_id": r.campaign_id,
                    "message": r.message,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]
        }


@router.get("/snapshots")
def list_snapshots(
    campaign_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Histórico de snapshots para auditoria."""
    with get_session() as session:
        q = (
            select(CampaignSnapshot)
            .order_by(desc(CampaignSnapshot.ingested_at))
            .limit(limit)
        )
        if campaign_id:
            q = q.where(CampaignSnapshot.campaign_id == campaign_id)
        rows = session.execute(q).scalars().all()

        return {
            "snapshots": [
                {
                    "id": r.id,
                    "campaign_id": r.campaign_id,
                    "campaign_name": r.campaign_name,
                    "status": r.status,
                    "impressions": r.impressions,
                    "cost": r.cost,
                    "report_date": r.report_date,
                    "batch_id": r.batch_id,
                    "ingested_at": r.ingested_at.isoformat(),
                }
                for r in rows
            ]
        }


@router.get("/metrics")
def get_metrics(campaign_id: Optional[str] = Query(None)):
    """Métricas agregadas para gráficos — spend e impressions por batch."""
    with get_session() as session:
        q = (
            select(
                CampaignSnapshot.batch_id,
                CampaignSnapshot.ingested_at,
                CampaignSnapshot.report_date,
                func.sum(CampaignSnapshot.cost).label("total_cost"),
                func.sum(CampaignSnapshot.impressions).label("total_impressions"),
                func.count(distinct(CampaignSnapshot.campaign_id)).label("campaign_count"),
            )
            .group_by(
                CampaignSnapshot.batch_id,
                CampaignSnapshot.ingested_at,
                CampaignSnapshot.report_date,
            )
            .order_by(CampaignSnapshot.ingested_at)
            .limit(200)
        )
        if campaign_id:
            q = q.where(CampaignSnapshot.campaign_id == campaign_id)

        rows = session.execute(q).all()

        return {
            "metrics": [
                {
                    "batch_id": r.batch_id,
                    "ingested_at": r.ingested_at.isoformat(),
                    "report_date": r.report_date,
                    "total_cost": float(r.total_cost or 0),
                    "total_impressions": float(r.total_impressions or 0),
                    "campaign_count": r.campaign_count,
                }
                for r in rows
            ]
        }


@router.get("/summary")
def get_summary():
    """Resumo geral para cards do dashboard."""
    with get_session() as session:
        total_campaigns = session.execute(
            select(func.count(distinct(CampaignSnapshot.campaign_id)))
        ).scalar() or 0

        total_alerts_today = session.execute(
            select(func.count(AlertLog.id))
            .where(AlertLog.created_at >= datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ))
        ).scalar() or 0

        total_snapshots = session.execute(
            select(func.count(distinct(CampaignSnapshot.batch_id)))
        ).scalar() or 0

        last_update = session.execute(
            select(CampaignSnapshot.ingested_at)
            .order_by(desc(CampaignSnapshot.ingested_at))
            .limit(1)
        ).scalar_one_or_none()

        return {
            "total_campaigns": total_campaigns,
            "alerts_today": total_alerts_today,
            "total_snapshots": total_snapshots,
            "last_update": last_update.isoformat() if last_update else None,
        }


def _today_str() -> str:
    from datetime import date
    return date.today().isoformat()
