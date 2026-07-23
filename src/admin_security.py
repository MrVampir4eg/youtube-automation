"""Single-admin authentication, password recovery, and SMTP delivery."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Dict, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from database.models import Database


logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AdminSecurity:
    """Owns the one administrator account; plaintext passwords are never stored."""

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def validate_email(email: str) -> str:
        normalized = (email or "").strip().lower()
        if not EMAIL_RE.match(normalized) or len(normalized) > 254:
            raise ValueError("Вкажіть коректний email")
        return normalized

    @staticmethod
    def validate_password(password: str) -> None:
        if len(password or "") < 12:
            raise ValueError("Пароль повинен містити щонайменше 12 символів")
        checks = (
            any(char.islower() for char in password),
            any(char.isupper() for char in password),
            any(char.isdigit() for char in password),
        )
        if not all(checks):
            raise ValueError("Додайте до пароля великі й малі літери та цифру")

    @staticmethod
    def password_hash(password: str) -> str:
        AdminSecurity.validate_password(password)
        return generate_password_hash(password, method="scrypt")

    def bootstrap_from_environment(self) -> bool:
        """Create the only admin once from Render secrets."""
        if self.db.get_admin():
            return False
        email = os.getenv("ADMIN_EMAIL", "").strip()
        password = os.getenv("ADMIN_PASSWORD", "")
        if not email or not password:
            logger.warning(
                "Admin is not configured. Add ADMIN_EMAIL and ADMIN_PASSWORD."
            )
            return False
        normalized = self.validate_email(email)
        password_hash = self.password_hash(password)
        self.db.create_admin(normalized, password_hash)
        # Do not keep the bootstrap plaintext in the process environment longer
        # than necessary. Render retains its secret for disaster recovery.
        os.environ.pop("ADMIN_PASSWORD", None)
        logger.info("Administrator account created for %s", normalized)
        return True

    def authenticate(self, email: str, password: str) -> Optional[Dict]:
        admin = self.db.get_admin()
        if not admin:
            return None
        if not secrets.compare_digest(
            admin["email"], (email or "").strip().lower()
        ):
            # Run one expensive hash even for a wrong email to reduce timing clues.
            check_password_hash(admin["password_hash"], password or "")
            return None
        if not check_password_hash(admin["password_hash"], password or ""):
            return None
        self.db.update_admin_login()
        return self.db.get_admin()

    def change_password(self, current_password: str, new_password: str) -> None:
        admin = self.db.get_admin()
        if not admin or not check_password_hash(
            admin["password_hash"], current_password or ""
        ):
            raise ValueError("Поточний пароль неправильний")
        self.db.update_admin_password(self.password_hash(new_password))

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_reset_link(self, email: str, base_url: str) -> Optional[str]:
        """Return a link only when the submitted address is the admin address."""
        admin = self.db.get_admin()
        if not admin or not secrets.compare_digest(
            admin["email"], (email or "").strip().lower()
        ):
            return None
        token = secrets.token_urlsafe(40)
        expires = datetime.now(timezone.utc) + timedelta(minutes=30)
        self.db.create_password_reset_token(
            self._token_hash(token), expires.isoformat()
        )
        return f"{base_url.rstrip('/')}/reset-password/{token}"

    def validate_reset_token(self, token: str) -> bool:
        return bool(self.db.get_valid_password_reset(self._token_hash(token)))

    def reset_password(self, token: str, new_password: str) -> None:
        token_hash = self._token_hash(token)
        if not self.db.get_valid_password_reset(token_hash):
            raise ValueError("Посилання недійсне або вже прострочене")
        self.db.update_admin_password(self.password_hash(new_password))
        self.db.mark_password_reset_used(token_hash)

    @staticmethod
    def smtp_configured() -> bool:
        return bool(
            os.getenv("SMTP_HOST")
            and os.getenv("SMTP_USER")
            and os.getenv("SMTP_PASSWORD")
            and os.getenv("SMTP_FROM_EMAIL")
        )

    def send_reset_email(self, recipient: str, reset_link: str) -> None:
        if not self.smtp_configured():
            raise RuntimeError("Email-відновлення ще не налаштоване в Render")

        host = os.environ["SMTP_HOST"].strip()
        port = int(os.getenv("SMTP_PORT", "587"))
        user = os.environ["SMTP_USER"].strip()
        password = os.environ["SMTP_PASSWORD"]
        from_email = os.environ["SMTP_FROM_EMAIL"].strip()
        use_ssl = os.getenv("SMTP_USE_SSL", "False").lower() == "true" or port == 465

        message = EmailMessage()
        message["Subject"] = "Відновлення доступу до Reels Automation"
        message["From"] = from_email
        message["To"] = recipient
        message.set_content(
            "Хтось запросив зміну пароля адміністратора.\n\n"
            f"Посилання діє 30 хвилин:\n{reset_link}\n\n"
            "Якщо це були не ви — просто проігноруйте лист."
        )

        context = ssl.create_default_context()
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as server:
                server.login(user, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(user, password)
                server.send_message(message)
