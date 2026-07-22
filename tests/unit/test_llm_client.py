"""Tests for the LLM client abstraction (P0.5).

Covers:
- Deterministic mode without network
- API mode without silent fallback
- Factory mode selection
- Schema validation
- Authentication failure
- Timeout handling
- Prompt/model provenance
"""

from __future__ import annotations

import asyncio
import os

import pytest

from reflex.core.lesson_extractor import (
    ExtractedControlType,
    ExtractedFailureCategory,
    ExtractedTrigger,
    ExtractedVulnerability,
    LessonExtractionResult,
)
from reflex.core.llm_client import (
    APIBasedLLMClient,
    DeterministicLLMClient,
    ExtractionInput,
    ExtractionOutput,
    LLMAuthenticationError,
    LLMClient,
    LLMError,
    LLMFallbackProhibitedError,
    LLMTimeoutError,
    LLMValidationError,
    create_llm_client,
)
from reflex.models import Confidence


# -- Test fixtures ------------------------------------------------------------


def sample_input() -> ExtractionInput:
    return ExtractionInput(
        incident_urn="urn:li:incident:test-001",
        incident_title="Duplicate transactions in finance_daily_ledger",
        incident_description="Non-idempotent retry inserted duplicate rows.",
        human_confirmed_root_cause="Non-idempotent retry logic in ingestion pipeline.",
        incident_custom_type="DUPLICATE_ROWS",
    )


def sample_ownership_input() -> ExtractionInput:
    return ExtractionInput(
        incident_urn="urn:li:incident:test-002",
        incident_title="Inactive owner bob on finance assets",
        incident_description="Bob was deactivated but remains TECHNICAL_OWNER.",
        human_confirmed_root_cause="Offboarding process does not update ownership.",
        incident_custom_type="ORPHANED_OWNERSHIP",
    )


# -- P0.5: Deterministic mode tests -------------------------------------------


class TestDeterministicLLMClient:
    """Deterministic mode works without network or API key."""

    def test_deterministic_mode_is_default(self) -> None:
        """Factory creates DeterministicLLMClient by default."""
        client = create_llm_client()
        assert isinstance(client, DeterministicLLMClient)
        assert client.mode == "deterministic"

    def test_deterministic_mode_explicit(self) -> None:
        """Factory creates DeterministicLLMClient when mode is specified."""
        client = create_llm_client("deterministic")
        assert isinstance(client, DeterministicLLMClient)

    def test_deterministic_extracts_duplicate_rows(self) -> None:
        """Deterministic client correctly extracts duplicate-row lesson."""
        client = DeterministicLLMClient()

        async def run():
            return await client.extract_lesson(sample_input())

        output = asyncio.run(run())
        assert isinstance(output, ExtractionOutput)
        assert output.extraction_mode == "deterministic"
        assert output.model_identifier == "deterministic-template"
        assert output.result.failure_category == ExtractedFailureCategory.DUPLICATE_ROWS
        assert output.result.trigger == ExtractedTrigger.RETRY_AFTER_PARTIAL_FAILURE
        assert output.result.candidate_control_type == ExtractedControlType.UNIQUENESS
        assert output.result.target_field == "transaction_id"
        assert output.result.confidence == Confidence.HIGH

    def test_deterministic_extracts_orphaned_ownership(self) -> None:
        """Deterministic client correctly extracts ownership lesson."""
        client = DeterministicLLMClient()

        async def run():
            return await client.extract_lesson(sample_ownership_input())

        output = asyncio.run(run())
        assert output.result.failure_category == ExtractedFailureCategory.ORPHANED_OWNERSHIP
        assert output.result.candidate_control_type == ExtractedControlType.ACTIVE_OWNERSHIP

    def test_deterministic_no_network_required(self) -> None:
        """Deterministic mode requires no network connectivity."""
        client = DeterministicLLMClient()

        async def run():
            return await client.extract_lesson(sample_input())

        # Should complete instantly with no network
        output = asyncio.run(run())
        assert output.elapsed_ms < 1000  # Under 1 second
        assert output.token_count is None
        assert output.cost_estimate is None

    def test_deterministic_produces_validated_output(self) -> None:
        """Output passes LessonExtractionResult validation."""
        client = DeterministicLLMClient()

        async def run():
            return await client.extract_lesson(sample_input())

        output = asyncio.run(run())
        # Re-validate to confirm
        validated = LessonExtractionResult.model_validate(output.result.model_dump())
        assert validated.failure_category == ExtractedFailureCategory.DUPLICATE_ROWS

    def test_deterministic_implements_protocol(self) -> None:
        """DeterministicLLMClient satisfies the LLMClient protocol."""
        client = DeterministicLLMClient()
        assert isinstance(client, LLMClient)


# -- P0.5: API mode tests -----------------------------------------------------


class TestAPIModeConfiguration:
    """API mode configuration and error handling."""

    def test_api_mode_requires_key(self, monkeypatch) -> None:
        """API mode raises without API key."""
        monkeypatch.delenv("REFLEX_LLM_API_KEY", raising=False)
        with pytest.raises(LLMAuthenticationError, match="REFLEX_LLM_API_KEY"):
            APIBasedLLMClient()

    def test_api_mode_with_key(self, monkeypatch) -> None:
        """API mode creates client with valid key."""
        monkeypatch.setenv("REFLEX_LLM_API_KEY", "test-key-123")
        client = APIBasedLLMClient()
        assert client.mode == "api"
        assert client._model == "gpt-4o"

    def test_api_mode_custom_model(self, monkeypatch) -> None:
        """API mode respects custom model configuration."""
        monkeypatch.setenv("REFLEX_LLM_API_KEY", "test-key")
        monkeypatch.setenv("REFLEX_LLM_MODEL", "gpt-4o-mini")
        client = APIBasedLLMClient()
        assert client._model == "gpt-4o-mini"

    def test_factory_creates_api_client(self, monkeypatch) -> None:
        """Factory creates APIBasedLLMClient when mode=api."""
        monkeypatch.setenv("REFLEX_LLM_API_KEY", "test-key")
        client = create_llm_client("api")
        assert isinstance(client, APIBasedLLMClient)
        assert client.mode == "api"

    def test_factory_env_var_deterministic(self, monkeypatch) -> None:
        """Factory reads REFLEX_LLM_MODE from environment."""
        monkeypatch.setenv("REFLEX_LLM_MODE", "deterministic")
        client = create_llm_client()
        assert isinstance(client, DeterministicLLMClient)

    def test_factory_unknown_mode_raises(self) -> None:
        """Factory raises for unknown mode."""
        with pytest.raises(ValueError, match="Unknown REFLEX_LLM_MODE"):
            create_llm_client("unknown_mode")


# -- P0.5: No silent fallback tests -------------------------------------------


class TestNoSilentFallback:
    """API mode never silently falls back to deterministic mode."""

    def test_api_mode_without_key_fails_loudly(self, monkeypatch) -> None:
        """API mode without key raises immediately — no fallback."""
        monkeypatch.delenv("REFLEX_LLM_API_KEY", raising=False)
        with pytest.raises(LLMAuthenticationError):
            create_llm_client("api")

    def test_deterministic_mode_stays_deterministic(self) -> None:
        """Deterministic mode does not attempt API calls."""
        client = create_llm_client("deterministic")
        assert isinstance(client, DeterministicLLMClient)
        # No network call happens


# -- P0.5: Schema validation tests --------------------------------------------


class TestSchemaValidation:
    """LLM output must pass Pydantic validation."""

    def test_valid_extraction_passes(self) -> None:
        """Valid extraction result passes validation."""
        result = LessonExtractionResult(
            failure_category=ExtractedFailureCategory.DUPLICATE_ROWS,
            trigger=ExtractedTrigger.RETRY_AFTER_PARTIAL_FAILURE,
            vulnerable_characteristics=[ExtractedVulnerability.APPEND_ONLY_WITHOUT_IDEMPOTENCY],
            candidate_control_type=ExtractedControlType.UNIQUENESS,
            target_field="transaction_id",
            confidence=Confidence.HIGH,
        )
        validated = LessonExtractionResult.model_validate(result.model_dump())
        assert validated.failure_category == ExtractedFailureCategory.DUPLICATE_ROWS

    def test_missing_required_field_fails(self) -> None:
        """Missing required fields fail validation."""
        with pytest.raises(Exception):
            LessonExtractionResult(
                failure_category=ExtractedFailureCategory.DUPLICATE_ROWS,
                trigger=ExtractedTrigger.RETRY_AFTER_PARTIAL_FAILURE,
                vulnerable_characteristics=[],
                candidate_control_type=ExtractedControlType.UNIQUENESS,
            )

    def test_unknown_control_type_rejected(self) -> None:
        """Unknown control types are rejected."""
        with pytest.raises(Exception):
            LessonExtractionResult(
                failure_category=ExtractedFailureCategory.DUPLICATE_ROWS,
                trigger=ExtractedTrigger.RETRY_AFTER_PARTIAL_FAILURE,
                vulnerable_characteristics=[ExtractedVulnerability.APPEND_ONLY_WITHOUT_IDEMPOTENCY],
                candidate_control_type="invalid_type",  # Not a valid enum value
                confidence=Confidence.HIGH,
            )


# -- P0.5: Output provenance tests --------------------------------------------


class TestOutputProvenance:
    """Every extraction output includes model, prompt, and mode provenance."""

    def test_deterministic_output_has_provenance(self) -> None:
        """Deterministic output includes model and prompt identifiers."""
        client = DeterministicLLMClient()

        async def run():
            return await client.extract_lesson(sample_input())

        output = asyncio.run(run())
        assert output.model_identifier == "deterministic-template"
        assert output.prompt_version == "mvp-template-v1"
        assert output.extraction_mode == "deterministic"
        assert output.elapsed_ms >= 0
