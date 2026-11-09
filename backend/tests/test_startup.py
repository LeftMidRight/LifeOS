import io
import logging

import pytest
from fastapi import FastAPI
from sqlalchemy.exc import OperationalError

import app.main as main_module
from app.config import Settings


class _FailingEngine:
    def connect(self):
        raise OperationalError("SELECT 1", {}, Exception("MySQL 未启动"))


async def test_lifespan_fails_fast_when_mysql_unavailable(monkeypatch):
    settings = Settings(
        _env_file=None,
        lifeos_database_url="mysql+aiomysql://lifeos:secret@127.0.0.1:3306/lifeos",
    )
    app = FastAPI()
    app.state.settings = settings
    monkeypatch.setattr(main_module, "engine", _FailingEngine())

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = main_module.logger
    # Alembic 的 fileConfig 会禁用已存在的 logger，这里临时恢复以便断言日志内容。
    was_disabled = logger.disabled
    logger.addHandler(handler)
    logger.disabled = False
    try:
        with pytest.raises(OperationalError):
            async with main_module.lifespan(app):
                pass
    finally:
        logger.removeHandler(handler)
        logger.disabled = was_disabled

    logged = stream.getvalue()
    assert "MySQL 数据库连接失败" in logged
    assert "mysql+aiomysql://lifeos:***@127.0.0.1:3306/lifeos" in logged
    assert "secret" not in logged
