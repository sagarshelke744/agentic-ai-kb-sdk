"""Azure OpenAI LLM Provider implementation."""

from typing import Any, Optional
from agentic_kb.exceptions.errors import ConfigurationError
from agentic_kb.llm.openai import OpenAIProvider


class AzureOpenAIProvider(OpenAIProvider):
    """Azure OpenAI service provider implementation."""

    def __init__(
        self,
        azure_endpoint: str,
        api_key: Optional[str] = None,
        api_version: str = "2024-02-15-preview",
        azure_deployment: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ):
        model_name = azure_deployment or model or "gpt-4o"
        super().__init__(api_key=api_key, model=model_name, **kwargs)
        self.azure_endpoint = azure_endpoint.rstrip("/")
        self.api_version = api_version
        self.azure_deployment = azure_deployment or model_name

    @property
    def provider_name(self) -> str:
        return "azure"

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import AzureOpenAI
            except ImportError:
                raise ConfigurationError(
                    "The 'openai' package is required for AzureOpenAIProvider. "
                    "Install it via `pip install openai` or `pip install agentic-kb[llm]`."
                )
            self._client = AzureOpenAI(
                azure_endpoint=self.azure_endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
                azure_deployment=self.azure_deployment,
                timeout=self.timeout_seconds,
            )
        return self._client

    def _get_async_client(self) -> Any:
        if self._async_client is None:
            try:
                from openai import AsyncAzureOpenAI
            except ImportError:
                raise ConfigurationError(
                    "The 'openai' package is required for AzureOpenAIProvider. "
                    "Install it via `pip install openai` or `pip install agentic-kb[llm]`."
                )
            self._async_client = AsyncAzureOpenAI(
                azure_endpoint=self.azure_endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
                azure_deployment=self.azure_deployment,
                timeout=self.timeout_seconds,
            )
        return self._async_client
