"""Unit tests for Phase 4: Knowledgebase, semantic layer, vector store, and embeddings."""

import pytest
from agentic_kb.database.models import ColumnMetadata, DatabaseSchemaMetadata, TableMetadata
from agentic_kb.knowledgebase.embeddings import (
    EmbeddingProviderFactory,
    MockEmbeddingProvider,
)
from agentic_kb.knowledgebase.kb import KnowledgeBase
from agentic_kb.knowledgebase.metadata import (
    BusinessTerm,
    KnowledgeDocument,
    NormalizedMetadataStore,
)
from agentic_kb.knowledgebase.retriever import (
    InMemoryVectorStore,
    KnowledgeRetriever,
    cosine_similarity,
)


def test_mock_embedding_provider():
    provider = MockEmbeddingProvider(dimension=32)
    vec1 = provider.embed_text("orders revenue")
    vec2 = provider.embed_text("orders revenue")
    vec3 = provider.embed_text("completely different query")

    assert len(vec1) == 32
    assert vec1 == vec2  # Deterministic
    sim_same = cosine_similarity(vec1, vec2)
    assert pytest.approx(sim_same, 0.0001) == 1.0


def test_cosine_similarity():
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]

    assert pytest.approx(cosine_similarity(v1, v2)) == 1.0
    assert pytest.approx(cosine_similarity(v1, v3)) == 0.0


def test_in_memory_vector_store():
    store = InMemoryVectorStore()
    doc1 = KnowledgeDocument(
        title="Orders",
        content="Customer sales orders and transaction totals",
        doc_type="table",
        embedding=[1.0, 0.0, 0.0],
    )
    doc2 = KnowledgeDocument(
        title="Products",
        content="Product catalog and items",
        doc_type="table",
        embedding=[0.0, 1.0, 0.0],
    )
    store.add_documents([doc1, doc2])
    assert store.count() == 2

    # Search closest to doc1
    hits = store.search(query_embedding=[0.9, 0.1, 0.0], top_k=1)
    assert len(hits) == 1
    assert hits[0].document.title == "Orders"
    assert hits[0].score > 0.8


def test_metadata_normalization():
    table = TableMetadata(
        schema_name="sales",
        table_name="orders",
        full_name="sales.orders",
        columns=[
            ColumnMetadata(name="id", data_type="INTEGER", is_primary_key=True),
            ColumnMetadata(name="amount", data_type="NUMERIC(10,2)", description="Total order value"),
        ],
        description="Completed orders",
    )
    doc = NormalizedMetadataStore.normalize_table(table)
    assert doc.doc_type == "table"
    assert "sales.orders" in doc.content
    assert "Total order value" in doc.content


def test_business_term_normalization():
    term = BusinessTerm(
        term="revenue",
        definition="Total monetary value of completed sales orders",
        table="sales.orders",
        column="amount",
        filter="status = 'COMPLETED'",
        synonyms=["sales", "gross revenue", "turnover"],
    )
    doc = NormalizedMetadataStore.normalize_business_term(term)
    assert doc.doc_type == "business_term"
    assert "revenue" in doc.content
    assert "status = 'COMPLETED'" in doc.content


def test_knowledgebase_indexing_and_retrieval():
    kb = KnowledgeBase()
    schema = DatabaseSchemaMetadata(
        dialect="postgres",
        database_name="sales_db",
        tables={
            "sales.orders": TableMetadata(
                schema_name="sales",
                table_name="orders",
                full_name="sales.orders",
                columns=[
                    ColumnMetadata(name="id", data_type="INT", is_primary_key=True),
                    ColumnMetadata(name="amount", data_type="DECIMAL"),
                ],
                description="Orders and invoices",
            ),
            "hr.employees": TableMetadata(
                schema_name="hr",
                table_name="employees",
                full_name="hr.employees",
                columns=[ColumnMetadata(name="emp_id", data_type="INT")],
                description="Employee payroll and staffing",
            ),
        },
    )

    indexed = kb.index_schema(schema)
    assert indexed == 2

    kb.index_business_terms([
        BusinessTerm(
            term="net sales",
            definition="Gross amount minus discounts",
            table="sales.orders",
            column="amount",
        )
    ])

    # Query the knowledgebase
    res = kb.retrieve("What was our sales revenue?")
    assert len(res.search_results) > 0
    assert "sales.orders" in res.relevant_tables or "net sales" in res.relevant_terms
