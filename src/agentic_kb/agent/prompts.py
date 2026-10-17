"""Versioned system prompt templates for SQL agent orchestration."""

from typing import List, Optional
from pydantic import BaseModel, Field

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
    """Structured SQL generation output."""
    sql: str = Field(..., description="The executable SELECT SQL query")
    explanation: Optional[str] = Field(default=None, description="Explanation of query logic")
    tables_used: List[str] = Field(default_factory=list, description="Tables used in query")


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


def get_sql_generation_prompt(
    dialect: str,
    schema_context: str,
    business_rules: Optional[List[str]] = None,
    max_rows: int = 1000,
) -> str:
    """System prompt for dialect-accurate, safe SQL generation."""
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
- NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, or CREATE statements.
- Only query tables and columns defined in the schema above.
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
