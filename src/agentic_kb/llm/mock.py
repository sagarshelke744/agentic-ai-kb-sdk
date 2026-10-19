"""Mock LLM Provider for offline testing, local development, and CI."""

import json
import time
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
)
from pydantic import BaseModel

from agentic_kb.exceptions.errors import LLMMalformedOutputError
from agentic_kb.llm.base import BaseLLMProvider, LLMMessage, LLMResult, TokenUsage

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider(BaseLLMProvider):
    """
    Mock LLM provider useful for zero-cost unit testing, offline testing,
    and simulated agentic workflows.
    """

    def __init__(
        self,
        model: str = "mock-model",
        default_response: str = "Mock generated response",
        structured_responses: Optional[Dict[str, BaseModel]] = None,
        responses: Optional[List[Union[str, Exception]]] = None,
        response_generator: Optional[Callable[[List[LLMMessage]], str]] = None,
        **kwargs: Any,
    ):
        super().__init__(model=model, **kwargs)
        self.default_response = default_response
        self.structured_responses = structured_responses or {}
        self.responses = list(responses) if responses else []
        self.response_generator = response_generator
        self.history: List[List[LLMMessage]] = []

    @property
    def provider_name(self) -> str:
        return "mock"

    def _get_next_response(self, messages: List[LLMMessage]) -> str:
        self.history.append(messages)
        if self.responses:
            item = self.responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        if self.response_generator:
            return self.response_generator(messages)
        return self.default_response

    def _generate_offline_sql(self, question: str) -> tuple[str, list[str]]:
        """Map common natural language questions into valid T-SQL for all allowed tables."""
        q = question.lower()

        # ── System / Schema queries ─────────────────────────────
        if "table name" in q or "tables name" in q or "tables in" in q or "what tables" in q:
            return "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo' AND TABLE_TYPE = 'BASE TABLE'", ["dbo.employee", "dbo.departments", "dbo.projects", "dbo.orders"]

        # ── Projects Table ──────────────────────────────────────
        if "project" in q:
            if "count" in q or "how many" in q:
                return "SELECT COUNT(*) AS total_projects FROM dbo.projects", ["dbo.projects"]
            if "in progress" in q or "ongoing" in q or "active" in q:
                return "SELECT project_id, project_name, dept_name, budget, status FROM dbo.projects WHERE status = 'In Progress'", ["dbo.projects"]
            if "completed" in q or "finished" in q:
                return "SELECT project_id, project_name, dept_name, budget, status FROM dbo.projects WHERE status = 'Completed'", ["dbo.projects"]
            if "budget" in q or "highest" in q or "expensive" in q:
                return "SELECT TOP 1 project_name, dept_name, budget, status FROM dbo.projects ORDER BY budget DESC", ["dbo.projects"]
            if "name" in q:
                return "SELECT project_id, project_name, dept_name, status FROM dbo.projects", ["dbo.projects"]
            return "SELECT project_id, project_name, dept_name, budget, status, start_date, end_date FROM dbo.projects", ["dbo.projects"]

        # ── Orders Table ────────────────────────────────────────
        if "order" in q or "sales" in q or "revenue" in q or "customer" in q:
            if "customer" in q:
                return "SELECT DISTINCT customer_name FROM dbo.orders", ["dbo.orders"]
            if "total" in q and ("revenue" in q or "sales" in q or "amount" in q):
                return "SELECT SUM(total_amount) AS total_revenue FROM dbo.orders", ["dbo.orders"]
            if "count" in q or "how many orders" in q:
                return "SELECT COUNT(*) AS total_orders FROM dbo.orders", ["dbo.orders"]
            if "highest" in q or "top" in q or "largest" in q:
                return "SELECT TOP 1 customer_name, total_amount, status, shipping_city, sales_rep FROM dbo.orders ORDER BY total_amount DESC", ["dbo.orders"]
            if "delivered" in q:
                return "SELECT order_id, customer_name, total_amount, shipping_city FROM dbo.orders WHERE status = 'Delivered'", ["dbo.orders"]
            if "mumbai" in q:
                return "SELECT order_id, customer_name, total_amount, status FROM dbo.orders WHERE LOWER(shipping_city) = 'mumbai'", ["dbo.orders"]
            if "rep" in q or "by sales" in q:
                return "SELECT sales_rep, COUNT(*) AS orders_count, SUM(total_amount) AS total_sales FROM dbo.orders GROUP BY sales_rep", ["dbo.orders"]
            return "SELECT order_id, customer_name, order_date, total_amount, status, shipping_city, sales_rep FROM dbo.orders", ["dbo.orders"]

        # ── Departments Table ───────────────────────────────────
        if "department" in q or "dept" in q:
            if "manager" in q or "head" in q or "leads" in q:
                return "SELECT dept_name, manager_name, location FROM dbo.departments", ["dbo.departments"]
            if "budget" in q:
                if "highest" in q or "top" in q or "max" in q:
                    return "SELECT TOP 1 dept_name, budget, manager_name FROM dbo.departments ORDER BY budget DESC", ["dbo.departments"]
                return "SELECT dept_name, budget FROM dbo.departments ORDER BY budget DESC", ["dbo.departments"]
            if "headcount" in q or "people" in q:
                return "SELECT dept_name, headcount, location FROM dbo.departments ORDER BY headcount DESC", ["dbo.departments"]
            if "location" in q or "pune" in q or "mumbai" in q or "bangalore" in q:
                return "SELECT dept_name, manager_name, location FROM dbo.departments", ["dbo.departments"]
            if "employee" not in q and ("all" in q or "list" in q or "names" in q):
                return "SELECT dept_name, manager_name, budget, location, headcount FROM dbo.departments", ["dbo.departments"]

        # ── Employee Table ──────────────────────────────────────
        if "salary" in q:
            if "highest" in q or "maximum" in q or "max" in q or "most" in q:
                return "SELECT TOP 1 emp_id, emp_name, dept, salary, post FROM dbo.employee ORDER BY salary DESC", ["dbo.employee"]
            if "lowest" in q or "minimum" in q or "min" in q or "least" in q:
                return "SELECT TOP 1 emp_id, emp_name, dept, salary, post FROM dbo.employee ORDER BY salary ASC", ["dbo.employee"]
            if "average" in q or "avg" in q:
                return "SELECT AVG(salary) AS average_salary FROM dbo.employee", ["dbo.employee"]

        if "2002" in q:
            return "SELECT emp_id, emp_name, dept, hire_date FROM dbo.employee WHERE hire_date < '2002-01-01'", ["dbo.employee"]
        if "hire" in q or "joined" in q:
            return "SELECT emp_id, emp_name, dept, hire_date, post FROM dbo.employee ORDER BY hire_date DESC", ["dbo.employee"]

        if "hr" in q:
            return "SELECT emp_id, emp_name, dept, salary, location, post FROM dbo.employee WHERE LOWER(dept) = 'hr'", ["dbo.employee"]

        if "how many" in q or "count" in q or "number of employees" in q:
            return "SELECT COUNT(*) AS total_employees FROM dbo.employee", ["dbo.employee"]

        if "department names" in q or ("dept" in q and "employee" in q):
            return "SELECT DISTINCT dept FROM dbo.employee", ["dbo.employee"]

        # Default fallback: inspect employee records
        return "SELECT TOP 10 emp_id, emp_name, dept, salary, location, hire_date, post FROM dbo.employee", ["dbo.employee"]

    def _synthesize_offline_response(self, prompt_text: str) -> str:
        """Create a clear natural language answer from database records in prompt."""
        # Check if database results block is present
        if "Database Query Results:" not in prompt_text:
            return "Hello! I am your Sagar Database Assistant connected to SQL Server (dbo.employee). You can ask me questions like: 'Give me the department names from employee table' or 'Who earns the highest salary?'"

        try:
            results_section = prompt_text.split("Database Query Results:")[1]
            if "Instructions:" in results_section:
                results_section = results_section.split("Instructions:")[0]
            data_str = results_section.strip()
            if not data_str or data_str == "[]":
                return "The query ran successfully against your SQL Server database, but returned no matching records."

            records = json.loads(data_str)
            if not records:
                return "No records were found in the database matching your criteria."

            if isinstance(records, list):
                # Single count/aggregate result
                if len(records) == 1 and len(records[0]) == 1:
                    key, val = list(records[0].items())[0]
                    clean_key = key.replace("_", " ").title()
                    return f"Based on your database records, the **{clean_key}** is **{val}**."

                # Single row details (e.g. highest earner)
                if len(records) == 1:
                    rec = records[0]
                    lines = [f"- **{k.replace('_', ' ').title()}**: {v}" for k, v in rec.items()]
                    return "Here is the matching record from your database:\n\n" + "\n".join(lines)

                # Distinct lists (e.g. distinct departments or locations)
                if len(records[0]) == 1:
                    key = list(records[0].keys())[0]
                    clean_key = key.replace("_", " ").title()
                    items = [f"- {r[key]}" for r in records if r.get(key)]
                    return f"Here are the **{clean_key}s** found in your database ({len(items)} found):\n\n" + "\n".join(items)

                # Multi-column table
                headers = list(records[0].keys())
                header_line = "| " + " | ".join(h.replace('_', ' ').title() for h in headers) + " |"
                sep_line = "| " + " | ".join("---" for _ in headers) + " |"
                row_lines = [
                    "| " + " | ".join(str(r.get(h, "")) for h in headers) + " |"
                    for r in records[:15]
                ]
                return f"Here are the results from your SQL Server database ({len(records)} records found):\n\n" + header_line + "\n" + sep_line + "\n" + "\n".join(row_lines)

        except Exception:
            pass

        return "Query completed successfully on SQL Server and retrieved matching data."

    def generate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        start = time.time()
        combined_text = " ".join(m.content for m in messages)

        # Check if this is a response synthesis call
        if "Database Query Results:" in combined_text:
            content = self._synthesize_offline_response(combined_text)
        elif any(greeting in combined_text.lower() for greeting in ["hi", "hello", "hey", "help"]):
            content = "Hello! I am your Sagar Database Assistant connected to SQL Server (dbo.employee). You can ask me questions like: 'Give me the department names from employee table' or 'Who earns the highest salary?'"
        else:
            content = self._get_next_response(messages)

        prompt_chars = sum(len(m.content) for m in messages)
        usage = TokenUsage(
            prompt_tokens=max(1, prompt_chars // 4),
            completion_tokens=max(1, len(content) // 4),
            total_tokens=max(2, (prompt_chars + len(content)) // 4),
            estimated_cost_usd=0.0,
        )
        self.record_usage(usage)
        duration = (time.time() - start) * 1000
        return LLMResult(
            content=content,
            token_usage=usage,
            duration_ms=duration,
            model=self.model,
            provider=self.provider_name,
        )

    async def agenerate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        return self.generate(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)

    def generate_structured(
        self,
        messages: List[LLMMessage],
        response_model: Type[T],
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> T:
        model_name = response_model.__name__
        if model_name in self.structured_responses:
            instance = self.structured_responses[model_name]
            if isinstance(instance, response_model):
                return instance

        # Smart offline structured handling
        user_msg = ""
        for m in reversed(messages):
            if m.role == "user":
                user_msg = m.content
                break

        if model_name == "IntentDecision":
            lowered = user_msg.lower()
            is_greeting = lowered in ["hi", "hello", "hey", "good morning", "good evening", "who are you"]
            from agentic_kb.agent.prompts import IntentDecision
            tables = ["dbo.employee", "dbo.departments", "dbo.projects", "dbo.orders"]
            if "project" in lowered:
                tables = ["dbo.projects"]
            elif "order" in lowered or "sales" in lowered or "revenue" in lowered or "customer" in lowered:
                tables = ["dbo.orders"]
            elif "dept" in lowered or "department" in lowered:
                tables = ["dbo.departments", "dbo.employee"]
            decision = IntentDecision(
                requires_database=not is_greeting,
                reasoning="Offline intent detection based on user query",
                relevant_tables=tables if not is_greeting else [],
            )
            return decision  # type: ignore

        if model_name == "GeneratedSQLPlan":
            from agentic_kb.agent.prompts import GeneratedSQLPlan
            sql, tables_used = self._generate_offline_sql(user_msg)
            plan = GeneratedSQLPlan(
                sql=sql,
                explanation=f"Generated offline T-SQL query for: {user_msg}",
                tables_used=tables_used,
            )
            return plan  # type: ignore

        raw = self._get_next_response(messages)
        try:
            parsed = json.loads(raw)
            return response_model.model_validate(parsed)
        except Exception as e:
            raise LLMMalformedOutputError(
                f"Failed to parse mock structured output for {model_name}: {str(e)}",
                raw_output=raw,
            ) from e

    async def agenerate_structured(
        self,
        messages: List[LLMMessage],
        response_model: Type[T],
        temperature: Optional[float] = None,
        **kwargs: Any,
    ) -> T:
        return self.generate_structured(messages, response_model=response_model, **kwargs)

    def stream(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        res = self.generate(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)
        for word in res.content.split(" "):
            yield word + " "

    async def astream(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        res = self.generate(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)
        for word in res.content.split(" "):
            yield word + " "

