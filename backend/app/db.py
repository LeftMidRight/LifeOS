from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_settings = get_settings()
engine = create_async_engine(
    _settings.lifeos_database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    # 事务由写路由在返回响应前显式 commit；这里只负责异常回滚。
    # 不在 yield 之后 commit：FastAPI 的 yield dependency teardown 发生在响应发出之后，
    # 客户端紧接着的 refresh/GET 可能读到旧数据（read-after-write 竞态）。
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
