"""Response models for agentic-kb SDK."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentMetadata(BaseModel):
    """Metadata regarding how the answer was formed."""
    database_used: bool = False
    sql: Optional[str] = None
    sources: List[str] = Field(default_factory=list)
    execution_time_ms: Optional[float] = None
    row_count: Optional[int] = None
    tokens_used: Optional[int] = None
    steps: List[str] = Field(default_factory=list)
    custom: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Standardized response from the Agentic KnowledgeBase."""
    answer: str = Field(..., description="Grounded natural language answer")
    request_id: str = Field(..., description="Unique ID for request tracking and tracing")
    conversation_id: Optional[str] = None
    metadata: AgentMetadata = Field(default_factory=AgentMetadata)


class StreamChunk(BaseModel):
    """Chunk sent over Server-Sent Events during streaming."""
    event: str = Field(..., description="Event type: 'step', 'token', 'error', 'done'")
    data: Dict[str, Any] = Field(default_factory=dict)
