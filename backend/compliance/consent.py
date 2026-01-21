"""Consent management.

References:
- Requirements 7: Data Privacy and Security
- GDPR Article 7: Conditions for consent
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ConsentType(Enum):
    """Types of consent."""
    
    TERMS_OF_SERVICE = "terms_of_service"
    PRIVACY_POLICY = "privacy_policy"
    MARKETING = "marketing"
    DATA_PROCESSING = "data_processing"
    COOKIES = "cookies"
    THIRD_PARTY_SHARING = "third_party_sharing"


class ConsentStatus(Enum):
    """Consent status."""
    
    GIVEN = "given"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


@dataclass
class ConsentRecord:
    """Consent record."""
    
    consent_id: str
    user_id: str
    consent_type: ConsentType
    status: ConsentStatus
    given_at: datetime
    withdrawn_at: Optional[datetime] = None
    version: str = "1.0"
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class ConsentManager:
    """Consent manager.
    
    Manages user consent:
    - Record consent given
    - Record consent withdrawn
    - Check consent status
    - Consent versioning
    - Consent audit trail
    """
    
    def __init__(self):
        """Initialize consent manager."""
        self.consents: List[ConsentRecord] = []
        
        logger.info("ConsentManager initialized")
    
    def give_consent(
        self,
        user_id: str,
        consent_type: ConsentType,
        version: str = "1.0",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> ConsentRecord:
        """Record consent given.
        
        Args:
            user_id: User ID
            consent_type: Type of consent
            version: Policy version
            ip_address: User IP address
            user_agent: User agent string
            
        Returns:
            Consent record
        """
        consent_id = f"consent_{user_id}_{consent_type.value}_{int(datetime.now().timestamp())}"
        
        # Check if consent already exists
        existing = self.get_consent(user_id, consent_type)
        if existing and existing.status == ConsentStatus.GIVEN:
            logger.info(f"Consent already given: {user_id} - {consent_type.value}")
            return existing
        
        record = ConsentRecord(
            consent_id=consent_id,
            user_id=user_id,
            consent_type=consent_type,
            status=ConsentStatus.GIVEN,
            given_at=datetime.now(),
            version=version,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        
        self.consents.append(record)
        
        logger.info(
            f"Consent given: {user_id} - {consent_type.value}",
            extra={
                "consent_id": consent_id,
                "version": version,
            },
        )
        
        return record
    
    def withdraw_consent(
        self,
        user_id: str,
        consent_type: ConsentType,
    ) -> bool:
        """Record consent withdrawn.
        
        Args:
            user_id: User ID
            consent_type: Type of consent
            
        Returns:
            True if withdrawn
        """
        consent = self.get_consent(user_id, consent_type)
        
        if not consent:
            logger.warning(f"No consent found to withdraw: {user_id} - {consent_type.value}")
            return False
        
        if consent.status == ConsentStatus.WITHDRAWN:
            logger.info(f"Consent already withdrawn: {user_id} - {consent_type.value}")
            return True
        
        consent.status = ConsentStatus.WITHDRAWN
        consent.withdrawn_at = datetime.now()
        
        logger.warning(
            f"Consent withdrawn: {user_id} - {consent_type.value}",
            extra={"consent_id": consent.consent_id},
        )
        
        return True
    
    def get_consent(
        self,
        user_id: str,
        consent_type: ConsentType,
    ) -> Optional[ConsentRecord]:
        """Get consent record.
        
        Args:
            user_id: User ID
            consent_type: Type of consent
            
        Returns:
            Consent record or None
        """
        # Get most recent consent
        user_consents = [
            c for c in self.consents
            if c.user_id == user_id and c.consent_type == consent_type
        ]
        
        if not user_consents:
            return None
        
        # Return most recent
        return max(user_consents, key=lambda c: c.given_at)
    
    def has_consent(
        self,
        user_id: str,
        consent_type: ConsentType,
    ) -> bool:
        """Check if user has given consent.
        
        Args:
            user_id: User ID
            consent_type: Type of consent
            
        Returns:
            True if consent given
        """
        consent = self.get_consent(user_id, consent_type)
        return consent is not None and consent.status == ConsentStatus.GIVEN
    
    def get_user_consents(self, user_id: str) -> List[ConsentRecord]:
        """Get all consents for user.
        
        Args:
            user_id: User ID
            
        Returns:
            List of consent records
        """
        return [c for c in self.consents if c.user_id == user_id]
    
    def get_consent_summary(self, user_id: str) -> Dict[str, Any]:
        """Get consent summary for user.
        
        Args:
            user_id: User ID
            
        Returns:
            Consent summary
        """
        user_consents = self.get_user_consents(user_id)
        
        summary = {
            "user_id": user_id,
            "total_consents": len(user_consents),
            "consents": {},
        }
        
        for consent_type in ConsentType:
            consent = self.get_consent(user_id, consent_type)
            if consent:
                summary["consents"][consent_type.value] = {
                    "status": consent.status.value,
                    "given_at": consent.given_at.isoformat(),
                    "withdrawn_at": (
                        consent.withdrawn_at.isoformat()
                        if consent.withdrawn_at
                        else None
                    ),
                    "version": consent.version,
                }
            else:
                summary["consents"][consent_type.value] = {
                    "status": "not_given",
                }
        
        return summary
    
    def require_consent(
        self,
        user_id: str,
        consent_types: List[ConsentType],
    ) -> Dict[str, bool]:
        """Check if user has required consents.
        
        Args:
            user_id: User ID
            consent_types: Required consent types
            
        Returns:
            Dictionary of consent type to has_consent
        """
        return {
            consent_type.value: self.has_consent(user_id, consent_type)
            for consent_type in consent_types
        }
    
    def get_consent_audit_trail(
        self,
        user_id: str,
        consent_type: Optional[ConsentType] = None,
    ) -> List[ConsentRecord]:
        """Get consent audit trail for user.
        
        Args:
            user_id: User ID
            consent_type: Filter by consent type (optional)
            
        Returns:
            List of consent records (all versions)
        """
        consents = [c for c in self.consents if c.user_id == user_id]
        
        if consent_type:
            consents = [c for c in consents if c.consent_type == consent_type]
        
        # Sort by given_at
        consents.sort(key=lambda c: c.given_at)
        
        return consents
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get consent statistics.
        
        Returns:
            Statistics dictionary
        """
        total_consents = len(self.consents)
        given_consents = sum(1 for c in self.consents if c.status == ConsentStatus.GIVEN)
        withdrawn_consents = sum(1 for c in self.consents if c.status == ConsentStatus.WITHDRAWN)
        
        by_type = {}
        for consent_type in ConsentType:
            type_consents = [c for c in self.consents if c.consent_type == consent_type]
            by_type[consent_type.value] = {
                "total": len(type_consents),
                "given": sum(1 for c in type_consents if c.status == ConsentStatus.GIVEN),
                "withdrawn": sum(1 for c in type_consents if c.status == ConsentStatus.WITHDRAWN),
            }
        
        return {
            "total_consents": total_consents,
            "given_consents": given_consents,
            "withdrawn_consents": withdrawn_consents,
            "by_type": by_type,
        }
