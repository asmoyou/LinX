"""Data anonymization for analytics.

References:
- Requirements 7: Data Privacy and Security
- GDPR Article 4(5): Pseudonymisation
"""

import logging
import hashlib
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AnonymizationRule:
    """Anonymization rule."""
    
    field_name: str
    method: str  # hash, mask, generalize, suppress
    description: str


class DataAnonymizer:
    """Data anonymizer.
    
    Anonymizes sensitive data for analytics:
    - Hash: Replace with hash value
    - Mask: Replace with masked value (e.g., ****)
    - Generalize: Replace with generalized value (e.g., age range)
    - Suppress: Remove entirely
    """
    
    def __init__(self, salt: str = "linx_anonymization_salt"):
        """Initialize data anonymizer.
        
        Args:
            salt: Salt for hashing
        """
        self.salt = salt
        self.rules: Dict[str, AnonymizationRule] = {}
        
        # Initialize default rules
        self._initialize_default_rules()
        
        logger.info("DataAnonymizer initialized")
    
    def _initialize_default_rules(self):
        """Initialize default anonymization rules."""
        # User identifiers
        self.rules["user_id"] = AnonymizationRule(
            field_name="user_id",
            method="hash",
            description="Hash user ID for analytics",
        )
        
        self.rules["email"] = AnonymizationRule(
            field_name="email",
            method="hash",
            description="Hash email address",
        )
        
        self.rules["name"] = AnonymizationRule(
            field_name="name",
            method="suppress",
            description="Remove user name",
        )
        
        # IP addresses
        self.rules["ip_address"] = AnonymizationRule(
            field_name="ip_address",
            method="mask",
            description="Mask last octet of IP address",
        )
        
        # Age
        self.rules["age"] = AnonymizationRule(
            field_name="age",
            method="generalize",
            description="Generalize age to range",
        )
        
        # Location
        self.rules["location"] = AnonymizationRule(
            field_name="location",
            method="generalize",
            description="Generalize to city/country only",
        )
    
    def add_rule(self, rule: AnonymizationRule):
        """Add anonymization rule.
        
        Args:
            rule: Anonymization rule
        """
        self.rules[rule.field_name] = rule
        logger.info(f"Added anonymization rule: {rule.field_name}")
    
    def anonymize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Anonymize data dictionary.
        
        Args:
            data: Data to anonymize
            
        Returns:
            Anonymized data
        """
        anonymized = data.copy()
        
        for field_name, value in data.items():
            if field_name in self.rules:
                rule = self.rules[field_name]
                anonymized[field_name] = self._apply_rule(value, rule)
        
        return anonymized
    
    def anonymize_batch(self, data_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Anonymize batch of data.
        
        Args:
            data_list: List of data dictionaries
            
        Returns:
            List of anonymized data
        """
        return [self.anonymize(data) for data in data_list]
    
    def _apply_rule(self, value: Any, rule: AnonymizationRule) -> Any:
        """Apply anonymization rule to value.
        
        Args:
            value: Value to anonymize
            rule: Anonymization rule
            
        Returns:
            Anonymized value
        """
        if value is None:
            return None
        
        if rule.method == "hash":
            return self._hash_value(str(value))
        
        elif rule.method == "mask":
            return self._mask_value(str(value), rule.field_name)
        
        elif rule.method == "generalize":
            return self._generalize_value(value, rule.field_name)
        
        elif rule.method == "suppress":
            return None
        
        else:
            logger.warning(f"Unknown anonymization method: {rule.method}")
            return value
    
    def _hash_value(self, value: str) -> str:
        """Hash value with salt.
        
        Args:
            value: Value to hash
            
        Returns:
            Hashed value
        """
        salted = f"{value}{self.salt}"
        return hashlib.sha256(salted.encode()).hexdigest()[:16]
    
    def _mask_value(self, value: str, field_name: str) -> str:
        """Mask value.
        
        Args:
            value: Value to mask
            field_name: Field name
            
        Returns:
            Masked value
        """
        if field_name == "ip_address":
            # Mask last octet: 192.168.1.100 -> 192.168.1.***
            parts = value.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.***"
        
        elif field_name == "email":
            # Mask email: user@example.com -> u***@example.com
            if "@" in value:
                local, domain = value.split("@", 1)
                return f"{local[0]}***@{domain}"
        
        # Default masking
        if len(value) > 4:
            return value[:2] + "***" + value[-2:]
        return "***"
    
    def _generalize_value(self, value: Any, field_name: str) -> str:
        """Generalize value.
        
        Args:
            value: Value to generalize
            field_name: Field name
            
        Returns:
            Generalized value
        """
        if field_name == "age":
            # Generalize age to range
            age = int(value)
            if age < 18:
                return "<18"
            elif age < 25:
                return "18-24"
            elif age < 35:
                return "25-34"
            elif age < 45:
                return "35-44"
            elif age < 55:
                return "45-54"
            elif age < 65:
                return "55-64"
            else:
                return "65+"
        
        elif field_name == "location":
            # Generalize location to city/country
            # Assume format: "Street, City, State, Country"
            parts = str(value).split(",")
            if len(parts) >= 2:
                return f"{parts[-2].strip()}, {parts[-1].strip()}"
            return str(value)
        
        return str(value)
    
    def anonymize_for_analytics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Anonymize data specifically for analytics.
        
        Args:
            data: Data to anonymize
            
        Returns:
            Anonymized data suitable for analytics
        """
        # Keep useful fields for analytics, anonymize sensitive ones
        anonymized = self.anonymize(data)
        
        # Add anonymization metadata
        anonymized["_anonymized"] = True
        anonymized["_anonymized_at"] = datetime.now().isoformat()
        
        return anonymized
    
    def get_anonymization_report(self) -> Dict[str, Any]:
        """Get anonymization configuration report.
        
        Returns:
            Report dictionary
        """
        return {
            "total_rules": len(self.rules),
            "rules": {
                field_name: {
                    "method": rule.method,
                    "description": rule.description,
                }
                for field_name, rule in self.rules.items()
            },
        }


# Import datetime for anonymization metadata
from datetime import datetime
