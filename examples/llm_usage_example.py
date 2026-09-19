"""
Example: Using AuraJobs LLM Provider Abstraction

This demonstrates how to use the unified LLM interface for:
1. Simple text completion
2. Structured output (Pydantic models)
3. Switching between providers via config

Run with: python examples/llm_usage_example.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.llm_providers import (
    LiteLLMProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    GoogleGeminiProvider,
    create_provider,
    load_provider_from_yaml,
    quick_complete,
)
from pydantic import BaseModel


# Example structured response models
class JobSummary(BaseModel):
    title: str
    company: str
    key_skills: list[str]
    experience_years: str
    visa_sponsorship: bool
    remote_friendly: bool
    match_score: int  # 0-100


class VisaDetectionResult(BaseModel):
    visa_mentioned: bool
    visa_type: str  # "H1B", "Global Relocation", "Not mentioned", etc.
    evidence: str
    confidence: float


def example_basic_usage():
    """Basic text completion with different providers."""
    print("=" * 60)
    print("BASIC TEXT COMPLETION")
    print("=" * 60)

    # Using LiteLLM (unified interface)
    provider = LiteLLMProvider(model="groq/llama-3.1-8b-instant")

    prompt = "Summarize this job in one sentence: Senior Product Designer at Airbnb, Singapore. Focus on design systems and international expansion. 7+ years experience required."
    response = provider.complete(prompt)
    print(f"LiteLLM (Groq): {response}\n")

    # Using Ollama (local)
    try:
        ollama = OllamaProvider(model="llama3.2:3b")
        response = ollama.complete(prompt)
        print(f"Ollama (local): {response}\n")
    except Exception as e:
        print(f"Ollama not available: {e}\n")


def example_structured_output():
    """Structured output with Pydantic models."""
    print("=" * 60)
    print("STRUCTURED OUTPUT (Pydantic)")
    print("=" * 60)

    provider = LiteLLMProvider(model="groq/llama-3.1-8b-instant")

    job_text = """
    Senior Product Designer - Airbnb (Singapore)
    We're looking for a Staff Experience Designer to join our International team.
    7+ years of experience required. Focus on design systems, cross-cultural design,
    and scaling products across APAC markets. Visa sponsorship available for
    qualified candidates. Hybrid work model (3 days in office).
    """

    prompt = f"Extract structured information from this job posting:\n{job_text}"

    try:
        result = provider.complete_structured(
            prompt=prompt,
            response_model=JobSummary,
            system_prompt="You are a job analysis expert. Extract accurate information from job postings."
        )
        print(f"Title: {result.title}")
        print(f"Company: {result.company}")
        print(f"Key Skills: {result.key_skills}")
        print(f"Experience: {result.experience_years}")
        print(f"Visa Sponsorship: {result.visa_sponsorship}")
        print(f"Remote Friendly: {result.remote_friendly}")
        print(f"Match Score: {result.match_score}/100\n")
    except Exception as e:
        print(f"Structured output failed: {e}\n")


def example_visa_detection():
    """Visa sponsorship detection with structured output."""
    print("=" * 60)
    print("VISA SPONSORSHIP DETECTION")
    print("=" * 60)

    provider = LiteLLMProvider(model="groq/llama-3.1-8b-instant")

    job_descriptions = [
        "We offer H1B visa sponsorship for qualified candidates. Relocation package included.",
        "Must be authorized to work in the US without sponsorship. No visa support.",
        "Global relocation support available. We sponsor work visas for international talent.",
        "Product Designer role in Dubai. UAE employment visa provided by company.",
    ]

    for jd in job_descriptions:
        prompt = f"Analyze this job description for visa sponsorship:\n{jd}"

        try:
            result = provider.complete_structured(
                prompt=prompt,
                response_model=VisaDetectionResult,
                system_prompt="You are a visa sponsorship detection expert. Analyze job descriptions and return structured results."
            )
            print(f"JD: {jd[:60]}...")
            print(f"  Visa Mentioned: {result.visa_mentioned}")
            print(f"  Visa Type: {result.visa_type}")
            print(f"  Evidence: {result.evidence}")
            print(f"  Confidence: {result.confidence:.0%}\n")
        except Exception as e:
            print(f"  Failed: {e}\n")


def example_config_based():
    """Using config file (config/llm.yaml)."""
    print("=" * 60)
    print("CONFIG-BASED USAGE (config/llm.yaml)")
    print("=" * 60)

    try:
        provider = load_provider_from_yaml("config/llm.yaml")
        if provider:
            response = provider.complete(
                "Write a one-line tagline for AuraJobs job search engine.",
                system_prompt="You are a marketing copywriter."
            )
            print(f"From config: {response}\n")
        else:
            print("No config/llm.yaml found or invalid config\n")
    except Exception as e:
        print(f"Config-based failed: {e}\n")


def example_quick_complete():
    """Quick completion using default config."""
    print("=" * 60)
    print("QUICK COMPLETE HELPER")
    print("=" * 60)

    try:
        response = quick_complete(
            "List 3 key skills for a Senior Product Designer.",
            system_prompt="You are a hiring manager."
        )
        print(f"Quick complete: {response}\n")
    except Exception as e:
        print(f"Quick complete failed: {e}\n")


def example_provider_switching():
    """Demonstrate switching providers by changing model string."""
    print("=" * 60)
    print("PROVIDER SWITCHING (same code, different model)")
    print("=" * 60)

    prompt = "What is the most important skill for a Product Designer?"

    models = [
        ("Groq (Llama 3.1 8B)", "groq/llama-3.1-8b-instant"),
        ("Groq (GPT-OSS 20B)", "groq/openai/gpt-oss-20b"),
        ("Gemini 2.5 Flash", "gemini/gemini-2.5-flash"),
        ("Ollama (local Llama 3.2)", "ollama/llama3.2:3b"),
    ]

    for name, model in models:
        try:
            provider = LiteLLMProvider(model=model)
            response = provider.complete(prompt, max_tokens=50)
            print(f"{name}: {response[:80]}...")
        except Exception as e:
            print(f"{name}: Error - {e}")
        print()


if __name__ == "__main__":
    # Check for API keys
    has_groq = bool(os.getenv("GROQ_API_KEY"))
    has_gemini = bool(os.getenv("GEMINI_API_KEY"))

    if not has_groq and not has_gemini:
        print("⚠️  No API keys found in environment.")
        print("   Set GROQ_API_KEY or GEMINI_API_KEY for cloud providers.")
        print("   Or run `ollama serve` for local models.\n")

    example_basic_usage()
    example_structured_output()
    example_visa_detection()
    example_config_based()
    example_quick_complete()
    example_provider_switching()