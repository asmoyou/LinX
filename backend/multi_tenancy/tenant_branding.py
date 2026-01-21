"""Tenant-specific branding.

References:
- Requirements 14: Access Control and Security
- Design Section 18: User Interface
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class BrandColors:
    """Brand color scheme."""
    
    primary: str = "#3B82F6"  # Blue
    secondary: str = "#8B5CF6"  # Purple
    accent: str = "#10B981"  # Green
    background: str = "#FFFFFF"  # White
    text: str = "#1F2937"  # Dark gray
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary."""
        return {
            "primary": self.primary,
            "secondary": self.secondary,
            "accent": self.accent,
            "background": self.background,
            "text": self.text,
        }


@dataclass
class BrandAssets:
    """Brand assets."""
    
    logo_url: Optional[str] = None
    logo_dark_url: Optional[str] = None
    favicon_url: Optional[str] = None
    background_image_url: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Optional[str]]:
        """Convert to dictionary."""
        return {
            "logo_url": self.logo_url,
            "logo_dark_url": self.logo_dark_url,
            "favicon_url": self.favicon_url,
            "background_image_url": self.background_image_url,
        }


@dataclass
class TenantBrandConfig:
    """Tenant branding configuration."""
    
    tenant_id: UUID
    
    # Company information
    company_name: str
    tagline: Optional[str] = None
    
    # Colors
    colors: BrandColors = field(default_factory=BrandColors)
    
    # Assets
    assets: BrandAssets = field(default_factory=BrandAssets)
    
    # Custom CSS
    custom_css: Optional[str] = None
    
    # Email branding
    email_from_name: Optional[str] = None
    email_footer: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tenant_id": str(self.tenant_id),
            "company_name": self.company_name,
            "tagline": self.tagline,
            "colors": self.colors.to_dict(),
            "assets": self.assets.to_dict(),
            "custom_css": self.custom_css,
            "email_from_name": self.email_from_name,
            "email_footer": self.email_footer,
            "metadata": self.metadata,
        }


class TenantBranding:
    """Tenant branding management.
    
    Manages tenant-specific branding:
    - Brand colors and themes
    - Logo and assets
    - Custom CSS
    - Email branding
    """
    
    def __init__(self, database=None):
        """Initialize tenant branding.
        
        Args:
            database: Database connection
        """
        self.database = database
        self.branding: Dict[UUID, TenantBrandConfig] = {}
        
        logger.info("TenantBranding initialized")
    
    def get_branding(self, tenant_id: UUID) -> Optional[TenantBrandConfig]:
        """Get branding for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            TenantBrandConfig or None
        """
        return self.branding.get(tenant_id)
    
    def set_branding(self, config: TenantBrandConfig):
        """Set branding for a tenant.
        
        Args:
            config: Branding configuration
        """
        self.branding[config.tenant_id] = config
        logger.info(f"Set branding for tenant: {config.tenant_id}")
    
    def update_colors(
        self,
        tenant_id: UUID,
        colors: BrandColors,
    ) -> Optional[TenantBrandConfig]:
        """Update brand colors.
        
        Args:
            tenant_id: Tenant ID
            colors: New colors
            
        Returns:
            Updated config or None
        """
        config = self.get_branding(tenant_id)
        if not config:
            logger.warning(f"Branding not found for tenant: {tenant_id}")
            return None
        
        config.colors = colors
        logger.info(f"Updated colors for tenant: {tenant_id}")
        return config
    
    def update_assets(
        self,
        tenant_id: UUID,
        assets: BrandAssets,
    ) -> Optional[TenantBrandConfig]:
        """Update brand assets.
        
        Args:
            tenant_id: Tenant ID
            assets: New assets
            
        Returns:
            Updated config or None
        """
        config = self.get_branding(tenant_id)
        if not config:
            logger.warning(f"Branding not found for tenant: {tenant_id}")
            return None
        
        config.assets = assets
        logger.info(f"Updated assets for tenant: {tenant_id}")
        return config
    
    def update_custom_css(
        self,
        tenant_id: UUID,
        custom_css: str,
    ) -> Optional[TenantBrandConfig]:
        """Update custom CSS.
        
        Args:
            tenant_id: Tenant ID
            custom_css: Custom CSS
            
        Returns:
            Updated config or None
        """
        config = self.get_branding(tenant_id)
        if not config:
            logger.warning(f"Branding not found for tenant: {tenant_id}")
            return None
        
        # Validate CSS (basic check)
        if not self._validate_css(custom_css):
            logger.warning(f"Invalid CSS for tenant: {tenant_id}")
            return None
        
        config.custom_css = custom_css
        logger.info(f"Updated custom CSS for tenant: {tenant_id}")
        return config
    
    def update_email_branding(
        self,
        tenant_id: UUID,
        from_name: Optional[str] = None,
        footer: Optional[str] = None,
    ) -> Optional[TenantBrandConfig]:
        """Update email branding.
        
        Args:
            tenant_id: Tenant ID
            from_name: Email from name
            footer: Email footer
            
        Returns:
            Updated config or None
        """
        config = self.get_branding(tenant_id)
        if not config:
            logger.warning(f"Branding not found for tenant: {tenant_id}")
            return None
        
        if from_name:
            config.email_from_name = from_name
        
        if footer:
            config.email_footer = footer
        
        logger.info(f"Updated email branding for tenant: {tenant_id}")
        return config
    
    def generate_theme_css(self, tenant_id: UUID) -> str:
        """Generate CSS theme for tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            CSS string
        """
        config = self.get_branding(tenant_id)
        if not config:
            return ""
        
        colors = config.colors
        
        css = f"""
        :root {{
            --color-primary: {colors.primary};
            --color-secondary: {colors.secondary};
            --color-accent: {colors.accent};
            --color-background: {colors.background};
            --color-text: {colors.text};
        }}
        
        .btn-primary {{
            background-color: var(--color-primary);
            color: white;
        }}
        
        .btn-secondary {{
            background-color: var(--color-secondary);
            color: white;
        }}
        
        .text-primary {{
            color: var(--color-primary);
        }}
        
        .bg-primary {{
            background-color: var(--color-primary);
        }}
        """
        
        # Add custom CSS if provided
        if config.custom_css:
            css += f"\n\n/* Custom CSS */\n{config.custom_css}"
        
        return css
    
    def _validate_css(self, css: str) -> bool:
        """Validate CSS (basic check).
        
        Args:
            css: CSS string
            
        Returns:
            True if valid
        """
        # Basic validation - check for dangerous patterns
        dangerous_patterns = [
            "javascript:",
            "expression(",
            "import",
            "@import",
            "behavior:",
        ]
        
        css_lower = css.lower()
        for pattern in dangerous_patterns:
            if pattern in css_lower:
                logger.warning(f"Dangerous pattern found in CSS: {pattern}")
                return False
        
        return True
    
    def get_email_template(
        self,
        tenant_id: UUID,
        template_type: str,
    ) -> Dict[str, str]:
        """Get branded email template.
        
        Args:
            tenant_id: Tenant ID
            template_type: Template type (welcome, notification, etc.)
            
        Returns:
            Dictionary with template parts
        """
        config = self.get_branding(tenant_id)
        if not config:
            return {}
        
        from_name = config.email_from_name or config.company_name
        footer = config.email_footer or f"© {config.company_name}"
        
        return {
            "from_name": from_name,
            "footer": footer,
            "primary_color": config.colors.primary,
            "logo_url": config.assets.logo_url or "",
        }
