from __future__ import annotations

from sqlalchemy.engine import make_url


def validate_test_database_url(test_url: str, production_url: str | None) -> str:
    """校验测试库配置，返回测试库名；不安全时抛出 RuntimeError。

    规则：
    1. 测试 URL 必须带数据库名，且以 ``_test`` 结尾；
    2. 测试库名不能与生产库名相同（防止误把生产库当测试库 TRUNCATE）。
    """
    test_database = make_url(test_url).database
    if not test_database:
        raise RuntimeError(
            "拒绝运行：LIFEOS_TEST_DATABASE_URL 未指定数据库名；测试必须使用独立的 *_test 数据库"
        )
    if not test_database.endswith("_test"):
        raise RuntimeError(
            f"拒绝运行：测试库名 {test_database!r} 必须以 _test 结尾；"
            "测试必须使用独立的测试库"
        )

    production_database = make_url(production_url).database if production_url else None
    if production_database and production_database == test_database:
        raise RuntimeError(
            f"拒绝运行：测试库与生产库同名（{test_database!r}），"
            "请把 LIFEOS_TEST_DATABASE_URL 指向独立的测试库"
        )
    return test_database
