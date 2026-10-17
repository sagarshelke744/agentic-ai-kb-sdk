"""Example demonstrating custom LLM injection (e.g., custom model, LangGraph, or local gateway)."""

from agentic_kb import (
    AgenticKnowledgeBase,
    CustomCallableProvider,
    LLMMessage,
    LLMProviderFactory,
    FallbackLLMProvider,
    MockLLMProvider,
)


def main():
    print("=== Pattern 1: Direct Callable Injection (LangChain/LangGraph/Custom function) ===")

    # Any developer can supply their own function or wrap a LangGraph app/chain:
    def my_enterprise_llm(messages, **kwargs):
        user_msg = next((m.content for m in reversed(messages) if m.role == "user"), "")
        # Here a developer can call LangGraph, Ollama, HuggingFace, or internal proxy
        return f"[Enterprise Model]: Processing question '{user_msg}'"

    custom_provider = CustomCallableProvider(
        generate_fn=my_enterprise_llm,
        model="enterprise-llm-v1",
        provider_name_override="my_company_gateway",
    )

    agent1 = AgenticKnowledgeBase(
        llm=custom_provider,
        database={
            "type": "postgresql",
            "host": "localhost",
            "database": "sales_db",
            "username": "ai_agent_user",
        },
        knowledgebase={
            "allowed_tables": ["sales.orders", "sales.products"],
        },
    )

    response1 = agent1.ask("What was total revenue in Q3?")
    print("Answer 1:", response1.answer)
    print("Health 1:", agent1.health_check())

    print("\n=== Pattern 2: Multi-Provider Fallback Resilience ===")
    # Primary provider with automatic failover to backup
    primary = MockLLMProvider(default_response="Response from primary LLM")
    backup = MockLLMProvider(default_response="Response from fallback backup LLM")
    resilient_llm = FallbackLLMProvider(primary=primary, fallbacks=[backup])

    agent2 = AgenticKnowledgeBase(
        llm=resilient_llm,
        database={
            "type": "postgresql",
            "host": "localhost",
            "database": "sales_db",
            "username": "ai_agent_user",
        },
    )
    response2 = agent2.ask("How many active users?")
    print("Answer 2:", response2.answer)


if __name__ == "__main__":
    main()
