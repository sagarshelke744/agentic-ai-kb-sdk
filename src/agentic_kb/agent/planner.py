"""SQL Agent Orchestration and Multi-Step Execution Planner."""

import json
import time
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from agentic_kb.agent.prompts import (
    GeneratedSQLPlan,
    IntentDecision,
    get_intent_detection_prompt,
    get_response_synthesis_prompt,
    get_sql_generation_prompt,
)
from agentic_kb.database.base import BaseDatabaseProvider
from agentic_kb.database.models import DatabaseSchemaMetadata, QueryResult
from agentic_kb.exceptions.errors import LLMRateLimitError, LLMTimeoutError, SQLValidationError
from agentic_kb.llm.base import BaseLLMProvider, LLMMessage
from agentic_kb.models.config import AgenticKBConfig
from agentic_kb.models.request import ChatRequest
from agentic_kb.models.response import AgentMetadata, ChatResponse
from agentic_kb.observability.events import emit
from agentic_kb.observability.logging import get_logger
from agentic_kb.security.identifiers import fix_identifier_case
from agentic_kb.security.permissions import PermissionEngine
from agentic_kb.security.sanitizer import DataMasker, InputSanitizer
from agentic_kb.security.sql_validator import SQLValidator

logger = get_logger("agentic_kb.agent.planner")


class SQLAgentPlanner:
    """
    Orchestrates the complete SQL Agent workflow:
    Input Sanitization -> Intent Detection -> Schema Selection -> SQL Generation ->
    SQL Validation -> RLS Injection -> Database Execution -> Grounded Response Synthesis.
    """

    def __init__(self, config: AgenticKBConfig):
        self.config = config

    def execute_plan(
        self,
        request: ChatRequest,
        schema_metadata: DatabaseSchemaMetadata,
        llm: BaseLLMProvider,
        db: BaseDatabaseProvider,
        validator: SQLValidator,
        permissions: PermissionEngine,
        kb: Optional[Any] = None,
    ) -> ChatResponse:
        start_time = time.time()
        request_id = str(uuid.uuid4())
        steps_taken: List[str] = []
        step_labels = {'input_sanitization': 'Validating question', 'intent_detection': 'Understanding your question', 'direct_response': 'Answering directly', 'schema_selection': 'Selecting relevant tables', 'sql_generation': 'Generating SQL query', 'sql_validation': 'Validating query safety', 'rls_enforcement': 'Applying access rules', 'database_execution': 'Running query on database', 'response_synthesis': 'Writing the answer'}

        def _step(name: str) -> None:
            steps_taken.append(name)
            emit("step", step=name, message=step_labels.get(name, name))

        # Step 1: Input Sanitization (Prompt injection defense)
        _step("input_sanitization")
        sanitized_question = InputSanitizer.validate_input(request.message)

        # Step 2: Intent Detection
        _step("intent_detection")
        available_tables = list(schema_metadata.tables.keys())
        intent_prompt = get_intent_detection_prompt(available_tables)

        try:
            intent_decision = llm.generate_structured(
                messages=[
                    LLMMessage.system(intent_prompt),
                    LLMMessage.user(sanitized_question),
                ],
                response_model=IntentDecision,
                temperature=0.0,
            )
        except (LLMRateLimitError, LLMTimeoutError):
            raise
        except Exception as e:
            logger.info(f"Structured intent fallback: {str(e)}. Defaulting to database lookup.")
            # Default to database search if available tables exist
            intent_decision = IntentDecision(
                requires_database=len(available_tables) > 0,
                reasoning="Default fallback intent",
                relevant_tables=available_tables,
            )

        # If database is not needed, generate direct response
        if not intent_decision.requires_database:
            _step("direct_response")
            direct_res = llm.generate([
                LLMMessage.system(
                    self.config.response.system_instructions
                    or f"You are {self.config.agent.name}, a helpful enterprise assistant."
                ),
                LLMMessage.user(sanitized_question),
            ])
            duration_ms = round((time.time() - start_time) * 1000, 2)
            return ChatResponse(
                answer=direct_res.content,
                request_id=request_id,
                conversation_id=request.conversation_id,
                metadata=AgentMetadata(
                    database_used=False,
                    execution_time_ms=duration_ms,
                    tokens_used=direct_res.token_usage.total_tokens,
                    steps=steps_taken,
                ),
            )

        # Step 3: Schema Selection and Knowledgebase Retrieval
        _step("schema_selection")
        selected_tables = intent_decision.relevant_tables or available_tables
        active_business_rules = list(self.config.knowledgebase.business_rules)

        # Enhance schema context with semantic retrieval from Knowledgebase
        if kb is not None:
            retrieval = kb.retrieve(sanitized_question, top_k=5)
            if retrieval.relevant_tables:
                # Merge semantic search tables
                merged = list(set(selected_tables + retrieval.relevant_tables))
                selected_tables = [t for t in merged if t in available_tables or any(a.endswith(f".{t}") for a in available_tables)]
            if retrieval.formatted_prompt_context:
                active_business_rules.append(f"Semantic Domain Context:\n{retrieval.formatted_prompt_context}")

        schema_context = schema_metadata.to_prompt_context(table_names=selected_tables)
        if not schema_context:
            schema_context = schema_metadata.to_prompt_context()

        # Step 4: SQL Generation
        _step("sql_generation")
        sql_gen_prompt = get_sql_generation_prompt(
            dialect=db.dialect_name,
            schema_context=schema_context,
            business_rules=active_business_rules,
            max_rows=self.config.security.max_rows,
        )

        try:
            sql_plan = llm.generate_structured(
                messages=[
                    LLMMessage.system(sql_gen_prompt),
                    LLMMessage.user(sanitized_question),
                ],
                response_model=GeneratedSQLPlan,
                temperature=0.0,
            )
            raw_sql = sql_plan.sql
        except (LLMRateLimitError, LLMTimeoutError):
            raise
        except Exception:
            # Fallback to text generation
            gen_result = llm.generate([
                LLMMessage.system(sql_gen_prompt),
                LLMMessage.user(f"Generate SQL for: {sanitized_question}\nReturn ONLY the SQL query."),
            ])
            raw_sql = gen_result.content.strip()
            # Clean markdown code blocks if returned
            if "```sql" in raw_sql:
                raw_sql = raw_sql.split("```sql")[1].split("```")[0].strip()
            elif "```" in raw_sql:
                raw_sql = raw_sql.split("```")[1].split("```")[0].strip()

        # Step 5: SQL AST Validation and Limit Enforcement
        _step("sql_validation")
        # Match identifiers to the schema's exact spelling (e.g. carNo -> "carNo" on PostgreSQL)
        raw_sql = fix_identifier_case(raw_sql, schema_metadata, db.dialect_name)
        cleaned_sql = validator.validate_or_raise(raw_sql)

        # Step 6: Row-Level Security Predicate Injection (if tenant/user specified)
        _step("rls_enforcement")
        final_sql = permissions.apply_row_level_security(
            cleaned_sql,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
        )

        # Step 7: Safe Database Execution
        _step("database_execution")
        from agentic_kb.observability.metrics import metrics_collector
        query_result = db.execute(
            final_sql,
            max_rows=self.config.security.max_rows,
            timeout_seconds=self.config.security.query_timeout_seconds,
        )
        metrics_collector.inc_counter("db_queries_total", labels={"dialect": db.dialect_name})
        metrics_collector.record_histogram("db_query_duration_seconds", (query_result.duration_ms or 0.0) / 1000.0)

        # Step 8: Sensitive Data Masking on Query Result
        masked_rows = [
            DataMasker.mask_record(row) if self.config.security.mask_pii else row
            for row in query_result.rows
        ]

        # Step 9: Grounded Response Synthesis
        _step("response_synthesis")
        result_summary = json.dumps(masked_rows[:20], indent=2, default=str)
        if query_result.is_truncated:
            result_summary += f"\n[Note: Total rows truncated at {len(query_result.rows)}]"

        synthesis_prompt = get_response_synthesis_prompt(
            user_question=sanitized_question,
            query_result_summary=result_summary,
            system_instructions=self.config.response.system_instructions,
        )

        synthesis_result = llm.generate([
            LLMMessage.system(synthesis_prompt),
            LLMMessage.user("Please provide the answer based on the database records."),
        ])

        duration_ms = round((time.time() - start_time) * 1000, 2)
        total_tokens = llm.total_token_usage.total_tokens

        # Expose SQL only if configured (Section 30 of PRD)
        exposed_sql = final_sql if self.config.response.show_sql else None

        meta = AgentMetadata(
            database_used=True,
            sql=exposed_sql,
            sources=list(validator.validate(final_sql).tables_used) if self.config.response.include_sources else [],
            execution_time_ms=duration_ms,
            row_count=query_result.row_count,
            tokens_used=total_tokens,
            steps=steps_taken,
        )

        return ChatResponse(
            answer=synthesis_result.content,
            request_id=request_id,
            conversation_id=request.conversation_id,
            metadata=meta,
        )
