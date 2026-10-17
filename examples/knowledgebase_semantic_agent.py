"""Example demonstrating Phase 4: Knowledgebase, Semantic Layer & Vector Retrieval."""

from agentic_kb import (
    AgenticKnowledgeBase,
    BusinessTerm,
    KnowledgeBase,
    MockDatabaseProvider,
    MockLLMProvider,
)


def main():
    print("=== Initializing Knowledgebase & Semantic Layer ===")

    # Database with SaaS subscription data
    db = MockDatabaseProvider(
        database_name="saas_analytics",
        initial_tables={
            "subscriptions": [
                {"sub_id": "SUB-1", "user_id": "U100", "monthly_amount": 199.0, "status": "active"},
                {"sub_id": "SUB-2", "user_id": "U101", "monthly_amount": 499.0, "status": "active"},
                {"sub_id": "SUB-3", "user_id": "U102", "monthly_amount": 99.0, "status": "cancelled"},
            ],
            "support_tickets": [
                {"ticket_id": "T-1", "user_id": "U100", "issue": "Billing question", "status": "closed"},
            ],
        },
        table_descriptions={
            "subscriptions": "Recurring software subscriptions, pricing tiers, and active status",
            "support_tickets": "Customer care support tickets and resolution logs",
        },
    )

    # Business term definitions mapping business metrics to exact database expressions
    business_terms = [
        BusinessTerm(
            term="MRR",
            definition="Monthly Recurring Revenue from all currently active customer subscriptions",
            table="subscriptions",
            column="monthly_amount",
            filter="status = 'active'",
            synonyms=["monthly revenue", "recurring revenue"],
        ),
        BusinessTerm(
            term="churned subscription",
            definition="Subscriptions that have been cancelled by the user",
            table="subscriptions",
            filter="status = 'cancelled'",
            synonyms=["cancellations", "churn"],
        ),
    ]

    # Initialize KnowledgeBase
    kb = KnowledgeBase()

    # Create agent with semantic knowledgebase
    agent = AgenticKnowledgeBase(
        llm=MockLLMProvider(
            responses=[
                # 1. Intent decision
                '{"requires_database": true, "reasoning": "User asks for MRR", "relevant_tables": ["subscriptions"]}',
                # 2. SQL generation using semantic business term mapping
                '{"sql": "SELECT SUM(monthly_amount) AS total_mrr FROM subscriptions WHERE status = \'active\'", "explanation": "Calculates MRR adhering to business term definition"}',
                # 3. Final response synthesis
                "Current Monthly Recurring Revenue (MRR) is $698.00 from active subscriptions.",
            ]
        ),
        db=db,
        kb=kb,
        database={
            "type": "sqlite",
            "database": "saas_analytics",
            "host": "localhost",
            "username": "ai_user",
        },
        knowledgebase={
            "allowed_tables": ["subscriptions", "support_tickets"],
            "business_rules": [
                "Only subscriptions with status 'active' count towards recurring revenue metrics.",
            ],
        },
        response={
            "show_sql": True,
        },
    )

    # 1. Index schema metadata and business terms into semantic vector index
    schema_indexed = agent.index_schema_metadata()
    terms_indexed = agent.index_business_terms(business_terms)
    print(f"Indexed into KnowledgeBase: {schema_indexed} tables, {terms_indexed} business terms.")

    # 2. Test semantic retrieval directly
    query = "What is our current MRR?"
    print(f"\nQuerying KnowledgeBase for: '{query}'")
    retrieval = agent.kb.retrieve(query)
    print(f"Discovered Relevant Tables: {retrieval.relevant_tables}")
    print(f"Discovered Relevant Business Terms: {retrieval.relevant_terms}")
    print("\nRetrieved Semantic Context:")
    print("--------------------------------------------------")
    print(retrieval.formatted_prompt_context)
    print("--------------------------------------------------")

    # 3. Ask question via agent (leverages semantic retrieval for SQL generation)
    print("\nAsking agent:")
    res = agent.ask(query)
    print(f"Answer: {res.answer}")
    print(f"Executed SQL: {res.metadata.sql}")
    print(f"Steps: {res.metadata.steps}")

    agent.close()


if __name__ == "__main__":
    main()
