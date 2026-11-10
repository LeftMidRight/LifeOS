from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import to_utc_naive, utcnow
from app.models import AiInsight
from app.schemas import Insight


async def save_insight(session: AsyncSession, insight: Insight) -> AiInsight:
    row = AiInsight(
        id=str(uuid4()),
        scope=insight.scope,
        period_start=to_utc_naive(insight.from_),
        period_end=to_utc_naive(insight.to),
        model=insight.model,
        payload=insight.model_dump(mode="json", by_alias=True),
        created_at=to_utc_naive(utcnow()),
    )
    session.add(row)
    await session.flush()
    return row


async def insight_in_range(
    session: AsyncSession, scope: str, from_: datetime, to: datetime
) -> AiInsight | None:
    """返回指定 scope 与完整时间范围匹配的最近一条回顾快照。"""
    result = await session.execute(
        select(AiInsight)
        .where(
            AiInsight.scope == scope,
            AiInsight.period_start == to_utc_naive(from_),
            AiInsight.period_end == to_utc_naive(to),
        )
        .order_by(AiInsight.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def latest_insight(session: AsyncSession, scope: str) -> dict | None:
    result = await session.execute(
        select(AiInsight)
        .where(AiInsight.scope == scope)
        .order_by(AiInsight.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return row.payload if row is not None else None
