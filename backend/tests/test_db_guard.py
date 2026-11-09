import pytest

from tests.db_guard import validate_test_database_url

PRODUCTION = "mysql+aiomysql://lifeos:p%40ss@127.0.0.1:3306/lifeos?charset=utf8mb4"
TEST = "mysql+aiomysql://lifeos:p%40ss@127.0.0.1:3306/lifeos_test?charset=utf8mb4"


def test_valid_lifeos_test_is_accepted():
    assert validate_test_database_url(TEST, PRODUCTION) == "lifeos_test"


def test_same_database_as_production_is_rejected():
    same = "mysql+aiomysql://lifeos:secret@127.0.0.1:3306/lifeos_test"
    with pytest.raises(RuntimeError, match="与生产库同名"):
        validate_test_database_url(same, same)


def test_database_without_test_suffix_is_rejected():
    with pytest.raises(RuntimeError, match="必须以 _test 结尾"):
        validate_test_database_url(PRODUCTION, "mysql+aiomysql://lifeos:secret@127.0.0.1:3306/other")


def test_missing_database_name_is_rejected():
    with pytest.raises(RuntimeError, match="未指定数据库名"):
        validate_test_database_url("mysql+aiomysql://lifeos:secret@127.0.0.1:3306", PRODUCTION)


def test_production_url_optional():
    assert validate_test_database_url(TEST, None) == "lifeos_test"
