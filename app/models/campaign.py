from sqlalchemy import (
    Column, String, Float, Integer, DateTime, BigInteger, Index, text
)
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


class CampaignSnapshot(Base):
    """Snapshot imutável — cada importação do Coupler gera novos registros."""

    __tablename__ = "campaign_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id = Column(String, nullable=False, index=True)
    campaign_name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    impressions = Column(Float, default=0)
    cost = Column(Float, default=0)
    report_date = Column(String, nullable=False)  # "today" ou "yesterday"
    ingested_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    batch_id = Column(String, nullable=False, index=True)

    __table_args__ = (
        Index("ix_campaign_batch", "campaign_id", "batch_id"),
    )


class AlertLog(Base):
    """Registro de alertas enviados — garante idempotência."""

    __tablename__ = "alert_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    alert_key = Column(String, unique=True, nullable=False)
    alert_type = Column(String, nullable=False)
    campaign_id = Column(String, nullable=False)
    message = Column(String, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
