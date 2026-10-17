"""Request models for agentic-kb SDK."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """User question or message request."""
    message: str = Field(..., min_length=1, description="User's natural language question")
    conversation_id: Optional[str] = Field(default=None, description="Optional conversation/session ID")
    user_id: Optional[str] = Field(default=None, description="Optional user identifier for auditing/RLS")
    tenant_id: Optional[str] = Field(default=None, description="Optional tenant identifier for multi-tenancy")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional client context")
