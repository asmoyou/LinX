"""Privacy policy and terms of service management.

References:
- Requirements 7: Data Privacy and Security
- GDPR Article 13: Information to be provided
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PolicyDocument:
    """Policy document."""
    
    policy_id: str
    policy_type: str  # privacy_policy, terms_of_service, cookie_policy, etc.
    version: str
    effective_date: datetime
    content: str
    summary: str
    language: str = "en"


class PolicyManager:
    """Policy manager.
    
    Manages legal policies:
    - Privacy policy
    - Terms of service
    - Cookie policy
    - Data processing agreements
    - Policy versioning
    """
    
    def __init__(self):
        """Initialize policy manager."""
        self.policies: List[PolicyDocument] = []
        
        # Initialize default policies
        self._initialize_default_policies()
        
        logger.info("PolicyManager initialized")
    
    def _initialize_default_policies(self):
        """Initialize default policy documents."""
        # Privacy Policy
        self.add_policy(PolicyDocument(
            policy_id="privacy_policy_v1",
            policy_type="privacy_policy",
            version="1.0",
            effective_date=datetime(2024, 1, 1),
            content=self._get_privacy_policy_content(),
            summary="This privacy policy explains how we collect, use, and protect your personal data.",
            language="en",
        ))
        
        # Terms of Service
        self.add_policy(PolicyDocument(
            policy_id="terms_of_service_v1",
            policy_type="terms_of_service",
            version="1.0",
            effective_date=datetime(2024, 1, 1),
            content=self._get_terms_of_service_content(),
            summary="These terms govern your use of our digital workforce platform.",
            language="en",
        ))
        
        # Cookie Policy
        self.add_policy(PolicyDocument(
            policy_id="cookie_policy_v1",
            policy_type="cookie_policy",
            version="1.0",
            effective_date=datetime(2024, 1, 1),
            content=self._get_cookie_policy_content(),
            summary="This policy explains how we use cookies and similar technologies.",
            language="en",
        ))
    
    def add_policy(self, policy: PolicyDocument):
        """Add policy document.
        
        Args:
            policy: Policy document
        """
        self.policies.append(policy)
        
        logger.info(
            f"Added policy: {policy.policy_type} v{policy.version}",
            extra={"policy_id": policy.policy_id},
        )
    
    def get_policy(
        self,
        policy_type: str,
        version: Optional[str] = None,
        language: str = "en",
    ) -> Optional[PolicyDocument]:
        """Get policy document.
        
        Args:
            policy_type: Policy type
            version: Policy version (latest if not specified)
            language: Language code
            
        Returns:
            Policy document or None
        """
        # Filter by type and language
        matching = [
            p for p in self.policies
            if p.policy_type == policy_type and p.language == language
        ]
        
        if not matching:
            return None
        
        # Filter by version if specified
        if version:
            matching = [p for p in matching if p.version == version]
            return matching[0] if matching else None
        
        # Return latest version
        return max(matching, key=lambda p: p.effective_date)
    
    def get_latest_policies(self, language: str = "en") -> Dict[str, PolicyDocument]:
        """Get latest version of all policies.
        
        Args:
            language: Language code
            
        Returns:
            Dictionary of policy type to policy document
        """
        policy_types = set(p.policy_type for p in self.policies)
        
        return {
            policy_type: self.get_policy(policy_type, language=language)
            for policy_type in policy_types
        }
    
    def list_policy_versions(
        self,
        policy_type: str,
        language: str = "en",
    ) -> List[PolicyDocument]:
        """List all versions of a policy.
        
        Args:
            policy_type: Policy type
            language: Language code
            
        Returns:
            List of policy documents
        """
        policies = [
            p for p in self.policies
            if p.policy_type == policy_type and p.language == language
        ]
        
        # Sort by effective date
        policies.sort(key=lambda p: p.effective_date, reverse=True)
        
        return policies
    
    def get_policy_summary(
        self,
        policy_type: str,
        language: str = "en",
    ) -> Optional[str]:
        """Get policy summary.
        
        Args:
            policy_type: Policy type
            language: Language code
            
        Returns:
            Policy summary or None
        """
        policy = self.get_policy(policy_type, language=language)
        return policy.summary if policy else None
    
    # Default policy content
    
    def _get_privacy_policy_content(self) -> str:
        """Get privacy policy content."""
        return """
# Privacy Policy

**Effective Date: January 1, 2024**

## 1. Introduction

LinX Digital Workforce Platform ("we", "our", or "us") is committed to protecting your privacy. This Privacy Policy explains how we collect, use, disclose, and safeguard your information.

## 2. Information We Collect

### 2.1 Personal Information
- Name and contact information
- Account credentials
- Payment information
- Usage data and preferences

### 2.2 Automatically Collected Information
- IP address and device information
- Browser type and version
- Usage patterns and analytics

## 3. How We Use Your Information

We use your information to:
- Provide and maintain our services
- Process your transactions
- Send you updates and notifications
- Improve our platform
- Comply with legal obligations

## 4. Data Sharing and Disclosure

We do not sell your personal information. We may share your information with:
- Service providers who assist our operations
- Legal authorities when required by law
- Business partners with your consent

## 5. Your Rights (GDPR)

You have the right to:
- Access your personal data
- Rectify inaccurate data
- Request erasure of your data
- Object to data processing
- Data portability
- Withdraw consent

## 6. Data Security

We implement appropriate technical and organizational measures to protect your data, including:
- Encryption at rest and in transit
- Access controls and authentication
- Regular security audits
- Incident response procedures

## 7. Data Retention

We retain your data only as long as necessary for the purposes outlined in this policy or as required by law.

## 8. International Data Transfers

Your data may be transferred to and processed in countries other than your own. We ensure appropriate safeguards are in place.

## 9. Children's Privacy

Our services are not intended for children under 16. We do not knowingly collect data from children.

## 10. Changes to This Policy

We may update this policy from time to time. We will notify you of significant changes.

## 11. Contact Us

For privacy-related questions, contact us at: privacy@linx-platform.com
"""
    
    def _get_terms_of_service_content(self) -> str:
        """Get terms of service content."""
        return """
# Terms of Service

**Effective Date: January 1, 2024**

## 1. Acceptance of Terms

By accessing or using LinX Digital Workforce Platform, you agree to be bound by these Terms of Service.

## 2. Description of Service

LinX provides an AI-powered digital workforce management platform for creating, managing, and coordinating AI agents.

## 3. User Accounts

### 3.1 Account Creation
- You must provide accurate information
- You are responsible for account security
- You must be at least 18 years old

### 3.2 Account Termination
- You may terminate your account at any time
- We may suspend or terminate accounts for violations

## 4. Acceptable Use

You agree not to:
- Violate any laws or regulations
- Infringe on intellectual property rights
- Transmit malicious code or content
- Attempt to gain unauthorized access
- Use the service for illegal purposes

## 5. Intellectual Property

### 5.1 Our Rights
- We retain all rights to the platform
- Our trademarks and logos are protected

### 5.2 Your Content
- You retain rights to your content
- You grant us license to use your content to provide services

## 6. Payment Terms

- Fees are charged according to your subscription plan
- Payments are non-refundable except as required by law
- We may change pricing with notice

## 7. Limitation of Liability

To the maximum extent permitted by law, we are not liable for:
- Indirect or consequential damages
- Loss of data or profits
- Service interruptions

## 8. Indemnification

You agree to indemnify us against claims arising from your use of the service.

## 9. Dispute Resolution

Disputes will be resolved through binding arbitration in accordance with applicable law.

## 10. Changes to Terms

We may modify these terms at any time. Continued use constitutes acceptance of changes.

## 11. Contact

For questions about these terms, contact: legal@linx-platform.com
"""
    
    def _get_cookie_policy_content(self) -> str:
        """Get cookie policy content."""
        return """
# Cookie Policy

**Effective Date: January 1, 2024**

## 1. What Are Cookies

Cookies are small text files stored on your device when you visit our website.

## 2. Types of Cookies We Use

### 2.1 Essential Cookies
Required for the platform to function properly.

### 2.2 Analytics Cookies
Help us understand how users interact with our platform.

### 2.3 Preference Cookies
Remember your settings and preferences.

## 3. Third-Party Cookies

We may use third-party services that set cookies:
- Analytics providers
- Authentication services
- Content delivery networks

## 4. Managing Cookies

You can control cookies through your browser settings. Note that disabling cookies may affect functionality.

## 5. Updates

We may update this policy. Check back regularly for changes.

## 6. Contact

For questions about cookies, contact: privacy@linx-platform.com
"""
