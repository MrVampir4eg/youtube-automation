import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.models import Database
from src.admin_security import AdminSecurity


class AdminSecurityTests(unittest.TestCase):
    def test_bootstrap_auth_change_and_one_time_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(str(Path(directory) / "security.db"))
            security = AdminSecurity(database)
            variables = {
                "ADMIN_EMAIL": "Owner@Example.com",
                "ADMIN_PASSWORD": "InitialStrong123",
            }
            with patch.dict(os.environ, variables, clear=False):
                self.assertTrue(security.bootstrap_from_environment())

            admin = database.get_admin()
            self.assertEqual(admin["email"], "owner@example.com")
            self.assertNotEqual(admin["password_hash"], "InitialStrong123")
            self.assertIsNotNone(
                security.authenticate("owner@example.com", "InitialStrong123")
            )

            security.change_password("InitialStrong123", "ChangedStrong456")
            self.assertIsNone(
                security.authenticate("owner@example.com", "InitialStrong123")
            )
            self.assertIsNotNone(
                security.authenticate("owner@example.com", "ChangedStrong456")
            )

            link = security.create_reset_link(
                "owner@example.com", "https://dashboard.example"
            )
            token = link.rsplit("/", 1)[-1]
            self.assertTrue(security.validate_reset_token(token))
            security.reset_password(token, "RecoveredStrong789")
            self.assertFalse(security.validate_reset_token(token))
            self.assertIsNotNone(
                security.authenticate("owner@example.com", "RecoveredStrong789")
            )
            database.close()

    def test_reset_does_not_reveal_unknown_email(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(str(Path(directory) / "security.db"))
            security = AdminSecurity(database)
            database.create_admin(
                "owner@example.com", security.password_hash("InitialStrong123")
            )
            self.assertIsNone(
                security.create_reset_link(
                    "stranger@example.com", "https://dashboard.example"
                )
            )
            database.close()

    def test_password_policy_rejects_weak_password(self):
        with self.assertRaises(ValueError):
            AdminSecurity.validate_password("short")
        with self.assertRaises(ValueError):
            AdminSecurity.validate_password("alllowercase123")


if __name__ == "__main__":
    unittest.main()
