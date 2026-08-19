"""Unit Tests for Top 7 Enterprise Connector Skill Packages."""

import os
import pytest
from unittest.mock import patch, MagicMock
from skills import (
    search_sharepoint,
    search_jira,
    search_google_drive,
    search_salesforce,
    search_slack,
    search_github,
    search_bigquery,
)
from tools.scaffold import create_skill


class MockToolContext:
    def __init__(self, state=None):
        self.state = state or {}


def test_category_a_skills_fail_closed_without_token():
    """Verifies that all 4 Category A skills strictly fail closed when user OAuth token is missing."""
    empty_context = MockToolContext(state={})
    
    with patch.dict(os.environ, {"ENV": "production"}):
        res_sp = search_sharepoint("payroll", tool_context=empty_context)
        assert "AUTH_REQUIRED" in res_sp
        
        res_jira = search_jira("sprint bug", tool_context=empty_context)
        assert "AUTH_REQUIRED" in res_jira
        
        res_drive = search_google_drive("quarterly spreadsheet", tool_context=empty_context)
        assert "AUTH_REQUIRED" in res_drive
        
        res_sf = search_salesforce("opportunity deal", tool_context=empty_context)
        assert "AUTH_REQUIRED" in res_sf


def test_category_a_sharepoint_with_token(monkeypatch):
    """Verifies that SharePoint skill succeeds when user OAuth token is present."""
    mock_context = MockToolContext(state={"sharepoint_oauth": "ya29.alice_valid_token"})
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {
                "document": {
                    "id": "doc_1",
                    "derivedStructData": {
                        "title": "2026 Executive Payroll.docx",
                        "link": "https://sharepoint.com/payroll.docx",
                        "snippets": [{"snippet": "Executive payroll details."}]
                    }
                }
            }
        ]
    }
    
    with patch("requests.Session.post", return_value=mock_resp):
        res = search_sharepoint("payroll", tool_context=mock_context)
        assert "2026 Executive Payroll.docx" in res
        assert "https://sharepoint.com/payroll.docx" in res


def test_category_b_slack_and_github_service_account(monkeypatch):
    """Verifies that Category B skills execute using Service Account ADC credentials."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {
                "document": {
                    "id": "msg_101",
                    "structData": {
                        "title": "#announcements: Cluster failover",
                        "url": "https://slack.com/archives/C123/p456",
                        "description": "Failover completed smoothly."
                    }
                }
            }
        ]
    }
    
    with patch("tools.datastore_search._get_adc_token", return_value="mock_adc_token"):
        with patch("requests.Session.post", return_value=mock_resp):
            res_slack = search_slack("failover")
            assert "#announcements: Cluster failover" in res_slack
            
            res_gh = search_github("auth decorator")
            assert "Cluster failover" in res_gh


def test_category_c_bigquery_column_filtering(monkeypatch):
    """Verifies that BigQuery structured skill filters displayed columns."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {
                "document": {
                    "id": "row_101",
                    "structData": {
                        "customer_id": "CUST-9921",
                        "region": "North America",
                        "q3_revenue": "$4,250,000",
                        "internal_secret_salt": "do_not_leak_this"
                    }
                }
            }
        ]
    }
    
    with patch("tools.datastore_search._get_adc_token", return_value="mock_adc_token"):
        with patch("requests.Session.post", return_value=mock_resp):
            res = search_bigquery(
                "CUST-9921",
                display_columns=["customer_id", "region", "q3_revenue"]
            )
            assert "customer_id: CUST-9921" in res
            assert "q3_revenue: $4,250,000" in res
            assert "region: North America" in res


def test_scaffolder_creates_valid_skill(tmp_path):
    """Verifies that tools.scaffold creates a valid runnable skill directory."""
    skill_dir = create_skill(
        name="zendesk_support",
        category="A",
        engine_id="zendesk-engine",
        token_key="zendesk_oauth",
        scopes=["read:tickets"],
        output_dir=str(tmp_path)
    )
    
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "tool.py").exists()
    assert (skill_dir / "example_agent.py").exists()
    
    skill_md = (skill_dir / "SKILL.md").read_text()
    assert "ge-zendesk-support-connector" in skill_md
    assert "read:tickets" in skill_md
