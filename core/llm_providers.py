"""
LLM Provider Abstraction for AuraJobs.

Provides a unified interface for multiple LLM providers:
- LiteLLM (supports 100+ providers via single interface)
- Direct OpenAI-compatible endpoints (Groq, OpenRouter, Together AI, etc.)
- Local Ollama
- Google Gemini

All providers support the same `complete()` method signature.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import os
import yaml
from pathlib import Path


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, model: str, **kwargs):
        self.model = model
        self.config = kwargs

    @abstractmethod
    def complete(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Complete a prompt and return the response text."""
        pass

    @abstractmethod
    def complete_structured(
        self,
        prompt: str,
        response_model: type,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Complete a prompt and return a structured (Pydantic) response."""
        pass


class LiteLLMProvider(BaseLLMProvider):
    """LiteLLM provider - unified interface for 100+ LLM providers."""

    def __init__(self, model: str, **kwargs):
        super().__init__(model, **kwargs)
        try:
            from litellm import completion
            self._completion = completion
        except ImportError:
            raise ImportError("LiteLLM not installed. Run: pip install litellm")

        # Set API keys from environment if not provided
        self._setup_env_keys()

    def _setup_env_keys(self):
        """Auto-populate API keys from environment variables."""
        provider_keys = {
            "gemini": "GEMINI_API_KEY",
            "groq": "GROQ_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "cohere": "COHERE_API_KEY",
            "together_ai": "TOGETHER_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
        }

        # Extract provider from model string (e.g., "gemini/gemini-1.5-pro" -> "gemini")
        provider = self.model.split("/")[0] if "/" in self.model else "unknown"
        env_var = provider_keys.get(provider)

        if env_var and not os.getenv(env_var):
            # Check config for key
            key = self.config.get(f"{provider}_api_key")
            if key:
                os.environ[env_var] = key

    def complete(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self._completion(
            model=self.model,
            messages=messages,
            **{**self.config, **kwargs}
        )
        return response.choices[0].message.content

    def complete_structured(
        self,
        prompt: str,
        response_model: type,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Use LiteLLM with instructor-style structured output."""
        try:
            import instructor
            from litellm import completion
        except ImportError:
            raise ImportError("Instructor not installed. Run: pip install instructor")

        client = instructor.from_litellm(completion)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_model=response_model,
            **{**self.config, **kwargs}
        )


class OllamaProvider(BaseLLMProvider):
    """Local Ollama provider via OpenAI-compatible endpoint."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434/v1", **kwargs):
        super().__init__(model, **kwargs)
        self.base_url = base_url
        try:
            from openai import OpenAI
            self.client = OpenAI(
                base_url=base_url,
                api_key="ollama",  # Required but ignored by Ollama
            )
        except ImportError:
            raise ImportError("OpenAI client not installed. Run: pip install openai")

    def complete(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **{**self.config, **kwargs}
        )
        return response.choices[0].message.content

    def complete_structured(
        self,
        prompt: str,
        response_model: type,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Any:
        try:
            import instructor
        except ImportError:
            raise ImportError("Instructor not installed. Run: pip install instructor")

        client = instructor.from_openai(self.client)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_model=response_model,
            **{**self.config, **kwargs}
        )


class OpenAICompatibleProvider(BaseLLMProvider):
    """Generic OpenAI-compatible provider (Groq, OpenRouter, Together AI, etc.)."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        **kwargs
    ):
        super().__init__(model, **kwargs)
        self.base_url = base_url
        self.api_key = api_key
        try:
            from openai import OpenAI
            self.client = OpenAI(base_url=base_url, api_key=api_key)
        except ImportError:
            raise ImportError("OpenAI client not installed. Run: pip install openai")

    def complete(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **{**self.config, **kwargs}
        )
        return response.choices[0].message.content

    def complete_structured(
        self,
        prompt: str,
        response_model: type,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Any:
        try:
            import instructor
        except ImportError:
            raise ImportError("Instructor not installed. Run: pip install instructor")

        client = instructor.from_openai(self.client)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_model=response_model,
            **{**self.config, **kwargs}
        )


class GoogleGeminiProvider(BaseLLMProvider):
    """Direct Google Gemini provider using google-genai SDK."""

    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
        except ImportError:
            raise ImportError("Google GenAI not installed. Run: pip install google-genai")

    def complete(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        contents = []
        if system_prompt:
            contents.append({"role": "system", "parts": [{"text": system_prompt}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            **{**self.config, **kwargs}
        )
        return response.text

    def complete_structured(
        self,
        prompt: str,
        response_model: type,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Any:
        try:
            import instructor
        except ImportError:
            raise ImportError("Instructor not installed. Run: pip install instructor")

        # Use instructor with google-genai
        client = instructor.from_google_genai(self.client)

        contents = []
        if system_prompt:
            contents.append({"role": "system", "parts": [{"text": system_prompt}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        return client.chat.completions.create(
            model=self.model,
            messages=contents,
            response_model=response_model,
            **{**self.config, **kwargs}
        )


# Provider registry
PROVIDER_CLASSES = {
    "litellm": LiteLLMProvider,
    "ollama": OllamaProvider,
    "openai_compatible": OpenAICompatibleProvider,
    "gemini": GoogleGeminiProvider,
}


def create_provider(config: Dict[str, Any]) -> BaseLLMProvider:
    """
    Factory function to create an LLM provider from config.

    Config format:
    {
        "provider": "litellm",  # or "ollama", "openai_compatible", "gemini"
        "model": "groq/llama-3.1-8b-instant",
        "base_url": "http://localhost:11434/v1",  # for ollama/openai_compatible
        "api_key": "sk-...",  # for openai_compatible/gemini
        "temperature": 0.1,
        "max_tokens": 1000,
    }
    """
    provider_type = config.get("provider", "litellm")
    model = config.get("model")

    if not model:
        raise ValueError("Model is required in provider config")

    provider_class = PROVIDER_CLASSES.get(provider_type)
    if not provider_class:
        raise ValueError(f"Unknown provider type: {provider_type}")

    # Filter out provider type and model from config before passing to constructor
    filtered_config = {k: v for k, v in config.items() if k not in ("provider", "model")}

    return provider_class(model=model, **filtered_config)


def load_provider_from_yaml(config_path: str = "config/llm.yaml") -> Optional[BaseLLMProvider]:
    """Load LLM provider from YAML config file."""
    path = Path(config_path)
    if not path.exists():
        return None

    with open(path) as f:
        config = yaml.safe_load(f)

    if not config or "provider" not in config:
        return None

    return create_provider(config)


# Convenience function for simple completions
def quick_complete(prompt: str, provider: Optional[BaseLLMProvider] = None, **kwargs) -> str:
    """Quick completion using default or provided provider."""
    if provider is None:
        provider = load_provider_from_yaml()
    if provider is None:
        raise ValueError("No provider configured. Create config/llm.yaml or pass provider explicitly.")
    return provider.complete(prompt, **kwargs)