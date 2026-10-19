"""Multi-database support: config, factory, SQL dialect handling, RLS, shared SQLAlchemy base."""

import pytest
import sqlalchemy as sa

from agentic_kb.database.factory import DatabaseProviderFactory
from agentic_kb.database.models import ColumnMetadata, DatabaseSchemaMetadata, TableMetadata
from agentic_kb.database.sqlalchemy_base import SQLAlchemyProvider
from agentic_kb.exceptions.errors import ConfigurationError, PermissionDeniedError, SecurityError
from agentic_kb.models.config import DatabaseConfig
from agentic_kb.security.identifiers import fix_identifier_case
from agentic_kb.security.permissions import PermissionEngine
from agentic_kb.security.sql_validator import SQLValidator


# ------------------------------------------------------------------ config
@pytest.mark.parametrize(
    "db_type,canonical,port",
    [
        ("postgres", "postgresql", 5432),
        ("PostgreSQL", "postgresql", 5432),
        ("mysql", "mysql", 3306),
        ("mariadb", "mysql", 3306),
        ("mssql", "sqlserver", 1433),
        ("sqlserver", "sqlserver", 1433),
        ("mongo", "mongodb", 27017),
        ("mongodb", "mongodb", 27017),
    ],
)
def test_type_aliases_and_default_ports(db_type, canonical, port):
    cfg = DatabaseConfig(type=db_type, database="d", username="u")
    assert cfg.type == canonical and cfg.port == port


def test_explicit_port_wins():
    assert DatabaseConfig(type="mysql", database="d", username="u", port=3307).port == 3307


@pytest.mark.parametrize(
    "db_type,prefix",
    [("postgresql", "postgresql+psycopg2://"), ("mysql", "mysql+pymysql://"), ("sqlserver", "mssql+pymssql://")],
)
def test_connection_url_escapes_special_characters(db_type, prefix):
    cfg = DatabaseConfig(type=db_type, database="d", username="us@er", password="p@ss:w/rd#1")
    url = cfg.get_connection_url()
    assert url.startswith(prefix)
    parsed = sa.engine.make_url(url)
    assert parsed.username == "us@er" and parsed.password == "p@ss:w/rd#1" and parsed.database == "d"


def test_mysql_options_become_url_query():
    cfg = DatabaseConfig(type="mysql", database="d", username="u", password="p", options={"charset": "utf8mb4"})
    assert cfg.get_connection_url().endswith("?charset=utf8mb4")


def test_mongodb_uri_and_auth_source():
    cfg = DatabaseConfig(type="mongodb", database="shop", username="u@x", password="p w")
    assert cfg.get_connection_url() == "mongodb://u%40x:p+w@localhost:27017/?authSource=shop"
    anon = DatabaseConfig(type="mongodb", database="shop")
    assert anon.get_connection_url() == "mongodb://localhost:27017"


def test_url_env_overrides_everything(monkeypatch):
    monkeypatch.setenv("MY_DB_URL", "mysql+pymysql://x:y@h:1/z")
    cfg = DatabaseConfig(type="mysql", database="d", username="u", url_env="MY_DB_URL")
    assert cfg.get_connection_url() == "mysql+pymysql://x:y@h:1/z"


# ------------------------------------------------------------------ factory
def test_builtin_types_are_listed():
    names = DatabaseProviderFactory.get_registered_providers()
    for n in ("postgresql", "mysql", "sqlserver", "mongodb", "sqlite"):
        assert n in names


@pytest.mark.parametrize(
    "db_type,class_name",
    [
        ("postgresql", "PostgreSQLProvider"),
        ("mysql", "MySQLProvider"),
        ("mssql", "SQLServerProvider"),
        ("mongo", "MongoDBProvider"),
    ],
)
def test_factory_builds_each_provider_lazily(db_type, class_name):
    db = DatabaseProviderFactory.create({"type": db_type, "database": "d", "username": "u", "password": "p"})
    assert type(db).__name__ == class_name


def test_dialect_names():
    kinds = {
        t: DatabaseProviderFactory.create({"type": t, "database": "d", "username": "u"}).dialect_name
        for t in ("postgresql", "mysql", "sqlserver", "mongodb")
    }
    assert kinds == {"postgresql": "postgresql", "mysql": "mysql", "sqlserver": "sqlserver", "mongodb": "mongodb"}


# ------------------------------------------------------------------ driver session settings
class _FakeCursor:
    def __init__(self, fail_on=None):
        self.statements, self.fail_on = [], fail_on or []

    def execute(self, sql):
        if any(f in sql for f in self.fail_on):
            raise RuntimeError("unsupported")
        self.statements.append(sql)

    def close(self):
        pass


class _FakeConn:
    def __init__(self, cursor):
        self._c = cursor

    def cursor(self):
        return self._c


def test_mysql_sets_read_only_session_and_time_limit():
    db = DatabaseProviderFactory.create({"type": "mysql", "database": "d", "username": "u"}, query_timeout_seconds=12)
    cur = _FakeCursor()
    db._on_connect(_FakeConn(cur))
    assert cur.statements[0] == "SET SESSION TRANSACTION READ ONLY"
    assert "SET SESSION MAX_EXECUTION_TIME=12000" in cur.statements


def test_mysql_falls_back_to_mariadb_time_limit():
    db = DatabaseProviderFactory.create({"type": "mysql", "database": "d", "username": "u"}, query_timeout_seconds=3)
    cur = _FakeCursor(fail_on=["MAX_EXECUTION_TIME"])
    db._on_connect(_FakeConn(cur))
    assert any("max_statement_time" in s for s in cur.statements)


def test_mysql_reflects_only_configured_database_by_default():
    db = DatabaseProviderFactory.create({"type": "mysql", "database": "shop", "username": "u"})
    assert db._default_schemas() == ["shop"]


def test_postgres_connect_args_enforce_read_only_and_timeout():
    db = DatabaseProviderFactory.create(
        {"type": "postgresql", "database": "d", "username": "u"}, query_timeout_seconds=7
    )
    opts = db._connect_args()["options"]
    assert "statement_timeout=7000" in opts and "default_transaction_read_only=on" in opts


def test_sqlserver_connect_args():
    db = DatabaseProviderFactory.create(
        {"type": "sqlserver", "database": "d", "username": "u"}, query_timeout_seconds=9
    )
    assert db._connect_args()["timeout"] == 9


def test_missing_driver_gives_install_hint(monkeypatch):
    import importlib

    real = importlib.import_module

    def fake(name, *a, **k):
        if name == "agentic_kb.database.mysql":
            raise ImportError("No module named 'pymysql'", name="pymysql")
        return real(name, *a, **k)

    monkeypatch.setattr(importlib, "import_module", fake)
    with pytest.raises(ConfigurationError, match=r"agentic-kb\[mysql\]"):
        DatabaseProviderFactory.create({"type": "mysql", "database": "d", "username": "u"})


# ------------------------------------------------------------------ shared SQLAlchemy base (real engine via SQLite)
class _SqliteProvider(SQLAlchemyProvider):
    LABEL = "SQLite"

    @property
    def dialect_name(self):
        return "sqlite"


@pytest.fixture
def sqlite_db(tmp_path):
    url = f"sqlite:///{tmp_path / 't.db'}"
    eng = sa.create_engine(url)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        c.exec_driver_sql(
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), note TEXT)"
        )
        c.exec_driver_sql("INSERT INTO users VALUES (1,'Ann'),(2,'Bob')")
        c.exec_driver_sql("INSERT INTO orders VALUES (1,1,'a%b'),(2,2,'10:30')")
    eng.dispose()
    db = _SqliteProvider(connection_url=url, query_timeout_seconds=5)
    yield db
    db.close()


def test_base_executes_and_limits(sqlite_db):
    res = sqlite_db.execute("SELECT * FROM users ORDER BY id", max_rows=1)
    assert res.row_count == 1 and res.is_truncated and res.columns == ["id", "name"]


def test_literals_with_colon_and_percent_are_not_misparsed(sqlite_db):
    rows = sqlite_db.execute("SELECT note FROM orders WHERE note LIKE '%:30' OR note LIKE 'a%b'").rows
    assert sorted(r["note"] for r in rows) == ["10:30", "a%b"]


def test_bind_params_still_supported(sqlite_db):
    assert sqlite_db.execute("SELECT name FROM users WHERE id = :i", params={"i": 2}).rows == [{"name": "Bob"}]


@pytest.mark.parametrize(
    "sql", ["DELETE FROM users", "update users set name='x'", "DROP TABLE users", "EXEC sp_x", "SET x=1"]
)
def test_read_only_blocks_writes(sqlite_db, sql):
    with pytest.raises(SecurityError):
        sqlite_db.execute(sql)


def test_base_reflects_tables_columns_and_foreign_keys(sqlite_db):
    meta = sqlite_db.get_schema_metadata(allowed_tables=["ORDERS"])  # case-insensitive allow-list
    assert list(meta.tables) == ["main.orders"]
    col = next(c for c in meta.tables["main.orders"].columns if c.name == "user_id")
    assert col.is_foreign_key and col.foreign_table == "main.users"


def test_health_check(sqlite_db):
    assert sqlite_db.health_check()["status"] == "healthy"


# ------------------------------------------------------------------ SQL validator per dialect
def test_validator_enforces_limit_per_dialect():
    assert "LIMIT 50" in SQLValidator(max_rows=50, dialect="mysql").validate("SELECT * FROM t").cleaned_sql
    assert "TOP 50" in SQLValidator(max_rows=50, dialect="sqlserver").validate("SELECT * FROM t").cleaned_sql
    assert "LIMIT 50" in SQLValidator(max_rows=50, dialect="postgresql").validate("SELECT * FROM t").cleaned_sql


def test_validator_accepts_native_syntax():
    assert SQLValidator(dialect="mysql").validate("SELECT `a` FROM `t` LIMIT 5").is_valid
    assert SQLValidator(dialect="sqlserver").validate("SELECT TOP 5 [a] FROM [dbo].[t]").is_valid


@pytest.mark.parametrize("dialect", ["postgresql", "mysql", "sqlserver"])
def test_validator_blocks_writes_per_dialect(dialect):
    assert not SQLValidator(dialect=dialect).validate("DELETE FROM t").is_valid


# ------------------------------------------------------------------ RLS (regression: used to be skipped silently)
@pytest.mark.parametrize("dialect", ["postgresql", "postgres", "mysql", "sqlserver", "mssql"])
def test_rls_is_applied_for_every_dialect_name(dialect):
    out = PermissionEngine(dialect=dialect).apply_row_level_security("SELECT * FROM orders", tenant_id="acme")
    assert "tenant_id = 'acme'" in out


def test_rls_escapes_quotes_in_ids():
    out = PermissionEngine(dialect="postgresql").apply_row_level_security(
        "SELECT * FROM orders", tenant_id="x' OR '1'='1"
    )
    assert "tenant_id = 'x'' OR ''1''=''1'" in out


def test_rls_fails_closed_on_unparseable_sql():
    with pytest.raises(PermissionDeniedError):
        PermissionEngine(dialect="postgresql").apply_row_level_security("SELEC ((", tenant_id="acme")


def test_rls_noop_without_ids():
    assert PermissionEngine(dialect="postgresql").apply_row_level_security("SELECT 1") == "SELECT 1"


# ------------------------------------------------------------------ identifier fixes per dialect
def _schema():
    def col(n):
        return ColumnMetadata(name=n, data_type="text")

    return DatabaseSchemaMetadata(
        dialect="x",
        database_name="d",
        tables={
            "dbo.user": TableMetadata(table_name="user", full_name="dbo.user", columns=[col("id"), col("carNo")]),
        },
    )


def test_sqlserver_reserved_word_table_is_bracketed():
    assert "[user]" in fix_identifier_case("SELECT id FROM user", _schema(), "sqlserver")


def test_mysql_reserved_word_table_is_backticked():
    assert "`user`" in fix_identifier_case("SELECT id FROM user", _schema(), "mysql")
