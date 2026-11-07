import os
import subprocess
import sys
import unittest


class PasswordConfigurationTests(unittest.TestCase):
    def run_with(self, password, allow_pin):
        env = os.environ.copy()
        env.update({
            "ADMIN_PASSWORD": password,
            "SECRET_KEY": "test-secret-key-is-at-least-thirty-two-characters",
            "ALLOW_INSECURE_PIN": allow_pin,
        })
        return subprocess.run(
            [sys.executable, "-c", "import app.config"],
            env=env, capture_output=True, text=True,
        )

    def test_strong_password_does_not_require_opt_in(self):
        self.assertEqual(self.run_with("strong-enough-password", "false").returncode, 0)

    def test_pin_requires_explicit_opt_in(self):
        self.assertNotEqual(self.run_with("123456", "false").returncode, 0)
        self.assertEqual(self.run_with("123456", "true").returncode, 0)

    def test_short_non_pin_is_rejected(self):
        for password in ("12345", "1234567", "abcdef", "１２３４５６"):
            with self.subTest(password=password):
                self.assertNotEqual(self.run_with(password, "true").returncode, 0)
