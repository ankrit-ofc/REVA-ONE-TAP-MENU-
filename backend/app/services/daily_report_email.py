"""
Rendering and delivery for the Nightly One-Liner.

The design requirement is comprehension in three seconds, which drives two
choices that are easy to undo by accident:

- The SUBJECT carries the headline, so the report is readable from a phone
  lock screen without opening anything:
      "Deja Brew — Rs 42,300 today, up 14% vs your usual Tuesday"
- The BODY is one card with five lines and nothing else. No charts, no metric
  tables. Every addition costs the owner a second of scanning, so additions
  need to justify themselves against that budget.

Transport mirrors receipt_email._dispatch (Resend over httpx, dev fallback when
the key is unset, recipient redacted in logs). That ~30 lines is duplicated on
purpose rather than extracted into a shared mailer: the original sits on the
payment path, and refactoring it to serve a reporting feature would put billing
at risk for no functional gain.

Unlike receipts, a summary is safe to retry and useless if silently dropped, so
`send_report` RAISES on failure and the caller (jobs.nightly_report) records the
attempt in the ledger. Never call this from a request path without catching.
"""

import logging
import uuid
from decimal import Decimal

import httpx

from app.core.config import settings
from app.services.customer_service import redact_email
from app.services.daily_report_service import Comparison, DailyReport

logger = logging.getLogger("app.daily_report")

# Currency codes we have a short human label for. Anything else falls back to
# the ISO code, which is correct if less pretty ("EUR 1,240").
_CURRENCY_LABELS = {"NPR": "Rs", "INR": "Rs", "USD": "$", "GBP": "£", "EUR": "€"}

_POSITIVE = "#0f7b3f"
_NEGATIVE = "#b3261e"
_MUTED = "#6b6b6b"
_INK = "#1a1a1a"


def _currency(code: str) -> str:
    return _CURRENCY_LABELS.get(code.upper(), code.upper())


def _money(value: Decimal, code: str) -> str:
    """Whole units only — decimals cost scanning time and add nothing here."""
    return f"{_currency(code)} {value:,.0f}"


def _esc(value: object) -> str:
    """Escape user-controlled text (restaurant and product names) for HTML."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _hour_label(hour: int) -> str:
    suffix = "AM" if hour < 12 else "PM"
    h = hour % 12 or 12
    return f"{h} {suffix}"


def _hour_range(start: int, end: int) -> str:
    start_suffix = "AM" if start < 12 else "PM"
    end_suffix = "AM" if end < 12 else "PM"
    if start_suffix == end_suffix:
        return f"{start % 12 or 12}–{end % 12 or 12} {end_suffix}"
    return f"{_hour_label(start)}–{_hour_label(end)}"


# ── Comparison phrasing ───────────────────────────────────────────────────────

def _comparison_words(cmp: Comparison, weekday: str) -> str | None:
    """Plain-text phrasing, or None when we have no honest comparison to make."""
    if cmp.pct is None:
        return None
    rounded = round(cmp.pct)
    if rounded == 0:
        return f"about the same as your usual {weekday}"
    direction = "up" if rounded > 0 else "down"
    return f"{direction} {abs(rounded)}% vs your usual {weekday}"


def _comparison_html(cmp: Comparison, weekday: str) -> str:
    """Compact arrow form for the card. Empty string renders nothing at all —
    an absent baseline must never appear as "0%"."""
    if cmp.pct is None:
        return (
            f"<div style='font-size:13px;color:{_MUTED};margin-top:2px'>"
            f"not enough history yet for a usual {_esc(weekday)}</div>"
        )
    rounded = round(cmp.pct)
    if rounded == 0:
        return (
            f"<div style='font-size:13px;color:{_MUTED};margin-top:2px'>"
            f"about the same as your usual {_esc(weekday)}</div>"
        )
    color = _POSITIVE if rounded > 0 else _NEGATIVE
    arrow = "&#8593;" if rounded > 0 else "&#8595;"
    return (
        f"<div style='font-size:13px;color:{color};margin-top:2px'>"
        f"{arrow}{abs(rounded)}% vs your usual {_esc(weekday)}</div>"
    )


def _subject(report: DailyReport) -> str:
    headline = f"{report.restaurant_name} — {_money(report.revenue, report.currency)} today"
    words = _comparison_words(report.revenue_cmp, report.weekday_label)
    return f"{headline}, {words}" if words else headline


# ── Bodies ────────────────────────────────────────────────────────────────────

def _render_text(report: DailyReport) -> str:
    cur = report.currency
    lines = [
        f"{report.restaurant_name} — {report.local_date:%A %d %b %Y}",
        "",
        f"Revenue today: {_money(report.revenue, cur)}",
    ]
    words = _comparison_words(report.revenue_cmp, report.weekday_label)
    if words:
        lines.append(f"  ({words})")

    lines.append(f"Orders: {report.orders}")
    words = _comparison_words(report.orders_cmp, report.weekday_label)
    if words:
        lines.append(f"  ({words})")

    lines.append(f"Average order: {_money(report.aov, cur)}")
    words = _comparison_words(report.aov_cmp, report.weekday_label)
    if words:
        lines.append(f"  ({words})")

    lines.append("")
    if report.best_seller_name:
        lines.append(f"Best seller: {report.best_seller_name} ({report.best_seller_qty} sold)")
    if report.quiet:
        lines.append(
            f"Quietest stretch: {_hour_range(report.quiet.start_hour, report.quiet.end_hour)} "
            f"({_money(report.quiet.revenue, cur)})"
        )
    lines += [
        "",
        f"Worth a look: about {report.browsed_no_order} table"
        f"{'' if report.browsed_no_order == 1 else 's'} scanned the menu but "
        f"didn't order.",
        "",
        "You're receiving this because the daily report is switched on for this "
        "restaurant. Turn it off any time in Settings.",
    ]
    return "\n".join(lines)


def _stat_cell(label: str, value: str, comparison_html: str) -> str:
    return (
        f"<td width='50%' valign='top' style='padding:0 8px 0 0'>"
        f"<div style='font-size:12px;color:{_MUTED};text-transform:uppercase;"
        f"letter-spacing:.04em'>{_esc(label)}</div>"
        f"<div style='font-size:22px;font-weight:700;color:{_INK};margin-top:4px'>"
        f"{_esc(value)}</div>"
        f"{comparison_html}</td>"
    )


def _render_html(report: DailyReport) -> str:
    cur = report.currency
    weekday = report.weekday_label

    footnotes = []
    if report.best_seller_name:
        footnotes.append(
            f"<tr><td style='padding:10px 0;border-top:1px solid #ececec'>"
            f"<span style='font-size:12px;color:{_MUTED}'>Best seller</span><br>"
            f"<span style='font-size:15px;color:{_INK}'>"
            f"{_esc(report.best_seller_name)} &middot; {report.best_seller_qty} sold"
            f"</span></td></tr>"
        )
    if report.quiet:
        footnotes.append(
            f"<tr><td style='padding:10px 0;border-top:1px solid #ececec'>"
            f"<span style='font-size:12px;color:{_MUTED}'>Quietest stretch</span><br>"
            f"<span style='font-size:15px;color:{_INK}'>"
            f"{_esc(_hour_range(report.quiet.start_hour, report.quiet.end_hour))} "
            f"&middot; {_esc(_money(report.quiet.revenue, cur))}</span></td></tr>"
        )

    # "~" and "about" are deliberate: this figure is an approximation with a
    # known downward bias (see daily_report_service._browsed_without_ordering).
    tables_word = "table" if report.browsed_no_order == 1 else "tables"
    worth_a_look = (
        f"<tr><td style='padding:10px 0;border-top:1px solid #ececec'>"
        f"<span style='font-size:12px;color:{_MUTED}'>Worth a look</span><br>"
        f"<span style='font-size:15px;color:{_INK}'>"
        f"~{report.browsed_no_order} {tables_word} scanned the menu but didn't order"
        f"</span></td></tr>"
    )

    return (
        f"<div style='margin:0;padding:16px;background:#f4f4f5;"
        f"font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",Roboto,sans-serif'>"
        f"<table role='presentation' cellpadding='0' cellspacing='0' border='0' "
        f"width='100%' style='max-width:420px;margin:0 auto;background:#ffffff;"
        f"border-radius:12px;padding:20px'>"
        f"<tr><td>"
        f"<div style='font-size:13px;color:{_MUTED}'>"
        f"{_esc(report.restaurant_name)} &middot; {report.local_date:%a %d %b}</div>"
        f"<div style='font-size:40px;line-height:1.1;font-weight:700;color:{_INK};"
        f"margin-top:10px'>{_esc(_money(report.revenue, cur))}</div>"
        f"{_comparison_html(report.revenue_cmp, weekday)}"
        f"</td></tr>"
        f"<tr><td style='padding-top:18px'>"
        f"<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%'>"
        f"<tr>"
        f"{_stat_cell('Orders', str(report.orders), _comparison_html(report.orders_cmp, weekday))}"
        f"{_stat_cell('Avg order', _money(report.aov, cur), _comparison_html(report.aov_cmp, weekday))}"
        f"</tr></table></td></tr>"
        f"<tr><td style='padding-top:14px'>"
        f"<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%'>"
        f"{''.join(footnotes)}{worth_a_look}"
        f"</table></td></tr>"
        f"<tr><td style='padding-top:16px'>"
        f"<span style='font-size:11px;color:#9a9a9a'>You're receiving this because "
        f"the daily report is switched on for this restaurant. Turn it off any time "
        f"in Settings.</span>"
        f"</td></tr>"
        f"</table></div>"
    )


def render(report: DailyReport) -> tuple[str, str, str]:
    """(subject, text_body, html_body) — pure, so it can be previewed in tests."""
    return _subject(report), _render_text(report), _render_html(report)


# ── Transport ─────────────────────────────────────────────────────────────────

def send_report(report: DailyReport, recipients: list[str], restaurant_id: uuid.UUID) -> bool:
    """
    Dispatch the report. RAISES on delivery failure so the ledger can retry —
    the opposite of receipt_email, and deliberate: see the module docstring.

    Returns True when the message was actually handed to Resend, False when the
    provider is unconfigured and it was only logged. Callers that report success
    to a human MUST surface that difference — a test send that says "sent" while
    RESEND_API_KEY is empty is exactly the silent failure this feature exists to
    avoid.
    """
    if not recipients:
        raise ValueError("No recipient configured for the daily report")

    subject, text_body, html_body = render(report)

    if not settings.RESEND_API_KEY.strip():
        logger.info(
            "DAILY REPORT (not sent — RESEND_API_KEY unset) restaurant=%s date=%s "
            "to=%s subject=%s",
            restaurant_id,
            report.local_date,
            ", ".join(redact_email(r) for r in recipients),
            subject,
        )
        return False

    response = httpx.post(
        settings.RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": settings.REPORTS_FROM,
            "to": recipients,
            "subject": subject,
            "text": text_body,
            "html": html_body,
        },
        timeout=10,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Resend rejected the daily report (status {response.status_code})"
        )
    logger.info(
        "Daily report emailed restaurant=%s date=%s to=%s",
        restaurant_id,
        report.local_date,
        ", ".join(redact_email(r) for r in recipients),
    )
    return True
