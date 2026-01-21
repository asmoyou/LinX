"""Tests for Data Classification System."""

import pytest
from datetime import datetime
from uuid import uuid4

from shared.data_classification import (
    DataClassifier,
    ClassificationLevel,
    ClassificationRule,
    ClassificationResult,
    ClassificationMetadata,
    get_data_classifier,
    classify_text,
    classify_document,
)


def test_classification_level_ordering():
    """Test classification level ordering."""
    assert ClassificationLevel.PUBLIC < ClassificationLevel.INTERNAL
    assert ClassificationLevel.INTERNAL < ClassificationLevel.CONFIDENTIAL
    assert ClassificationLevel.CONFIDENTIAL < ClassificationLevel.RESTRICTED
    
    assert ClassificationLevel.PUBLIC <= ClassificationLevel.PUBLIC
    assert ClassificationLevel.INTERNAL <= ClassificationLevel.CONFIDENTIAL


def test_classification_level_properties():
    """Test classification level properties."""
    level = ClassificationLevel.CONFIDENTIAL
    
    assert level.description
    assert level.color
    assert level.value == "confidential"


def test_classification_rule_matches():
    """Test classification rule matching."""
    rule = ClassificationRule(
        name="Test Rule",
        level=ClassificationLevel.CONFIDENTIAL,
        patterns=[r'\b\d{3}-\d{2}-\d{4}\b'],
        keywords=["confidential", "secret"],
        min_matches=1,
    )
    
    # Should match pattern
    assert rule.matches("SSN: 123-45-6789")
    
    # Should match keyword
    assert rule.matches("This is confidential information")
    
    # Should not match
    assert not rule.matches("This is public information")


def test_classification_rule_case_sensitivity():
    """Test case sensitivity in rules."""
    rule = ClassificationRule(
        name="Case Sensitive",
        level=ClassificationLevel.INTERNAL,
        keywords=["SECRET"],
        case_sensitive=True,
    )
    
    assert rule.matches("This is SECRET")
    assert not rule.matches("This is secret")
    
    rule.case_sensitive = False
    assert rule.matches("This is secret")


def test_classification_rule_min_matches():
    """Test minimum matches requirement."""
    rule = ClassificationRule(
        name="Multiple Matches",
        level=ClassificationLevel.CONFIDENTIAL,
        keywords=["salary", "compensation", "bonus"],
        min_matches=2,
    )
    
    # Only one match
    assert not rule.matches("The salary is competitive")
    
    # Two matches
    assert rule.matches("The salary and compensation package")
    
    # Three matches
    assert rule.matches("Salary, compensation, and bonus information")


def test_data_classifier_initialization():
    """Test data classifier initialization."""
    classifier = DataClassifier()
    
    assert len(classifier.rules) > 0
    assert any(rule.name == "SSN" for rule in classifier.rules)
    assert any(rule.name == "Credit Card" for rule in classifier.rules)


def test_classify_ssn():
    """Test classification of SSN."""
    classifier = DataClassifier()
    
    result = classifier.classify("My SSN is 123-45-6789")
    
    assert result.level == ClassificationLevel.RESTRICTED
    assert result.confidence > 0
    assert "SSN" in result.matched_rules


def test_classify_credit_card():
    """Test classification of credit card."""
    classifier = DataClassifier()
    
    result = classifier.classify("Card number: 4532-1234-5678-9010")
    
    assert result.level == ClassificationLevel.RESTRICTED
    assert "Credit Card" in result.matched_rules


def test_classify_api_key():
    """Test classification of API key."""
    classifier = DataClassifier()
    
    result = classifier.classify("api_key = 'sk-1234567890abcdefghijklmnop'")
    
    assert result.level == ClassificationLevel.RESTRICTED
    assert "API Keys" in result.matched_rules


def test_classify_financial_data():
    """Test classification of financial data."""
    classifier = DataClassifier()
    
    result = classifier.classify("The company revenue was $10M with profit margins of 25%")
    
    assert result.level == ClassificationLevel.CONFIDENTIAL
    assert "Financial Data" in result.matched_rules


def test_classify_personal_information():
    """Test classification of personal information."""
    classifier = DataClassifier()
    
    result = classifier.classify(
        "Contact: john.doe@example.com, phone: 555-123-4567, "
        "date of birth: 01/01/1990"
    )
    
    assert result.level == ClassificationLevel.CONFIDENTIAL


def test_classify_internal_data():
    """Test classification of internal data."""
    classifier = DataClassifier()
    
    result = classifier.classify("Internal team meeting notes for the engineering department")
    
    assert result.level == ClassificationLevel.INTERNAL


def test_classify_empty_text():
    """Test classification of empty text."""
    classifier = DataClassifier()
    
    result = classifier.classify("")
    
    assert result.level == ClassificationLevel.PUBLIC
    assert result.confidence == 1.0


def test_classify_no_matches():
    """Test classification when no rules match."""
    classifier = DataClassifier()
    
    result = classifier.classify("The weather is nice today")
    
    assert result.level == ClassificationLevel.INTERNAL  # Default
    assert result.confidence == 0.5


def test_classify_multiple_rules():
    """Test classification with multiple matching rules."""
    classifier = DataClassifier()
    
    text = (
        "Confidential financial report: "
        "Employee salary: $100,000, "
        "SSN: 123-45-6789, "
        "Credit card: 4532-1234-5678-9010"
    )
    
    result = classifier.classify(text)
    
    # Should use highest classification level
    assert result.level == ClassificationLevel.RESTRICTED
    assert len(result.matched_rules) > 1


def test_add_custom_rule():
    """Test adding custom classification rule."""
    classifier = DataClassifier()
    
    custom_rule = ClassificationRule(
        name="Custom Rule",
        level=ClassificationLevel.CONFIDENTIAL,
        keywords=["custom", "test"],
        min_matches=1,
    )
    
    classifier.add_rule(custom_rule)
    
    result = classifier.classify("This is a custom test")
    
    assert "Custom Rule" in result.matched_rules


def test_remove_rule():
    """Test removing classification rule."""
    classifier = DataClassifier()
    
    initial_count = len(classifier.rules)
    
    # Remove a rule
    removed = classifier.remove_rule("SSN")
    
    assert removed
    assert len(classifier.rules) == initial_count - 1
    
    # Try to remove non-existent rule
    removed = classifier.remove_rule("NonExistent")
    assert not removed


def test_classify_document():
    """Test document classification."""
    classifier = DataClassifier()
    
    result = classifier.classify_document(
        content="This document contains confidential salary information",
        filename="salaries_2024.pdf",
        metadata={"department": "HR"},
    )
    
    assert result.level == ClassificationLevel.CONFIDENTIAL
    assert result.metadata["filename"] == "salaries_2024.pdf"
    assert result.metadata["content_length"] > 0


def test_get_routing_rules_public():
    """Test routing rules for public data."""
    classifier = DataClassifier()
    
    rules = classifier.get_routing_rules(ClassificationLevel.PUBLIC)
    
    assert rules["allow_cloud_llm"] is True
    assert rules["allow_external_storage"] is True
    assert rules["allow_sharing"] is True


def test_get_routing_rules_restricted():
    """Test routing rules for restricted data."""
    classifier = DataClassifier()
    
    rules = classifier.get_routing_rules(ClassificationLevel.RESTRICTED)
    
    assert rules["allow_cloud_llm"] is False
    assert rules["allow_external_storage"] is False
    assert rules["require_encryption"] is True
    assert rules["require_audit_log"] is True
    assert rules["allow_sharing"] is False


def test_should_use_local_llm():
    """Test LLM routing decision."""
    classifier = DataClassifier()
    
    # Public data can use cloud LLM
    assert not classifier.should_use_local_llm(ClassificationLevel.PUBLIC)
    
    # All other levels must use local LLM
    assert classifier.should_use_local_llm(ClassificationLevel.INTERNAL)
    assert classifier.should_use_local_llm(ClassificationLevel.CONFIDENTIAL)
    assert classifier.should_use_local_llm(ClassificationLevel.RESTRICTED)


def test_classification_result_to_dict():
    """Test classification result serialization."""
    result = ClassificationResult(
        level=ClassificationLevel.CONFIDENTIAL,
        confidence=0.8,
        matched_rules=["Rule1", "Rule2"],
        reasons=["Reason1", "Reason2"],
    )
    
    data = result.to_dict()
    
    assert data["level"] == "confidential"
    assert data["confidence"] == 0.8
    assert len(data["matched_rules"]) == 2
    assert "timestamp" in data


def test_classification_metadata():
    """Test classification metadata."""
    metadata = ClassificationMetadata(
        classification=ClassificationLevel.CONFIDENTIAL,
        classified_at=datetime.utcnow(),
        classified_by="automatic",
        confidence=0.9,
        review_required=True,
    )
    
    # Test serialization
    data = metadata.to_dict()
    assert data["classification"] == "confidential"
    assert data["confidence"] == 0.9
    assert data["review_required"] is True
    
    # Test deserialization
    restored = ClassificationMetadata.from_dict(data)
    assert restored.classification == ClassificationLevel.CONFIDENTIAL
    assert restored.confidence == 0.9


def test_get_data_classifier_singleton():
    """Test global classifier singleton."""
    classifier1 = get_data_classifier()
    classifier2 = get_data_classifier()
    
    assert classifier1 is classifier2


def test_classify_text_helper():
    """Test classify_text helper function."""
    result = classify_text("SSN: 123-45-6789")
    
    assert result.level == ClassificationLevel.RESTRICTED


def test_classify_document_helper():
    """Test classify_document helper function."""
    result = classify_document(
        content="Confidential information",
        filename="test.txt",
    )
    
    assert result.level == ClassificationLevel.CONFIDENTIAL
    assert result.metadata["filename"] == "test.txt"
