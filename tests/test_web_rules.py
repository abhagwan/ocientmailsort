"""Tests for the rules web routes."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest
from fastapi import Request
from mailsort.web.routes.rules import explain_move
from mailsort.db.database import Database
from mailsort.config import Config

def test_explain_move_route_rule_source(db: Database, test_config: Config):
    """Verify the explain route generates a statistical explanation for rule moves."""
    # 1. Setup: Create a rule and a corresponding audit log entry
    rule_id = db.execute(
        "INSERT INTO rules (rule_type, condition_value, target_folder_path, confidence, source) "
        "VALUES ('exact_sender', 'noreply@chase.com', 'INBOX/Affairs/Banks', 0.95, 'bootstrap')"
    ).lastrowid
    
    db.execute(
        "INSERT INTO audit_log (id, run_id, email_id, rule_id, classification_source, moved, target_folder, confidence, created_at) "
        "VALUES (100, 'run-1', 'e-1', ?, 'rule', 1, 'INBOX/Affairs/Banks', 1.0, datetime('now'))",
        (rule_id,)
    )
    db.commit()

    # 2. Mock FastAPI Request and its dependencies
    request = MagicMock(spec=Request)
    request.state.db = db
    request.app.state.templates = MagicMock()
    request.app.state.config = test_config

    # 3. Call the route handler
    response = explain_move(request, audit_id=100)

    # 4. Verify template rendering
    assert response is not None
    args, kwargs = request.app.state.templates.TemplateResponse.call_args
    assert args[0] == "audit/explain.html"
    
    context = args[1]
    assert "amazon.com" not in context["explanation"] # verify it uses the real data
    assert "noreply@chase.com" in context["explanation"]
    assert "100% success rate" in context["explanation"]

def test_explain_move_route_llm_source(db: Database, test_config: Config):
    """Verify the explain route shows LLM reasoning for AI moves."""
    db.execute(
        "INSERT INTO audit_log (id, run_id, email_id, classification_source, moved, target_folder, llm_reasoning, confidence, created_at) "
        "VALUES (101, 'run-1', 'e-2', 'llm', 1, 'INBOX/Shopping', 'Found order number', 1.0, datetime('now'))"
    )
    db.commit()

    request = MagicMock(spec=Request)
    request.state.db = db
    request.app.state.templates = MagicMock()
    request.app.state.config = test_config

    explain_move(request, audit_id=101)

    args, _ = request.app.state.templates.TemplateResponse.call_args
    context = args[1]
    assert "Found order number" in context["explanation"]

def test_explain_move_404(db: Database, test_config: Config):
    request = MagicMock(spec=Request)
    request.state.db = db
    with pytest.raises(Exception) as exc: # FastAPI HTTPException
        explain_move(request, audit_id=999)
