"""Tests for platform detection and sandbox selection.

This module tests the automatic platform detection and sandbox selection logic.
"""

import platform
import unittest
from unittest.mock import MagicMock, patch

from virtualization.sandbox_selector import (
    PlatformType,
    SandboxSelector,
    SandboxType,
    get_sandbox_selector,
)


class TestPlatformDetection(unittest.TestCase):
    """Test platform detection functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.selector = SandboxSelector()

    def test_platform_detection(self):
        """Test that platform is detected correctly."""
        detected_platform = self.selector._platform
        self.assertIn(
            detected_platform,
            [
                PlatformType.LINUX.value,
                PlatformType.MACOS.value,
                PlatformType.WINDOWS.value,
                "Unknown",
            ],
        )

    def test_platform_info(self):
        """Test that platform info is collected."""
        info = self.selector._platform_details
        self.assertIn("system", info)
        self.assertIn("release", info)
        self.assertIn("version", info)
        self.assertIn("machine", info)
        self.assertIn("processor", info)
        self.assertIn("python_version", info)

    @patch("platform.system")
    def test_linux_detection(self, mock_system):
        """Test Linux platform detection."""
        mock_system.return_value = "Linux"
        selector = SandboxSelector()
        self.assertEqual(selector._platform, PlatformType.LINUX.value)

    @patch("platform.system")
    def test_macos_detection(self, mock_system):
        """Test macOS platform detection."""
        mock_system.return_value = "Darwin"
        selector = SandboxSelector()
        self.assertEqual(selector._platform, PlatformType.MACOS.value)

    @patch("platform.system")
    def test_windows_detection(self, mock_system):
        """Test Windows platform detection."""
        mock_system.return_value = "Windows"
        selector = SandboxSelector()
        self.assertEqual(selector._platform, PlatformType.WINDOWS.value)

    @patch("platform.system")
    def test_unknown_platform_detection(self, mock_system):
        """Test unknown platform detection."""
        mock_system.return_value = "FreeBSD"
        selector = SandboxSelector()
        self.assertEqual(selector._platform, "Unknown")


class TestSandboxSelection(unittest.TestCase):
    """Test sandbox selection logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.selector = SandboxSelector()

    def test_sandbox_detection(self):
        """Test that a sandbox is detected."""
        sandbox = self.selector.detect_best_sandbox()
        self.assertIsInstance(sandbox, SandboxType)

    def test_sandbox_config(self):
        """Test that sandbox config is returned."""
        config = self.selector.get_sandbox_config()
        self.assertIn("runtime", config)
        self.assertIn("security_level", config)
        self.assertIn("overhead", config)
        self.assertIn("platform", config)
        self.assertIn("features", config)

    @patch("platform.system")
    @patch("virtualization.sandbox_selector.SandboxSelector._is_gvisor_available")
    def test_gvisor_selection_on_linux(self, mock_gvisor, mock_system):
        """Test gVisor selection on Linux when available."""
        mock_system.return_value = "Linux"
        mock_gvisor.return_value = True

        selector = SandboxSelector()
        sandbox = selector.detect_best_sandbox()

        self.assertEqual(sandbox, SandboxType.GVISOR)

    @patch("platform.system")
    @patch("virtualization.sandbox_selector.SandboxSelector._is_gvisor_available")
    @patch("virtualization.sandbox_selector.SandboxSelector._is_firecracker_available")
    def test_firecracker_selection_on_linux(self, mock_firecracker, mock_gvisor, mock_system):
        """Test Firecracker selection on Linux when gVisor not available."""
        mock_system.return_value = "Linux"
        mock_gvisor.return_value = False
        mock_firecracker.return_value = True

        selector = SandboxSelector()
        sandbox = selector.detect_best_sandbox()

        self.assertEqual(sandbox, SandboxType.FIRECRACKER)

    @patch("platform.system")
    @patch("virtualization.sandbox_selector.SandboxSelector._is_gvisor_available")
    @patch("virtualization.sandbox_selector.SandboxSelector._is_firecracker_available")
    def test_docker_fallback_on_linux(self, mock_firecracker, mock_gvisor, mock_system):
        """Test Docker Enhanced fallback on Linux."""
        mock_system.return_value = "Linux"
        mock_gvisor.return_value = False
        mock_firecracker.return_value = False

        selector = SandboxSelector()
        sandbox = selector.detect_best_sandbox()

        self.assertEqual(sandbox, SandboxType.DOCKER_ENHANCED)

    @patch("platform.system")
    def test_docker_on_macos(self, mock_system):
        """Test Docker Enhanced on macOS."""
        mock_system.return_value = "Darwin"

        selector = SandboxSelector()
        sandbox = selector.detect_best_sandbox()

        self.assertEqual(sandbox, SandboxType.DOCKER_ENHANCED)

    @patch("platform.system")
    def test_docker_on_windows(self, mock_system):
        """Test Docker Enhanced on Windows."""
        mock_system.return_value = "Windows"

        selector = SandboxSelector()
        sandbox = selector.detect_best_sandbox()

        self.assertEqual(sandbox, SandboxType.DOCKER_ENHANCED)


class TestSandboxValidation(unittest.TestCase):
    """Test sandbox validation logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.selector = SandboxSelector()

    def test_docker_validation_always_passes(self):
        """Test that Docker Enhanced validation always passes."""
        result = self.selector.validate_sandbox_requirements(SandboxType.DOCKER_ENHANCED)
        self.assertTrue(result)

    @patch("platform.system")
    @patch("virtualization.sandbox_selector.SandboxSelector._is_gvisor_available")
    def test_gvisor_validation_on_linux(self, mock_gvisor, mock_system):
        """Test gVisor validation on Linux."""
        mock_system.return_value = "Linux"
        mock_gvisor.return_value = True

        selector = SandboxSelector()
        result = selector.validate_sandbox_requirements(SandboxType.GVISOR)

        self.assertTrue(result)

    @patch("platform.system")
    def test_gvisor_validation_on_macos(self, mock_system):
        """Test gVisor validation fails on macOS."""
        mock_system.return_value = "Darwin"

        selector = SandboxSelector()
        result = selector.validate_sandbox_requirements(SandboxType.GVISOR)

        self.assertFalse(result)


class TestSecurityWarnings(unittest.TestCase):
    """Test security warning generation."""

    @patch("platform.system")
    def test_linux_security_warning(self, mock_system):
        """Test security warning on Linux."""
        mock_system.return_value = "Linux"

        selector = SandboxSelector()
        warning = selector._get_security_warning()

        self.assertIn("gVisor", warning)
        self.assertIn("Firecracker", warning)

    @patch("platform.system")
    def test_macos_security_warning(self, mock_system):
        """Test security warning on macOS."""
        mock_system.return_value = "Darwin"

        selector = SandboxSelector()
        warning = selector._get_security_warning()

        self.assertIn("macOS", warning)
        self.assertIn("not available", warning)

    @patch("platform.system")
    def test_windows_security_warning(self, mock_system):
        """Test security warning on Windows."""
        mock_system.return_value = "Windows"

        selector = SandboxSelector()
        warning = selector._get_security_warning()

        self.assertIn("Windows", warning)
        self.assertIn("not available", warning)


class TestGlobalSelector(unittest.TestCase):
    """Test global selector instance."""

    def test_get_sandbox_selector(self):
        """Test that global selector is returned."""
        selector1 = get_sandbox_selector()
        selector2 = get_sandbox_selector()

        # Should return same instance
        self.assertIs(selector1, selector2)

    def test_selector_is_sandbox_selector(self):
        """Test that global selector is SandboxSelector instance."""
        selector = get_sandbox_selector()
        self.assertIsInstance(selector, SandboxSelector)


if __name__ == "__main__":
    unittest.main()
