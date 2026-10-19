"""Versioned system prompt templates for SQL agent orchestration."""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator

# Prompt version identifiers for tracing and production debugging
INTENT_DETECTION_PROMPT_VERSION = "1.0"
SQL_GENERATION_PROMPT_VERSION = "1.0"
RESPONSE_SYNTHESIS_PROMPT_VERSION = "1.0"


class IntentDecision(BaseModel):
    """Structured decision on whether query requires database execution."""
    requires_database: bool = Field(..., description="Whether the question asks for data stored in the database")
    reasoning: str = Field(..., description="Brief reasoning for the decision")
    relevant_tables: List[str] = Field(default_factory=list, description="List of tables likely needed to answer the query")


class GeneratedSQLPlan(BaseModel):
    """Structured query generation output (SQL text, or a JSON query object for MongoDB)."""
    sql: Union[str, Dict[str, Any]] = Field(
        ..., description="The executable read-only query: a SELECT statement, or for MongoDB a JSON object"
    )
    explanation: Optional[str] = Field(default=None, description="Explanation of query logic")
    tables_used: List[str] = Field(default_factory=list, description="Tables used in query")

    @field_validator("sql")
    @classmethod
    def _serialize_query_object(cls, v: Union[str, Dict[str, Any]]) -> str:
        """MongoDB queries arrive as objects; the rest of the pipeline works with their JSON text."""
        if isinstance(v, dict):
            from agentic_kb.security.mongo_validator import dump_query

            return dump_query(v)
        return v


def get_intent_detection_prompt(available_tables: List[str]) -> str:
    """System prompt to classify user question intent."""
    tables_list = ", ".join(available_tables) if available_tables else "None"
    return f"""You are a query intent analyzer for an enterprise database assistant.
Your task is to determine whether the user's question requires querying the database.

Available database tables:
{tables_list}

Rules:
1. If the user is asking for specific business facts, numbers, metrics, customers, orders, or records, set requires_database=true.
2. If the user is asking a general greeting, conversational question, or general knowledge question not related to the database, set requires_database=false.
3. Identify which of the available tables are relevant to answering the question.
"""


DIALECT_NOTES = {
    "postgresql": (
        "Quote identifiers with double quotes when they contain upper-case letters. "
        "Use LIMIT n for row limits and ILIKE for case-insensitive matching."
    ),
    "mysql": (
        "Quote identifiers with backticks (`name`). Use LIMIT n for row limits. "
        "String comparison is case-insensitive by default. Do not use ILIKE or double-quoted identifiers."
    ),
    "sqlserver": (
        "This is T-SQL (Microsoft SQL Server). Use SELECT TOP n instead of LIMIT, "
        "square brackets for identifiers ([name]), GETDATE() for the current time, and no ILIKE. "
        "Use OFFSET ... FETCH only together with ORDER BY."
    ),
}


def get_mongo_generation_prompt(schema_context: str, business_rules: Optional[List[str]] = None, max_rows: int = 1000) -> str:
    """System prompt for safe MongoDB aggregation-pipeline generation."""
    rules_text = "\n".join(f"- {r}" for r in (business_rules or []))
    return f"""You are an expert MongoDB engineer. Generate ONE read-only aggregation query that answers the user's question.

Collections and fields (nested fields use dotted paths, e.g. address.city; types were inferred from sampled documents):
{schema_context}

Business Rules & Constraints:
{rules_text or "- Strictly adhere to read-only queries."}

Output format - return the query as a JSON OBJECT (not a string) in the "sql" field:
{{"collection": "<collection name>", "pipeline": [ {{"$match": {{...}}}}, {{"$group": {{...}}}} ]}}

Rules:
- Use only these stages: $match, $project, $group, $sort, $limit, $skip, $unwind, $lookup, $addFields, $set, $unset, $count, $facet, $bucket, $bucketAuto, $sample, $replaceRoot, $replaceWith, $sortByCount.
- NEVER use $out, $merge, $function, $accumulator, $where, $unionWith or $graphLookup.
- Only use collections and fields listed above. Reference fields in expressions as "$field.path".
- Arrays of sub-documents (types like array<object>) must be $unwind-ed before grouping on their fields.
- Dates and ids use Extended JSON: {{"$date": "2024-01-31T00:00:00Z"}}, {{"$oid": "<24 hex chars>"}}.
- Counting: use {{"$count": "total"}} or $group with {{"$sum": 1}}.
- Cap results to at most {max_rows} documents (add a $limit stage).
"""


def get_sql_generation_prompt(
    dialect: str,
    schema_context: str,
    business_rules: Optional[List[str]] = None,
    max_rows: int = 1000,
) -> str:
    """System prompt for dialect-accurate, safe SQL generation."""
    if dialect.lower() == "mongodb":
        return get_mongo_generation_prompt(schema_context, business_rules, max_rows)
    dialect_note = DIALECT_NOTES.get(dialect.lower(), "")
    rules_text = "\n".join(f"- {r}" for r in (business_rules or []))
    if not rules_text:
        rules_text = "- Strictly adhere to read-only queries."

    return f"""You are an expert SQL engineer. Your task is to generate a single, accurate, and safe SQL query to answer the user's question.

Target Database Dialect: {dialect}

Database Schema:
{schema_context}

Business Rules & Constraints:
{rules_text}
- Return ONLY valid {dialect} SELECT statements.
{('- ' + dialect_note) if dialect_note else ''}
- NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or CREATE statements.
- Only query tables and columns defined in the schema above.
- Identifiers are case-sensitive. Copy table and column names EXACTLY as written in the schema, and wrap any name containing upper-case letters (e.g. camelCase like "carNo") in double quotes. Never lower-case them.
- Ensure proper JOIN conditions and WHERE filters.
- Default to limiting results to {max_rows} rows if applicable.
"""


def get_response_synthesis_prompt(
    user_question: str,
    query_result_summary: str,
    system_instructions: Optional[str] = None,
) -> str:
    """Prompt for synthesizing grounded natural language response from DB query result."""
    base_guideline = system_instructions or "Be professional, concise, and helpful."
    return f"""You are a database intelligence assistant.
{base_guideline}

User Question:
{user_question}

Database Query Results:
{query_result_summary}

Instructions:
1. Answer the user's question directly and concisely using ONLY the provided database query results.
2. If the query returned zero rows, inform the user clearly that no matching records were found.
3. Do not invent or hallucinate data that is not present in the results.
4. Format numbers, totals, and currency clearly for human reading.
"""
