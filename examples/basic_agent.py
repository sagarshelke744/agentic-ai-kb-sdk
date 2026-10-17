"""Basic example demonstrating AgenticKnowledgeBase usage."""

from agentic_kb import AgenticKnowledgeBase


def main():
    # Initialize from configuration file
    agent = AgenticKnowledgeBase.from_yaml("configs/example.yaml")

    # Inspect health & configuration
    health = agent.health_check()
    print("Agent Health:", health)

    # Ask a question
    question = "What were our total sales last month?"
    print(f"\nUser Question: {question}")

    response = agent.ask(question)
    print(f"Agent Answer: {response.answer}")
    print(f"Request ID: {response.request_id}")
    print(f"Metadata: {response.metadata.model_dump()}")


if __name__ == "__main__":
    main()
