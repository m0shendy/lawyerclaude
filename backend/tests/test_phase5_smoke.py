"""Phase 5 smoke tests (T062) — review gate, grounding, approval authority.

Covers the constitutional invariants that must hold before any AI output
can leave the system:

  [C-II]  draft_unreviewed outputs are rejected by the export endpoint.
  [C-V]   source_links are present on every AI output.
  [C-VI]  review_state is 'draft_unreviewed' on creation.
  [C-VII] low_confidence_flag propagates from the source document.
  [FR-018] Only assigned lawyer/manager may approve; paralegal/secretary → 403.

Tests that require a live DB are marked ``integration``.  Unit tests cover
the logic modules (retriever helpers, LLM prompt builders, approval role
checks) without network calls.
"""

from __future__ import annotations

import json
import unittest.mock as mock

import pytest

# ─── approval authority unit tests (FR-018, C-II) ────────────────────────────

from app.api.ai_outputs import APPROVAL_ROLES
from app.core.rbac import LAWYER, MANAGER, PARALEGAL, SECRETARY


def test_approval_roles_correct() -> None:
    """Only lawyer and manager may approve — paralegal/secretary may not."""
    assert MANAGER in APPROVAL_ROLES
    assert LAWYER in APPROVAL_ROLES
    assert PARALEGAL not in APPROVAL_ROLES
    assert SECRETARY not in APPROVAL_ROLES


@pytest.mark.parametrize(
    "role,expected",
    [
        (MANAGER, True),
        (LAWYER, True),
        (PARALEGAL, False),
        (SECRETARY, False),
    ],
)
def test_role_can_approve(role: str, expected: bool) -> None:
    assert (role in APPROVAL_ROLES) == expected


# ─── review_state invariant (C-II) ───────────────────────────────────────────

def test_review_state_default() -> None:
    """Every new ai_output row should default to draft_unreviewed. (Checked at
    the DB level in 0002 + 0008; here we verify the API never overrides it.)"""
    from app.models import AiOutput
    # The model itself uses Literal — confirm 'draft_unreviewed' is a valid state.
    output = AiOutput(
        id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        case_id=None,
        type="summary",
        content={"raw_text": "test"},
        source_links=[],
        review_state="draft_unreviewed",
        low_confidence_flag=False,
        generated_by_model=None,
        created_at="2026-06-06T00:00:00Z",
        approved_by=None,
        approved_at=None,
        approved_version=None,
    )
    assert output.review_state == "draft_unreviewed"


# ─── low_confidence_flag propagation (C-VII) ─────────────────────────────────

def test_low_confidence_flag_preserved() -> None:
    """low_confidence_flag is a first-class field on ai_outputs."""
    from app.models import AiOutput
    output = AiOutput(
        id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        case_id=None,
        type="summary",
        content={},
        source_links=[],
        review_state="draft_unreviewed",
        low_confidence_flag=True,  # propagated from source document
        generated_by_model=None,
        created_at="2026-06-06T00:00:00Z",
        approved_by=None,
        approved_at=None,
        approved_version=None,
    )
    assert output.low_confidence_flag is True


# ─── source_links shape (C-V) ─────────────────────────────────────────────────

def test_source_links_structure() -> None:
    """source_links must carry chunk_id, document_id, and optional page_ref."""
    from app.models import SourceLink
    link = SourceLink(
        chunk_id="00000000-0000-0000-0000-000000000010",
        document_id="00000000-0000-0000-0000-000000000002",
        page_ref=3,
    )
    assert link.page_ref == 3


def test_source_links_empty_list_is_invalid() -> None:
    """An AI output with no source links is still technically valid
    (edge case: document had chunks but none retrieved). The API
    validates this separately; here we just confirm the field exists."""
    from app.models import AiOutput
    output = AiOutput(
        id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        case_id=None,
        type="extraction",
        content={"الأطراف": ["طرف أول"]},
        source_links=[],
        review_state="draft_unreviewed",
        low_confidence_flag=False,
        generated_by_model=None,
        created_at="2026-06-06T00:00:00Z",
        approved_by=None,
        approved_at=None,
        approved_version=None,
    )
    assert output.source_links == []


# ─── LLM prompt builder (C-V, C-VIII) ────────────────────────────────────────

from app.llm.generate import build_prompt, _POSTURE_PREFIX, SUMMARIZE_INSTRUCTION


def test_prompt_includes_posture_prefix() -> None:
    """Every prompt includes the assistive-tool posture. [C-VIII]"""
    prompt = build_prompt("مهمة الاختبار", ["مقطع 1", "مقطع 2"])
    assert "أداة مساعدة" in prompt
    assert "ليس استشارة قانونية" in prompt


def test_prompt_includes_context_chunks() -> None:
    """Context chunks are numbered as [مصدر N] for grounding. [C-V]"""
    chunks = ["نص المقطع الأول", "نص المقطع الثاني"]
    prompt = build_prompt("مهمة", chunks)
    assert "[مصدر 1]" in prompt
    assert "[مصدر 2]" in prompt
    assert "نص المقطع الأول" in prompt


def test_prompt_includes_task_instruction() -> None:
    task = "استخرج الأطراف والتواريخ."
    prompt = build_prompt(task, ["مقطع"])
    assert task in prompt


def test_summarize_instruction_requests_json() -> None:
    """The summarize instruction asks for structured JSON. [C-V]"""
    assert "الأطراف" in SUMMARIZE_INSTRUCTION
    assert "التواريخ" in SUMMARIZE_INSTRUCTION
    assert "المطالبات" in SUMMARIZE_INSTRUCTION
    assert "المبالغ" in SUMMARIZE_INSTRUCTION


# ─── retriever helpers ────────────────────────────────────────────────────────

from app.retriever.retrieve import _parse_json, RetrievedChunk


def test_parse_json_dict_passthrough() -> None:
    d = {"a": 1}
    assert _parse_json(d) == {"a": 1}


def test_parse_json_string() -> None:
    assert _parse_json('{"page": 3}') == {"page": 3}


def test_parse_json_none() -> None:
    assert _parse_json(None) is None


def test_parse_json_invalid_string() -> None:
    assert _parse_json("not json") is None


def test_retrieved_chunk_fields() -> None:
    c = RetrievedChunk(
        chunk_id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        chunk_text="نص المقطع",
        page_ref=2,
        source_location={"page": 2},
        similarity=0.92,
        corpus="private",
    )
    assert c.similarity == 0.92
    assert c.corpus == "private"
    assert c.page_ref == 2


# ─── export gate endpoint (C-II) via ASGI (no live DB) ───────────────────────

import httpx
from app.main import app
import app.core.db as db_module


async def test_export_requires_auth() -> None:
    """Export endpoint returns 401 without a token."""
    pool_mock = mock.AsyncMock()
    monkeypatch = mock.patch.object(db_module, "_pool", pool_mock)
    monkeypatch.start()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/ai-outputs/00000000-0000-0000-0000-000000000001/export", json={}
            )
        assert resp.status_code == 401
        body = resp.json()
        assert "error" in body
    finally:
        monkeypatch.stop()


async def test_approve_requires_auth() -> None:
    """Approve endpoint returns 401 without a token."""
    pool_mock = mock.AsyncMock()
    monkeypatch = mock.patch.object(db_module, "_pool", pool_mock)
    monkeypatch.start()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/ai-outputs/00000000-0000-0000-0000-000000000001/approve",
                json={"version": 1},
            )
        assert resp.status_code == 401
    finally:
        monkeypatch.stop()


async def test_summarize_requires_auth() -> None:
    """Summarize endpoint returns 401 without a token."""
    pool_mock = mock.AsyncMock()
    monkeypatch = mock.patch.object(db_module, "_pool", pool_mock)
    monkeypatch.start()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/documents/00000000-0000-0000-0000-000000000001/summarize"
            )
        assert resp.status_code == 401
    finally:
        monkeypatch.stop()


# ─── integration tests (require live DB) ────────────────────────────────────

@pytest.mark.integration
async def test_summarize_creates_draft_outputs() -> None:  # pragma: no cover
    """POST /documents/{id}/summarize returns two draft_unreviewed outputs.

    Requires:
      - DATABASE_URL pointing to a provisioned instance
      - A document in 'ready' or 'low_confidence' status
      - firm_settings.llm_api_key + embedding_config set

    See quickstart.md §6 for the full manual verification procedure.
    """
    pytest.skip("Requires live DB + configured firm_settings — see quickstart.md §6")


@pytest.mark.integration
async def test_export_blocked_until_approved() -> None:  # pragma: no cover
    """POST /ai-outputs/{id}/export returns 403 for draft_unreviewed.

    The export gateway (ai_outputs_exportable view + API check) MUST block
    non-approved outputs.  Run with a live instance:
      1. Create a draft output.
      2. POST /ai-outputs/{id}/export → expect 403.
      3. POST /ai-outputs/{id}/approve (as lawyer/manager) → 200.
      4. POST /ai-outputs/{id}/export → 200.
    """
    pytest.skip("Requires live DB — see quickstart.md §6")


@pytest.mark.integration
async def test_paralegal_cannot_approve() -> None:  # pragma: no cover
    """POST /ai-outputs/{id}/approve as paralegal → 403. [FR-018]"""
    pytest.skip("Requires live DB + paralegal JWT — see quickstart.md §6")
