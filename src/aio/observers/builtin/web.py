"""Is the company's front door actually open?

The cheapest external observation there is: one GET against each company's
own website. No key, no vendor, no account -- which makes it the first
observer that tells the founder something JARVIS could not have known from
its own database.

Two deliberate restraints. Companies with no website recorded are skipped
entirely rather than reported as broken: most pre-launch companies have none,
and "you have no website" is not an outage. And an unexpected failure inside
this observer (a malformed URL, an SSL stack blowing up) is not reported as
downtime -- only a real connection failure or a 5xx from the server is,
because a false "your site is down" at 3am costs more trust than a missed
one.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import httpx

from aio.models.business import Company
from aio.models.signals import Signal
from aio.observers.base import Observer, register_observer

if TYPE_CHECKING:
    from aio.business.service import BusinessService

logger = logging.getLogger("aio.observers.web")

# Long enough that a cold serverless start is not an incident, short enough
# that a human would have already noticed and been annoyed.
_SLOW_SECONDS = 3.0

# Above this the request is treated as a failed connection rather than a slow
# one -- nobody waits ten seconds for a homepage.
_TIMEOUT_SECONDS = 10.0


def _normalized(website: str) -> str:
    """Founders type 'tradew.in', not 'https://tradew.in'."""
    website = website.strip()
    if not website:
        return ""
    return website if "://" in website else f"https://{website}"


class WebsiteObserver(Observer):
    """Watches each company's public website for outages and slowdowns."""

    name = "website"
    display_name = "Website Uptime"
    description = "Checks each company's website is reachable and responding quickly."
    watches = ("website_offline", "website_slow")

    def observe(self, business: "BusinessService") -> list[Signal]:
        signals: list[Signal] = []
        for company in business.list_companies():
            url = _normalized(company.website)
            if not url:
                continue
            signal = self._check(company, url)
            if signal is not None:
                signals.append(signal)
        return signals

    def _check(self, company: Company, url: str) -> Signal | None:
        started = time.perf_counter()
        try:
            response = httpx.get(url, timeout=_TIMEOUT_SECONDS, follow_redirects=True)
        except httpx.RequestError as exc:
            # DNS failure, refused connection, TLS error, timeout. From the
            # outside world's point of view these are indistinguishable from
            # the site being down, which is exactly what a visitor sees.
            return self._offline(company, url, f"{type(exc).__name__}: {exc}")
        except Exception:
            # Anything else is a bug in this observer, not evidence about the
            # site. Say nothing rather than declare a false outage.
            logger.warning("website check for %s failed unexpectedly", url, exc_info=True)
            return None

        elapsed = time.perf_counter() - started

        if response.status_code >= 500:
            return self._offline(
                company, url, f"Server returned HTTP {response.status_code}."
            )

        if elapsed > _SLOW_SECONDS:
            return Signal(
                source=self.name,
                kind="website_slow",
                title=f"{company.name}'s website is slow ({elapsed:.1f}s)",
                detail=(
                    f"{url} responded HTTP {response.status_code} in {elapsed:.1f}s, "
                    f"over the {_SLOW_SECONDS:.0f}s threshold. Visitors leave."
                ),
                severity="notable",
                company_id=company.id,
                dedupe_key=f"website_slow:{company.id}",
            )
        return None

    def _offline(self, company: Company, url: str, reason: str) -> Signal:
        return Signal(
            source=self.name,
            kind="website_offline",
            title=f"{company.name}'s website is unreachable",
            detail=f"{url} -- {reason}",
            severity="urgent",
            company_id=company.id,
            # Identity is "this company's site is down", not this attempt, so
            # a multi-day outage stays one signal that keeps getting louder.
            dedupe_key=f"website_offline:{company.id}",
        )


register_observer(WebsiteObserver())
