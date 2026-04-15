import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings


class EmailService:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def send_email(self, *, to_email: str, subject: str, text_body: str, html_body: str | None = None) -> None:
        if not settings.EMAILS_ENABLED:
            self.logger.info("Email delivery disabled; skipping email to %s with subject %s", to_email, subject)
            return

        message = EmailMessage()
        message["From"] = settings.EMAIL_FROM
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(text_body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        if settings.SMTP_USE_SSL:
            smtp_client = smtplib.SMTP_SSL(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=settings.REDIS_SOCKET_TIMEOUT,
            )
        else:
            smtp_client = smtplib.SMTP(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=settings.REDIS_SOCKET_TIMEOUT,
            )

        with smtp_client as server:
            if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
                server.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(message)

    def send_verification_email(self, *, to_email: str, full_name: str, verification_token: str) -> None:
        verification_link = f"{settings.FRONTEND_URL.rstrip('/')}/verify-email?token={verification_token}"
        text_body = (
            f"Hi {full_name},\n\n"
            "Verify your MooveSaathi account using the link below:\n"
            f"{verification_link}\n\n"
            "If you did not create this account, you can ignore this email."
        )
        html_body = (
            f"<p>Hi {full_name},</p>"
            "<p>Verify your MooveSaathi account using the link below:</p>"
            f"<p><a href=\"{verification_link}\">Verify email</a></p>"
            "<p>If you did not create this account, you can ignore this email.</p>"
        )
        self.send_email(
            to_email=to_email,
            subject="Verify your MooveSaathi account",
            text_body=text_body,
            html_body=html_body,
        )
