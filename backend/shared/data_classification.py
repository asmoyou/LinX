"""Data Classification System.

Implements automatic data classification based on content analysis.

References:
- Requirements 7: Data Security and Privacy
- Design Section 8.4: Data Protection
- Task 5.2: Data Classification
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any
from uuid import UUID

logger = logging.getLogger(__name__)


class ClassificationLevel(Enum):
    """Data classification levels."""
    
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    
    def __lt__(self, other):
        """Compare classification levels for ordering."""
        if not isinstance(other, ClassificationLevel):
            return NotImplemented
        
        order = {
            ClassificationLevel.PUBLIC: 0,
            ClassificationLevel.INTERNAL: 1,
            ClassificationLevel.CONFIDENTIAL: 2,
            ClassificationLevel.RESTRICTED: 3,
        }
        return order[self] < order[other]
    
    def __le__(self, other):
        """Compare classification levels for ordering."""
        return self < other or self == other
    
    @property
    def description(self) -> str:
        """Get description of classification level."""
        descriptions = {
            ClassificationLevel.PUBLIC: "Public information, no restrictions",
            ClassificationLevel.INTERNAL: "Internal use only, not for external distribution",
            ClassificationLevel.CONFIDENTIAL: "Confidential information, restricted access",
            ClassificationLevel.RESTRICTED: "Highly restricted, requires special authorization",
        }
        return descriptions[self]
    
    @property
    def color(self) -> str:
        """Get color code for UI display."""
        colors = {
            ClassificationLevel.PUBLIC: "#4CAF50",  # Green
            ClassificationLevel.INTERNAL: "#2196F3",  # Blue
            ClassificationLevel.CONFIDENTIAL: "#FF9800",  # Orange
            ClassificationLevel.RESTRICTED: "#F44336",  # Red
        }
        return colors[self]


@dataclass
class ClassificationRule:
    """Rule for automatic classification."""
    
    name: str
    level: ClassificationLevel
    patterns: List[str]
    keywords: List[str] = field(default_factory=list)
    min_matches: int = 1
    case_sensitive: bool = False
    enabled: bool = True
    
    def matches(self, text: str) -> bool:
        """Check if text matches this rule.
        
        Args:
            text: Text to check
        
        Returns:
            True if text matches rule
        """
        if not self.enabled:
            return False
        
        flags = 0 if self.case_sensitive else re.IGNORECASE
        match_count = 0
        
        # Check patterns
        for pattern in self.patterns:
            if re.search(pattern, text, flags):
                match_count += 1
        
        # Check keywords
        for keyword in self.keywords:
            if self.case_sensitive:
                if keyword in text:
                    match_count += 1
            else:
                if keyword.lower() in text.lower():
                    match_count += 1
        
        return match_count >= self.min_matches


@dataclass
class ClassificationResult:
    """Result of data classification."""
    
    level: ClassificationLevel
    confidence: float
    matched_rules: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage.
        
        Returns:
            Dictionary representation
        """
        return {
            "level": self.level.value,
            "confidence": self.confidence,
            "matched_rules": self.matched_rules,
            "reasons": self.reasons,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class DataClassifier:
    """Automatic data classification engine."""
    
    def __init__(self):
        """Initialize data classifier with default rules."""
        self.rules: List[ClassificationRule] = []
        self._load_default_rules()
        
        logger.info("DataClassifier initialized with %d rules", len(self.rules))
    
    def _load_default_rules(self):
        """Load default classification rules."""
        # Restricted data patterns
        self.rules.append(ClassificationRule(
            name="SSN",
            level=ClassificationLevel.RESTRICTED,
            patterns=[
                r'\b\d{3}-\d{2}-\d{4}\b',  # SSN format
                r'\b\d{9}\b',  # SSN without dashes
            ],
            keywords=["social security", "ssn"],
        ))
        
        self.rules.append(ClassificationRule(
            name="Credit Card",
            level=ClassificationLevel.RESTRICTED,
            patterns=[
                r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',  # Credit card
            ],
            keywords=["credit card", "card number", "cvv"],
        ))
        
        self.rules.append(ClassificationRule(
            name="API Keys",
            level=ClassificationLevel.RESTRICTED,
            patterns=[
                r'api[_-]?key[\s:=]+["\']?[\w-]{20,}["\']?',
                r'secret[_-]?key[\s:=]+["\']?[\w-]{20,}["\']?',
                r'password[\s:=]+["\']?[\w-]{8,}["\']?',
            ],
            keywords=["api key", "secret key", "access token"],
        ))
        
        self.rules.append(ClassificationRule(
            name="Personal Health Information",
            level=ClassificationLevel.RESTRICTED,
            keywords=[
                "medical record", "diagnosis", "prescription",
                "patient", "health condition", "treatment",
            ],
            min_matches=2,
        ))
        
        # Confidential data patterns
        self.rules.append(ClassificationRule(
            name="Financial Data",
            level=ClassificationLevel.CONFIDENTIAL,
            keywords=[
                "salary", "compensation", "revenue", "profit",
                "financial statement", "budget", "invoice",
            ],
            min_matches=1,
        ))
        
        self.rules.append(ClassificationRule(
            name="Personal Information",
            level=ClassificationLevel.CONFIDENTIAL,
            patterns=[
                r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
                r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # Phone number
            ],
            keywords=[
                "date of birth", "address", "phone number",
                "email address", "personal data",
            ],
            min_matches=2,
        ))
        
        self.rules.append(ClassificationRule(
            name="Business Confidential",
            level=ClassificationLevel.CONFIDENTIAL,
            keywords=[
                "confidential", "proprietary", "trade secret",
                "internal only", "do not distribute",
                "strategic plan", "merger", "acquisition",
            ],
            min_matches=1,
        ))
        
        # Internal data patterns
        self.rules.append(ClassificationRule(
            name="Internal Communications",
            level=ClassificationLevel.INTERNAL,
            keywords=[
                "internal", "team", "department", "employee",
                "staff", "meeting notes", "draft",
            ],
            min_matches=2,
        ))
        
        self.rules.append(ClassificationRule(
            name="Technical Documentation",
            level=ClassificationLevel.INTERNAL,
            keywords=[
                "architecture", "design document", "implementation",
                "technical spec", "api documentation",
            ],
            min_matches=1,
        ))
    
    def add_rule(self, rule: ClassificationRule) -> None:
        """Add a custom classification rule.
        
        Args:
            rule: Classification rule to add
        """
        self.rules.append(rule)
        logger.info("Added classification rule: %s", rule.name)
    
    def remove_rule(self, rule_name: str) -> bool:
        """Remove a classification rule.
        
        Args:
            rule_name: Name of rule to remove
        
        Returns:
            True if rule was removed
        """
        initial_count = len(self.rules)
        self.rules = [r for r in self.rules if r.name != rule_name]
        
        if len(self.rules) < initial_count:
            logger.info("Removed classification rule: %s", rule_name)
            return True
        
        return False
    
    def classify(
        self,
        text: str,
        default_level: ClassificationLevel = ClassificationLevel.INTERNAL,
    ) -> ClassificationResult:
        """Classify text based on content analysis.
        
        Args:
            text: Text to classify
            default_level: Default classification if no rules match
        
        Returns:
            Classification result
        """
        if not text:
            return ClassificationResult(
                level=ClassificationLevel.PUBLIC,
                confidence=1.0,
                reasons=["Empty content"],
            )
        
        matched_rules: List[ClassificationRule] = []
        
        # Check all rules
        for rule in self.rules:
            if rule.matches(text):
                matched_rules.append(rule)
        
        if not matched_rules:
            # No rules matched, use default
            return ClassificationResult(
                level=default_level,
                confidence=0.5,
                reasons=["No classification rules matched, using default"],
            )
        
        # Use highest classification level from matched rules
        highest_level = max(rule.level for rule in matched_rules)
        
        # Calculate confidence based on number of matches
        confidence = min(1.0, len(matched_rules) * 0.3 + 0.4)
        
        result = ClassificationResult(
            level=highest_level,
            confidence=confidence,
            matched_rules=[rule.name for rule in matched_rules],
            reasons=[
                f"Matched rule '{rule.name}' ({rule.level.value})"
                for rule in matched_rules
            ],
        )
        
        logger.debug(
            "Classified text as %s (confidence: %.2f)",
            result.level.value,
            result.confidence,
        )
        
        return result
    
    def classify_document(
        self,
        content: str,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """Classify a document.
        
        Args:
            content: Document content
            filename: Optional filename
            metadata: Optional metadata
        
        Returns:
            Classification result
        """
        # Combine content with filename and metadata for classification
        text_to_classify = content
        
        if filename:
            text_to_classify = f"{filename}\n{text_to_classify}"
        
        if metadata:
            metadata_text = " ".join(str(v) for v in metadata.values())
            text_to_classify = f"{metadata_text}\n{text_to_classify}"
        
        result = self.classify(text_to_classify)
        
        # Add document-specific metadata
        result.metadata["filename"] = filename
        result.metadata["content_length"] = len(content)
        
        return result
    
    def get_routing_rules(
        self,
        classification: ClassificationLevel,
    ) -> Dict[str, bool]:
        """Get routing rules for classified data.
        
        Args:
            classification: Classification level
        
        Returns:
            Dictionary of routing rules
        """
        rules = {
            "allow_cloud_llm": False,
            "allow_external_storage": False,
            "require_encryption": False,
            "require_audit_log": False,
            "allow_sharing": False,
        }
        
        if classification == ClassificationLevel.PUBLIC:
            rules["allow_cloud_llm"] = True
            rules["allow_external_storage"] = True
            rules["allow_sharing"] = True
        
        elif classification == ClassificationLevel.INTERNAL:
            rules["allow_cloud_llm"] = False
            rules["allow_external_storage"] = False
            rules["require_encryption"] = True
            rules["require_audit_log"] = True
            rules["allow_sharing"] = True
        
        elif classification == ClassificationLevel.CONFIDENTIAL:
            rules["allow_cloud_llm"] = False
            rules["allow_external_storage"] = False
            rules["require_encryption"] = True
            rules["require_audit_log"] = True
            rules["allow_sharing"] = False
        
        elif classification == ClassificationLevel.RESTRICTED:
            rules["allow_cloud_llm"] = False
            rules["allow_external_storage"] = False
            rules["require_encryption"] = True
            rules["require_audit_log"] = True
            rules["allow_sharing"] = False
        
        return rules
    
    def should_use_local_llm(self, classification: ClassificationLevel) -> bool:
        """Determine if local LLM should be used for classified data.
        
        Args:
            classification: Classification level
        
        Returns:
            True if local LLM should be used
        """
        # Only PUBLIC data can use cloud LLM
        return classification != ClassificationLevel.PUBLIC


@dataclass
class ClassificationMetadata:
    """Metadata for classified data."""
    
    classification: ClassificationLevel
    classified_at: datetime
    classified_by: str  # "automatic" or user_id
    confidence: float
    review_required: bool = False
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[UUID] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage.
        
        Returns:
            Dictionary representation
        """
        return {
            "classification": self.classification.value,
            "classified_at": self.classified_at.isoformat(),
            "classified_by": self.classified_by,
            "confidence": self.confidence,
            "review_required": self.review_required,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewed_by": str(self.reviewed_by) if self.reviewed_by else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClassificationMetadata":
        """Create from dictionary.
        
        Args:
            data: Dictionary data
        
        Returns:
            ClassificationMetadata instance
        """
        return cls(
            classification=ClassificationLevel(data["classification"]),
            classified_at=datetime.fromisoformat(data["classified_at"]),
            classified_by=data["classified_by"],
            confidence=data["confidence"],
            review_required=data.get("review_required", False),
            reviewed_at=datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else None,
            reviewed_by=UUID(data["reviewed_by"]) if data.get("reviewed_by") else None,
        )


# Global classifier instance
_classifier_instance: Optional[DataClassifier] = None


def get_data_classifier() -> DataClassifier:
    """Get global data classifier instance.
    
    Returns:
        DataClassifier instance
    """
    global _classifier_instance
    
    if _classifier_instance is None:
        _classifier_instance = DataClassifier()
    
    return _classifier_instance


def classify_text(text: str) -> ClassificationResult:
    """Classify text using global classifier.
    
    Args:
        text: Text to classify
    
    Returns:
        Classification result
    """
    classifier = get_data_classifier()
    return classifier.classify(text)


def classify_document(
    content: str,
    filename: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ClassificationResult:
    """Classify document using global classifier.
    
    Args:
        content: Document content
        filename: Optional filename
        metadata: Optional metadata
    
    Returns:
        Classification result
    """
    classifier = get_data_classifier()
    return classifier.classify_document(content, filename, metadata)
