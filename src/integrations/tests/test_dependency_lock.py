"""Static checks: image deps come from uv.lock, not ad-hoc pip installs."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class LockedDependencyInstallTests(unittest.TestCase):
    """Prove DRF and Pillow are declared in the lock and Docker uses it."""

    def test_pyproject_declares_drf_and_pillow13(self):
        """Project dependencies pin DRF stack and Pillow 13."""
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('djangorestframework~=3.18.2', text)
        self.assertIn('drf-spectacular~=0.28.0', text)
        self.assertIn('pillow~=13.0.0', text)

    def test_uv_lock_pins_drf_and_pillow13(self):
        """uv.lock resolves DRF and Pillow 13 for the image sync."""
        text = (ROOT / "uv.lock").read_text(encoding="utf-8")
        self.assertRegex(
            text,
            r'name = "djangorestframework"\nversion = "3\.18\.\d+"',
        )
        self.assertRegex(
            text,
            r'name = "drf-spectacular"\nversion = "0\.28\.\d+"',
        )
        self.assertRegex(
            text,
            r'name = "pillow"\nversion = "13\.0\.\d+"',
        )

    def test_dockerfile_uses_locked_sync_without_extra_pip_install(self):
        """Runtime image installs only via uv sync --locked (no DRF pip add-on)."""
        text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("uv sync --locked --no-binary-package pillow", text)
        self.assertNotIn("uv pip install", text)
        # Explicitly reject the old unlocked DRF install pattern.
        self.assertNotIn("djangorestframework~=", text)
        self.assertNotIn("drf-spectacular~=", text)

    def test_requirements_txt_is_absent(self):
        """Stale requirements.txt is not a supported install path."""
        self.assertFalse(
            (ROOT / "requirements.txt").exists(),
            "requirements.txt must stay removed; use uv.lock / uv sync --locked",
        )
