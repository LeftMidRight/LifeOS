from alembic.config import Config

# URL 编码的密码：p@ss%w0rd
URL = "mysql+pymysql://lifeos:p%40ss%25w0rd@127.0.0.1:3306/lifeos_test?charset=utf8mb4"


def test_percent_encoded_url_round_trips_through_config():
    config = Config()
    config.set_main_option("sqlalchemy.url", URL.replace("%", "%%"))

    assert config.get_main_option("sqlalchemy.url") == URL


def test_escaped_url_is_visible_unescaped_in_section():
    config = Config()
    config.set_main_option("sqlalchemy.url", URL.replace("%", "%%"))

    assert config.get_section(config.config_ini_section)["sqlalchemy.url"] == URL
