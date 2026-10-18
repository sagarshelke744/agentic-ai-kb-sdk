"""Tests for case-sensitive identifier normalization on PostgreSQL."""

from agentic_kb.database.models import ColumnMetadata, DatabaseSchemaMetadata, TableMetadata
from agentic_kb.security.identifiers import fix_identifier_case


def _schema() -> DatabaseSchemaMetadata:
    def col(name):
        return ColumnMetadata(name=name, data_type="text")

    return DatabaseSchemaMetadata(
        dialect="postgresql",
        database_name="gadibidi",
        tables={
            "public.cars": TableMetadata(
                table_name="cars",
                full_name="public.cars",
                columns=[col(c) for c in ["id", "carNo", "rcNo", "model", "sellingPrice", "carLocation"]],
            ),
            "public.user": TableMetadata(
                table_name="user", full_name="public.user", columns=[col("id"), col("phoneNo")]
            ),
        },
    )


def test_unquoted_camel_case_columns_are_quoted():
    sql = fix_identifier_case(
        "SELECT id, carNo, rcNo, model, sellingPrice, carLocation FROM public.cars ORDER BY sellingPrice DESC",
        _schema(),
        "postgresql",
    )
    assert '"carNo"' in sql and '"rcNo"' in sql and '"sellingPrice"' in sql and '"carLocation"' in sql
    assert "ORDER BY \"sellingPrice\" DESC" in sql
    assert " model" in sql  # lower-case names stay unquoted


def test_wrongly_lowered_quoted_identifier_is_corrected():
    sql = fix_identifier_case('SELECT "carno" FROM cars', _schema(), "postgresql")
    assert '"carNo"' in sql


def test_reserved_word_table_is_quoted():
    sql = fix_identifier_case("SELECT id FROM user", _schema(), "postgresql")
    assert 'FROM "user"' in sql


def test_already_correct_sql_is_untouched():
    original = 'SELECT "carNo" FROM cars'
    assert fix_identifier_case(original, _schema(), "postgresql") == original


def test_non_case_folding_dialect_is_untouched():
    original = "SELECT carNo FROM cars"
    assert fix_identifier_case(original, _schema(), "sqlite") == original


def test_unparseable_sql_is_returned_unchanged():
    assert fix_identifier_case("SELEC ((", _schema(), "postgresql") == "SELEC (("
