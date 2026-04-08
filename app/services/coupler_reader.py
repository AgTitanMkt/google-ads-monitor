"""Lê os dados mais recentes vindos do Coupler (Postgres ou Google Sheets)."""

from __future__ import annotations

import logging
from typing import List, Dict, Any

from app.config import get_settings

logger = logging.getLogger(__name__)


# ---------- INTERFACE ---------------------------------------------------------

def read_latest_campaigns() -> List[Dict[str, Any]]:
    """Retorna lista de dicts com os dados de campanhas mais recentes."""
    settings = get_settings()
    if settings.data_source == "sheets":
        return _read_from_sheets()
    return _read_from_postgres()


# ---------- POSTGRES ----------------------------------------------------------

def _read_from_postgres() -> List[Dict[str, Any]]:
    """Lê a tabela que o Coupler popula diretamente no Postgres.

    O Coupler cria/atualiza uma tabela (ex: `google_ads_data`) a cada execução.
    Aqui lemos todas as linhas atuais dessa tabela.
    """
    from sqlalchemy import text
    from app.database.connection import get_engine

    engine = get_engine()
    query = text("""
        SELECT campaign_id, campaign_name, impressions, cost, status,
               segments_date AS report_date
        FROM google_ads_data
        ORDER BY campaign_id, segments_date
    """)
    with engine.connect() as conn:
        rows = conn.execute(query).mappings().all()

    return [dict(r) for r in rows]


# ---------- GOOGLE SHEETS -----------------------------------------------------

def _read_from_sheets() -> List[Dict[str, Any]]:
    import gspread
    from google.oauth2.service_account import Credentials

    settings = get_settings()
    creds = Credentials.from_service_account_file(
        settings.google_sheets_credentials_file,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(settings.google_sheets_spreadsheet_id)
    ws = sheet.worksheet(settings.google_sheets_worksheet_name)

    records = ws.get_all_records()
    # Normaliza nomes de colunas (Coupler pode usar headers variados)
    normalized = []
    for r in records:
        normalized.append({
            "campaign_id": str(r.get("campaign_id", r.get("Campaign ID", ""))),
            "campaign_name": r.get("campaign_name", r.get("Campaign", "")),
            "impressions": float(r.get("impressions", r.get("Impressions", 0))),
            "cost": float(r.get("cost", r.get("Cost", 0))),
            "status": r.get("status", r.get("Status", "")),
            "report_date": str(r.get("segments_date", r.get("Date", ""))),
        })
    return normalized
