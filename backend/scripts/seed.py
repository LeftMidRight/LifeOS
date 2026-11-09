from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ITEMS: list[tuple[int, int, int, str]] = [
    (0, 8, 20, "早上跑了 3 公里，风有点凉，但跑完脑子很清醒"),
    (0, 9, 5, "记得今天下午把方案发出去"),
    (0, 12, 30, "午饭 28 元 食堂"),
    (0, 14, 10, "突然想到一个点子，LifeOS 不该有四个模块，应该是一条流 #产品"),
    (0, 16, 45, "打车 32"),
    (0, 21, 15, "今天开了三个会，脑子有点糊。回来的路上一直在想那个架构问题，后来在地铁上突然想通了：其实不需要同步层，服务端就是唯一真相。"),
    (1, 9, 0, "todo: 预约牙医"),
    (1, 10, 30, "咖啡 22"),
    (1, 13, 0, "午饭 35 元 和同事"),
    (1, 19, 40, "买书 89 元《系统之美》，翻了前两章就停不下来"),
    (1, 22, 0, "感觉最近睡眠不太好，可能是因为睡前看手机太久"),
    (2, 8, 45, "地铁 6"),
    (2, 12, 15, "午饭 26 元 面馆"),
    (2, 20, 30, "晚饭 68 元 和同事聚餐 #社交"),
    (2, 23, 10, "在想要不要换掉现在这套技术栈，重写成本太高，但维护成本也高 #技术"),
    (3, 10, 20, "记得周五前把预算表整理好"),
    (3, 15, 45, "奶茶 18"),
    (3, 19, 0, "电影票 70，看了一半就困了"),
    (4, 11, 30, "交房租 4200"),
    (4, 18, 20, "这个月的电费 260，比上个月多了不少"),
    (5, 9, 40, "想到一个产品点子：把待办和日记合在一起，做完的事自动变成回顾 #产品 #灵感"),
    (5, 21, 0, "给爸妈打电话了吗？"),
]


async def main(force: bool) -> None:
    # 直接以文件路径运行（python scripts/seed.py）时，sys.path 只包含 scripts/，
    # 需要把 backend/ 加回来才能导入 app 包。
    if __package__ in (None, ""):
        backend_root = str(Path(__file__).resolve().parents[1])
        if backend_root not in sys.path:
            sys.path.insert(0, backend_root)

    from app.config import get_settings
    from app.models import Entry
    from app.repositories.entries import create_entry
    from app.schemas import EntryCreate
    from app.services.capture import parse_capture

    settings = get_settings()
    engine = create_async_engine(settings.lifeos_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            existing = await session.scalar(select(func.count()).select_from(Entry))
            if existing and not force:
                print(f"库里已有 {existing} 条记录，跳过。想强制追加请加 --force")
                return

            now = datetime.now().astimezone()
            created = 0
            for days_ago, hour, minute, text in ITEMS:
                at = (now - timedelta(days=days_ago)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                parsed = parse_capture(text, at)
                await create_entry(
                    session,
                    EntryCreate(
                        kind=parsed.kind,
                        content=parsed.content,
                        occurred_at=at,
                        amount=parsed.amount,
                        currency="CNY",
                        category=parsed.category,
                        status=parsed.status,
                        due_at=parsed.due_at,
                        tags=parsed.tags,
                        meta={"seeded": True, "captureNote": parsed.note},
                        source="import",
                    ),
                )
                created += 1

            await session.commit()
            print(f"已写入 {created} 条演示记录。")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.force))
