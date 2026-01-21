"""Tests for compliance module.

References:
- Requirements 7: Data Privacy and Security
- Design Section 8: Security Architecture
"""

import pytest
from datetime import datetime, timedelta
import tempfile

from compliance.gdpr import GDPRComplianceManager, DataExportRequest, DataDeletionRequest
from compliance.data_retention import (
    DataRetentionManager,
    DataCategory,
    RetentionPolicy,
)
from compliance.audit_reports import (
    ComplianceAuditReporter,
    ReportType,
)
from compliance.anonymization import DataAnonymizer, AnonymizationRule
from compliance.consent import (
    ConsentManager,
    ConsentType,
    ConsentStatus,
)
from compliance.policies import PolicyManager


# GDPR Tests

def test_gdpr_manager_initialization():
    """Test GDPR manager initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = GDPRComplianceManager(export_dir=tmpdir)
        
        assert manager.export_dir.exists()
        assert len(manager.export_requests) == 0
        assert len(manager.deletion_requests) == 0


def test_request_data_export():
    """Test data export request."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = GDPRComplianceManager(export_dir=tmpdir)
        
        request = manager.request_data_export("user123")
        
        assert request.user_id == "user123"
        assert request.status == "pending"
        assert len(manager.export_requests) == 1


def test_export_user_data():
    """Test user data export."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = GDPRComplianceManager(export_dir=tmpdir)
        
        data = manager.export_user_data("user123")
        
        assert data["user_id"] == "user123"
        assert "personal_information" in data
        assert "agents" in data
        assert "tasks" in data
        assert "knowledge_items" in data
        assert "memories" in data


def test_complete_export_request():
    """Test completing export request."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = GDPRComplianceManager(export_dir=tmpdir)
        
        request = manager.request_data_export("user123")
        success = manager.complete_export_request(request.request_id)
        
        assert success
        assert request.status == "completed"
        assert request.completed_at is not None


def test_request_data_deletion():
    """Test data deletion request."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = GDPRComplianceManager(export_dir=tmpdir)
        
        request = manager.request_data_deletion("user123")
        
        assert request.user_id == "user123"
        assert request.status == "pending"
        assert len(manager.deletion_requests) == 1


def test_delete_user_data():
    """Test user data deletion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = GDPRComplianceManager(export_dir=tmpdir)
        
        deleted_items = manager.delete_user_data("user123")
        
        assert len(deleted_items) > 0
        assert any("personal_info" in item for item in deleted_items)


def test_complete_deletion_request():
    """Test completing deletion request."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = GDPRComplianceManager(export_dir=tmpdir)
        
        request = manager.request_data_deletion("user123")
        success = manager.complete_deletion_request(request.request_id)
        
        assert success
        assert request.status == "completed"
        assert len(request.deleted_items) > 0


# Data Retention Tests

def test_retention_manager_initialization():
    """Test retention manager initialization."""
    manager = DataRetentionManager()
    
    assert len(manager.policies) > 0
    assert DataCategory.USER_DATA in manager.policies


def test_get_retention_policy():
    """Test getting retention policy."""
    manager = DataRetentionManager()
    
    policy = manager.get_policy(DataCategory.USER_DATA)
    
    assert policy is not None
    assert policy.category == DataCategory.USER_DATA
    assert policy.retention_days > 0


def test_set_retention_policy():
    """Test setting retention policy."""
    manager = DataRetentionManager()
    
    custom_policy = RetentionPolicy(
        category=DataCategory.TASK_DATA,
        retention_days=180,
        description="Custom task retention",
        auto_delete=True,
    )
    
    manager.set_policy(custom_policy)
    
    policy = manager.get_policy(DataCategory.TASK_DATA)
    assert policy.retention_days == 180


def test_calculate_expiry_date():
    """Test expiry date calculation."""
    manager = DataRetentionManager()
    
    created_at = datetime(2024, 1, 1)
    expiry = manager.calculate_expiry_date(DataCategory.TASK_DATA, created_at)
    
    assert expiry > created_at
    assert (expiry - created_at).days == 365


def test_is_expired():
    """Test expiry check."""
    manager = DataRetentionManager()
    
    # Old data should be expired
    old_date = datetime.now() - timedelta(days=400)
    assert manager.is_expired(DataCategory.TASK_DATA, old_date)
    
    # Recent data should not be expired
    recent_date = datetime.now() - timedelta(days=10)
    assert not manager.is_expired(DataCategory.TASK_DATA, recent_date)


def test_run_cleanup():
    """Test retention cleanup."""
    manager = DataRetentionManager()
    
    job = manager.run_cleanup(DataCategory.AGENT_DATA)
    
    assert job.category == DataCategory.AGENT_DATA
    assert job.status == "completed"
    assert job.items_deleted >= 0


def test_retention_stats():
    """Test retention statistics."""
    manager = DataRetentionManager()
    
    # Run some cleanups
    manager.run_cleanup(DataCategory.AGENT_DATA)
    manager.run_cleanup(DataCategory.TASK_DATA)
    
    stats = manager.get_retention_stats()
    
    assert stats["total_jobs"] >= 2
    assert stats["completed_jobs"] >= 2
    assert "policies" in stats


# Audit Reports Tests

def test_audit_reporter_initialization():
    """Test audit reporter initialization."""
    reporter = ComplianceAuditReporter()
    
    assert len(reporter.reports) == 0


def test_generate_access_report():
    """Test access report generation."""
    reporter = ComplianceAuditReporter()
    
    start_date = datetime.now() - timedelta(days=30)
    end_date = datetime.now()
    
    report = reporter.generate_access_report(start_date, end_date)
    
    assert report.report_type == ReportType.ACCESS_REPORT
    assert report.period_start == start_date
    assert report.period_end == end_date
    assert "total_accesses" in report.data


def test_generate_deletion_report():
    """Test deletion report generation."""
    reporter = ComplianceAuditReporter()
    
    start_date = datetime.now() - timedelta(days=30)
    end_date = datetime.now()
    
    report = reporter.generate_deletion_report(start_date, end_date)
    
    assert report.report_type == ReportType.DELETION_REPORT
    assert "total_deletions" in report.data


def test_generate_consent_report():
    """Test consent report generation."""
    reporter = ComplianceAuditReporter()
    
    start_date = datetime.now() - timedelta(days=30)
    end_date = datetime.now()
    
    report = reporter.generate_consent_report(start_date, end_date)
    
    assert report.report_type == ReportType.CONSENT_REPORT
    assert "consents_given" in report.data


def test_generate_compliance_summary():
    """Test compliance summary generation."""
    reporter = ComplianceAuditReporter()
    
    start_date = datetime.now() - timedelta(days=30)
    end_date = datetime.now()
    
    report = reporter.generate_compliance_summary(start_date, end_date)
    
    assert report.report_type == ReportType.COMPLIANCE_SUMMARY
    assert "compliance_score" in report.data
    assert len(reporter.reports) > 5  # Summary + sub-reports


def test_list_reports():
    """Test listing reports."""
    reporter = ComplianceAuditReporter()
    
    start_date = datetime.now() - timedelta(days=30)
    end_date = datetime.now()
    
    reporter.generate_access_report(start_date, end_date)
    reporter.generate_deletion_report(start_date, end_date)
    
    all_reports = reporter.list_reports()
    assert len(all_reports) == 2
    
    access_reports = reporter.list_reports(report_type=ReportType.ACCESS_REPORT)
    assert len(access_reports) == 1


# Anonymization Tests

def test_anonymizer_initialization():
    """Test anonymizer initialization."""
    anonymizer = DataAnonymizer()
    
    assert len(anonymizer.rules) > 0
    assert "user_id" in anonymizer.rules


def test_add_anonymization_rule():
    """Test adding anonymization rule."""
    anonymizer = DataAnonymizer()
    
    rule = AnonymizationRule(
        field_name="custom_field",
        method="hash",
        description="Custom field anonymization",
    )
    
    anonymizer.add_rule(rule)
    
    assert "custom_field" in anonymizer.rules


def test_anonymize_hash():
    """Test hash anonymization."""
    anonymizer = DataAnonymizer()
    
    data = {"user_id": "user123", "name": "John Doe"}
    anonymized = anonymizer.anonymize(data)
    
    assert anonymized["user_id"] != "user123"
    assert len(anonymized["user_id"]) == 16  # Hash length
    assert anonymized["name"] is None  # Suppressed


def test_anonymize_mask():
    """Test mask anonymization."""
    anonymizer = DataAnonymizer()
    
    data = {"ip_address": "192.168.1.100"}
    anonymized = anonymizer.anonymize(data)
    
    assert anonymized["ip_address"] == "192.168.1.***"


def test_anonymize_generalize():
    """Test generalize anonymization."""
    anonymizer = DataAnonymizer()
    
    data = {"age": 30}
    anonymized = anonymizer.anonymize(data)
    
    assert anonymized["age"] == "25-34"


def test_anonymize_batch():
    """Test batch anonymization."""
    anonymizer = DataAnonymizer()
    
    data_list = [
        {"user_id": "user1", "age": 25},
        {"user_id": "user2", "age": 35},
    ]
    
    anonymized_list = anonymizer.anonymize_batch(data_list)
    
    assert len(anonymized_list) == 2
    assert anonymized_list[0]["user_id"] != "user1"
    assert anonymized_list[0]["age"] == "25-34"


def test_anonymization_report():
    """Test anonymization report."""
    anonymizer = DataAnonymizer()
    
    report = anonymizer.get_anonymization_report()
    
    assert report["total_rules"] > 0
    assert "user_id" in report["rules"]


# Consent Management Tests

def test_consent_manager_initialization():
    """Test consent manager initialization."""
    manager = ConsentManager()
    
    assert len(manager.consents) == 0


def test_give_consent():
    """Test giving consent."""
    manager = ConsentManager()
    
    record = manager.give_consent(
        user_id="user123",
        consent_type=ConsentType.TERMS_OF_SERVICE,
        version="1.0",
    )
    
    assert record.user_id == "user123"
    assert record.consent_type == ConsentType.TERMS_OF_SERVICE
    assert record.status == ConsentStatus.GIVEN


def test_withdraw_consent():
    """Test withdrawing consent."""
    manager = ConsentManager()
    
    # Give consent first
    manager.give_consent("user123", ConsentType.MARKETING)
    
    # Withdraw consent
    success = manager.withdraw_consent("user123", ConsentType.MARKETING)
    
    assert success
    
    consent = manager.get_consent("user123", ConsentType.MARKETING)
    assert consent.status == ConsentStatus.WITHDRAWN


def test_has_consent():
    """Test checking consent."""
    manager = ConsentManager()
    
    # No consent initially
    assert not manager.has_consent("user123", ConsentType.PRIVACY_POLICY)
    
    # Give consent
    manager.give_consent("user123", ConsentType.PRIVACY_POLICY)
    
    # Should have consent now
    assert manager.has_consent("user123", ConsentType.PRIVACY_POLICY)


def test_get_consent_summary():
    """Test consent summary."""
    manager = ConsentManager()
    
    manager.give_consent("user123", ConsentType.TERMS_OF_SERVICE)
    manager.give_consent("user123", ConsentType.PRIVACY_POLICY)
    
    summary = manager.get_consent_summary("user123")
    
    assert summary["user_id"] == "user123"
    assert summary["total_consents"] == 2
    assert ConsentType.TERMS_OF_SERVICE.value in summary["consents"]


def test_require_consent():
    """Test requiring consent."""
    manager = ConsentManager()
    
    manager.give_consent("user123", ConsentType.TERMS_OF_SERVICE)
    
    required = manager.require_consent(
        "user123",
        [ConsentType.TERMS_OF_SERVICE, ConsentType.PRIVACY_POLICY],
    )
    
    assert required[ConsentType.TERMS_OF_SERVICE.value] is True
    assert required[ConsentType.PRIVACY_POLICY.value] is False


def test_consent_audit_trail():
    """Test consent audit trail."""
    manager = ConsentManager()
    
    # Give consent
    manager.give_consent("user123", ConsentType.MARKETING, version="1.0")
    
    # Withdraw consent
    manager.withdraw_consent("user123", ConsentType.MARKETING)
    
    # Give consent again
    manager.give_consent("user123", ConsentType.MARKETING, version="2.0")
    
    trail = manager.get_consent_audit_trail("user123", ConsentType.MARKETING)
    
    assert len(trail) == 2  # Two consent records


def test_consent_statistics():
    """Test consent statistics."""
    manager = ConsentManager()
    
    manager.give_consent("user1", ConsentType.TERMS_OF_SERVICE)
    manager.give_consent("user2", ConsentType.PRIVACY_POLICY)
    manager.give_consent("user3", ConsentType.MARKETING)
    manager.withdraw_consent("user3", ConsentType.MARKETING)
    
    stats = manager.get_statistics()
    
    assert stats["total_consents"] == 3
    assert stats["given_consents"] == 2
    assert stats["withdrawn_consents"] == 1


# Policy Management Tests

def test_policy_manager_initialization():
    """Test policy manager initialization."""
    manager = PolicyManager()
    
    assert len(manager.policies) > 0


def test_get_policy():
    """Test getting policy."""
    manager = PolicyManager()
    
    policy = manager.get_policy("privacy_policy")
    
    assert policy is not None
    assert policy.policy_type == "privacy_policy"
    assert len(policy.content) > 0


def test_get_latest_policies():
    """Test getting latest policies."""
    manager = PolicyManager()
    
    policies = manager.get_latest_policies()
    
    assert "privacy_policy" in policies
    assert "terms_of_service" in policies
    assert "cookie_policy" in policies


def test_list_policy_versions():
    """Test listing policy versions."""
    manager = PolicyManager()
    
    versions = manager.list_policy_versions("privacy_policy")
    
    assert len(versions) > 0
    assert versions[0].policy_type == "privacy_policy"


def test_get_policy_summary():
    """Test getting policy summary."""
    manager = PolicyManager()
    
    summary = manager.get_policy_summary("privacy_policy")
    
    assert summary is not None
    assert len(summary) > 0


def test_policy_content():
    """Test policy content."""
    manager = PolicyManager()
    
    privacy_policy = manager.get_policy("privacy_policy")
    terms = manager.get_policy("terms_of_service")
    cookies = manager.get_policy("cookie_policy")
    
    assert "GDPR" in privacy_policy.content
    assert "Terms of Service" in terms.content
    assert "Cookies" in cookies.content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
