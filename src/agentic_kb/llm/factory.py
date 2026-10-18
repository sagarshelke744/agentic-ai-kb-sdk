"""LLM Provider Factory and Extensible Registry."""

import os

from typing import Any, Dict, List, Optional, Type, Union

from agentic_kb.exceptions.errors import ConfigurationError
from agentic_kb.llm.azure import AzureOpenAIProvider
from agentic_kb.llm.base import BaseLLMProvider
from agentic_kb.llm.custom import CustomCallableProvider, FallbackLLMProvider
from agentic_kb.llm.gemini import GeminiProvider
from agentic_kb.llm.groq import GroqProvider
from agentic_kb.llm.mock import MockLLMProvider
from agentic_kb.llm.openai import OpenAIProvider
from agentic_kb.models.config import LLMConfig


class LLMProviderFactory:
    """
    Registry and factory for LLM providers.

    Supports built-in providers (OpenAI, Azure, Gemini, Groq, Mock) and custom user-registered providers.
    """

    _registry: Dict[str, Type[BaseLLMProvider]] = {
        "openai": OpenAIProvider,
        "azure": AzureOpenAIProvider,
        "gemini": GeminiProvider,
        "groq": GroqProvider,
        "mock": MockLLMProvider,
        "custom": CustomCallableProvider,
    }

    @classmethod
    def register(cls, name: str, provider_cls: Type[BaseLLMProvider]) -> None:
        """
        Register a custom LLM provider with the factory.

        Example:
        ```python
        LLMProviderFactory.register("anthropic", AnthropicProvider)
        LLMProviderFactory.register("my_company_llm", EnterpriseLLMProvider)
        ```
        """
        if not issubclass(provider_cls, BaseLLMProvider):
            raise ConfigurationError(
                f"Provider class {provider_cls.__name__} must inherit from BaseLLMProvider"
            )
        cls._registry[name.lower()] = provider_cls

    @classmethod
    def get_registered_providers(cls) -> List[str]:
        """Return list of currently registered provider identifiers."""
        return list(cls._registry.keys())

    @classmethod
    def create(
        cls,
        config: Union[LLMConfig, BaseLLMProvider, Dict[str, Any]],
        **kwargs: Any,
    ) -> BaseLLMProvider:
        """
        Create or return an LLMProvider instance.

        Accepts:
        - An existing BaseLLMProvider instance (direct pass-through / dependency injection)
        - An LLMConfig model instance
        - A dictionary matching LLMConfig fields
        """
        # 1. Direct instance injection
        if isinstance(config, BaseLLMProvider):
            return config

        # 2. Parse config
        if isinstance(config, dict):
            llm_cfg = LLMConfig(**config)
        elif isinstance(config, LLMConfig):
            llm_cfg = config
        else:
            raise ConfigurationError(
                f"Expected LLMConfig, dict, or BaseLLMProvider, got {type(config).__name__}"
            )

        provider_key = llm_cfg.provider.lower()
        provider_cls = cls._registry.get(provider_key)

        if not provider_cls:
            available = ", ".join(cls._registry.keys())
            raise ConfigurationError(
                f"Unknown LLM provider '{llm_cfg.provider}'. Registered providers are: {available}. "
                f"You can register a custom provider via `LLMProviderFactory.register('{provider_key}', YourProviderClass)`."
            )

        # Build provider kwargs based on type
        api_key = llm_cfg.get_api_key()
        common_kwargs: Dict[str, Any] = {
            "model": llm_cfg.model,
            "temperature": llm_cfg.temperature,
            "max_tokens": llm_cfg.max_tokens,
            "timeout_seconds": llm_cfg.timeout_seconds,
            "max_retries": llm_cfg.max_retries,
            **kwargs,
        }

        if provider_cls is AzureOpenAIProvider:
            if not llm_cfg.azure_endpoint:
                raise ConfigurationError("azure_endpoint is required when provider='azure'")
            return AzureOpenAIProvider(
                azure_endpoint=llm_cfg.azure_endpoint,
                api_key=api_key,
                api_version=llm_cfg.api_version or "2024-02-15-preview",
                azure_deployment=llm_cfg.azure_deployment or llm_cfg.model,
                **common_kwargs,
            )

        if provider_cls is GroqProvider:
            # The config default api_key_env targets OpenAI; Groq has its own key variable
            if not llm_cfg.api_key and llm_cfg.api_key_env == "OPENAI_API_KEY":
                api_key = os.getenv("GROQ_API_KEY")
            return GroqProvider(
                api_key=api_key,
                base_url=llm_cfg.base_url,
                **common_kwargs,
            )

        if provider_cls is OpenAIProvider:
            return OpenAIProvider(
                api_key=api_key,
                base_url=llm_cfg.base_url,
                **common_kwargs,
            )

        if provider_cls is GeminiProvider:
            return GeminiProvider(
                api_key=api_key,
                **common_kwargs,
            )

        if provider_cls is MockLLMProvider:
            return MockLLMProvider(**common_kwargs)

        # For custom registered providers, pass api_key and common kwargs
        return provider_cls(api_key=api_key, **common_kwargs)
