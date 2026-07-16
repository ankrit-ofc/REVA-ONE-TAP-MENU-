import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("app.email")


def send_email(to: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    """
    Sends an email via SMTP using the configured SMTP_* settings.

    Dev fallback: when SMTP_HOST is empty, the message (including any links in the
    body) is written to the log instead of being sent, so flows like password reset
    are testable without a mail server. SMTP errors are caught and logged — they
    never propagate to the caller (so an API endpoint can't leak delivery details).
    """
    if not settings.SMTP_HOST:
        logger.info("EMAIL (dev, not sent) to=%s subject=%s", to, subject)
        # The structured logger redacts any "token=" in the body (a production
        # safety net). In dev there's no SMTP, so print the full message to stdout
        # — bypassing that filter — so the reset link is actually usable locally.
        print(
            f"\n----- DEV EMAIL (SMTP not configured) -----\n"
            f"To: {to}\nSubject: {subject}\n\n{text_body}\n"
            f"-------------------------------------------\n",
            flush=True,
        )
        return

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    try:
        # Port 465 = implicit SSL (connection is encrypted from the start);
        # any other port (e.g. 587) = plain connection upgraded via STARTTLS.
        if settings.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=10, context=context
            ) as server:
                if settings.SMTP_USERNAME:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls(context=context)
                if settings.SMTP_USERNAME:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)
    except Exception:  # noqa: BLE001 — never surface SMTP failures to the API
        logger.exception("Failed to send email to=%s subject=%s", to, subject)


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    """Builds and sends the password-reset email containing the tokenized link."""
    subject = "Reset your password"
    text_body = (
        "We received a request to reset your password.\n\n"
        f"Use the link below to set a new password:\n{reset_link}\n\n"
        "If you didn't request this, you can safely ignore this email. "
        "The link expires soon and can be used only once."
    )
    html_body = (
        "<p>We received a request to reset your password.</p>"
        f'<p><a href="{reset_link}">Click here to set a new password</a></p>'
        f"<p>Or paste this link into your browser:<br>{reset_link}</p>"
        "<p>If you didn't request this, you can safely ignore this email. "
        "The link expires soon and can be used only once.</p>"
    )
    send_email(to_email, subject, text_body, html_body)
