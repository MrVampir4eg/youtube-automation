import importlib
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class DashboardAuthenticationTests(unittest.TestCase):
    def test_dashboard_csrf_and_bot_bearer_token(self):
        with tempfile.TemporaryDirectory() as directory:
            variables = {
                "DATABASE_PATH": str(Path(directory) / "dashboard.db"),
                "ADMIN_EMAIL": "owner@example.com",
                "ADMIN_PASSWORD": "InitialStrong123",
                "SECRET_KEY": "unit-test-session-secret",
                "AUTOMATION_API_TOKEN": "unit-test-bot-token",
                "USE_FREE_MODE": "True",
                "ENABLE_MARKET_TRENDS": "False",
                "ENABLE_INTERNAL_SCHEDULER": "False",
                "VIDEOS_PER_DAY": "0",
                "RENDER": "False",
            }
            with patch.dict(os.environ, variables, clear=False), patch(
                "src.scheduler.AutomationScheduler.start"
            ):
                sys.modules.pop("dashboard.app", None)
                module = importlib.import_module("dashboard.app")
                module.app.config.update(TESTING=True)
                client = module.app.test_client()

                protected = client.get("/")
                self.assertEqual(protected.status_code, 302)
                self.assertIn("/login", protected.headers["Location"])

                login_page = client.get("/login")
                csrf = re.search(
                    rb'name="csrf_token" value="([^"]+)"', login_page.data
                ).group(1).decode()
                logged_in = client.post(
                    "/login",
                    data={
                        "csrf_token": csrf,
                        "email": "owner@example.com",
                        "password": "InitialStrong123",
                    },
                )
                self.assertEqual(logged_in.status_code, 302)
                self.assertEqual(client.get("/").status_code, 200)
                self.assertEqual(client.get("/admin/security").status_code, 200)

                without_csrf = client.post(
                    "/api/channel-profiles", json={"name": "Second channel"}
                )
                self.assertEqual(without_csrf.status_code, 403)

                with client.session_transaction() as session:
                    csrf = session["csrf_token"]
                with_csrf = client.post(
                    "/api/channel-profiles",
                    json={"name": "Second channel"},
                    headers={"X-CSRF-Token": csrf},
                )
                self.assertEqual(with_csrf.status_code, 201)

                bot_client = module.app.test_client()
                unauthenticated = bot_client.get("/api/bot/status")
                self.assertEqual(unauthenticated.status_code, 401)
                bot_status = bot_client.get(
                    "/api/bot/status",
                    headers={"Authorization": "Bearer unit-test-bot-token"},
                )
                self.assertEqual(bot_status.status_code, 200)
                self.assertTrue(bot_status.get_json()["official_api_only"])

                module.db.close()
                module.scheduler.db.close()
                module.producer.db.close()


if __name__ == "__main__":
    unittest.main()
