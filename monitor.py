from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_URL = "https://dltlly.com"
TICKETS_URL = urljoin(BASE_URL, "/collections/tickets")
STATE_FILE = Path(__file__).with_name("known_tickets.json")
REQUEST_TIMEOUT = (5, 15)
DISCORD_MAX_ATTEMPTS = 3


def build_session() -> requests.Session:
    retry_policy = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "dltlly-ticket-monitor/1.0 "
                "(+https://github.com/nbrandtner/dltlly-ticket-monitor)"
            )
        }
    )
    session.mount("https://", HTTPAdapter(max_retries=retry_policy))
    return session


def load_known_tickets() -> list[dict[str, str]]:
    try:
        with STATE_FILE.open("r", encoding="utf-8") as file_handle:
            tickets = json.load(file_handle)
    except FileNotFoundError:
        print("No saved ticket state exists yet; starting with an empty state.")
        return []

    if not isinstance(tickets, list):
        raise RuntimeError("Saved ticket state must contain a JSON list")

    return tickets


def save_known_tickets(tickets: list[dict[str, str]]) -> None:
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=STATE_FILE.parent,
        prefix=f".{STATE_FILE.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as file_handle:
            json.dump(tickets, file_handle, indent=2, ensure_ascii=False)
            file_handle.write("\n")
        os.replace(temporary_path, STATE_FILE)
    finally:
        temporary_path.unlink(missing_ok=True)


def extract_tickets(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    events_section = soup.select_one(
        "section.shopify-section.shopify-section--main-collection"
    )

    if events_section is None:
        raise RuntimeError("Could not find events section")

    tickets = []
    for event in events_section.select("div.product-card__info"):
        link = event.select_one("a[href]")
        if link is None:
            continue

        relative_url = link.get("href")
        if not isinstance(relative_url, str):
            continue

        price_element = event.find("sale-price")
        if price_element is None:
            price_text = "Price unavailable"
        else:
            accessibility_text = price_element.select_one("span.sr-only")
            if accessibility_text is not None:
                accessibility_text.decompose()

            raw_price = price_element.get_text(" ", strip=True)
            price_text = re.sub(r"^ab\s*", "", raw_price, flags=re.IGNORECASE)

        tickets.append(
            {
                "title": link.get_text(strip=True),
                "url": urljoin(BASE_URL, relative_url),
                "price": price_text,
            }
        )

    if not tickets:
        raise RuntimeError("No tickets were extracted; refusing to overwrite saved state")

    return tickets


def discord_retry_delay(response: requests.Response | None, attempt: int) -> float:
    default_delay = float(2 ** (attempt - 1))
    if response is None or response.status_code != 429:
        return default_delay

    try:
        retry_after = float(response.json().get("retry_after", default_delay))
    except (AttributeError, TypeError, ValueError, requests.JSONDecodeError):
        retry_after = default_delay

    return min(max(retry_after, 1.0), 30.0)


def send_discord_notification(
    session: requests.Session,
    webhook_url: str,
    ticket: dict[str, str],
) -> None:
    payload = {
        "content": (
            f"New ticket found: {ticket['title']} - "
            f"{ticket['price']} - {ticket['url']}"
        )
    }
    last_error = "unknown error"
    attempts_made = 0

    for attempt in range(1, DISCORD_MAX_ATTEMPTS + 1):
        attempts_made = attempt
        response = None
        should_retry = True

        try:
            response = session.post(
                webhook_url,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            if response.ok:
                return

            last_error = f"HTTP {response.status_code}"
            should_retry = response.status_code == 429 or response.status_code >= 500
        except requests.RequestException as error:
            # Do not print the exception: it may contain the secret webhook URL.
            last_error = type(error).__name__

        if not should_retry or attempt == DISCORD_MAX_ATTEMPTS:
            break

        delay = discord_retry_delay(response, attempt)
        print(
            f"Discord delivery attempt {attempt} failed ({last_error}); "
            f"retrying in {delay:g} seconds."
        )
        time.sleep(delay)

    raise RuntimeError(
        f"Discord notification failed after {attempts_made} attempt(s) "
        f"({last_error})"
    )


def main() -> None:
    discord_webhook = os.getenv("DISCORD_WEBHOOK_URL")
    if not discord_webhook:
        raise RuntimeError("DISCORD_WEBHOOK_URL environment variable is not set")

    known_tickets = load_known_tickets()
    known_urls = {
        ticket["url"]
        for ticket in known_tickets
        if isinstance(ticket, dict) and isinstance(ticket.get("url"), str)
    }

    with build_session() as session:
        response = session.get(TICKETS_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        current_tickets = extract_tickets(response.text)

        saved_tickets = []
        new_ticket_count = 0
        delivery_failures = []

        for ticket in current_tickets:
            if ticket["url"] in known_urls:
                saved_tickets.append(ticket)
                continue

            new_ticket_count += 1
            print(
                f"New ticket found: {ticket['title']} - "
                f"{ticket['price']} - {ticket['url']}"
            )

            try:
                send_discord_notification(session, discord_webhook, ticket)
            except RuntimeError as error:
                print(f"Discord delivery failed for {ticket['title']}: {error}")
                delivery_failures.append(ticket)
            else:
                saved_tickets.append(ticket)

    if new_ticket_count == 0:
        print("No new tickets found.")

    # Failed deliveries are deliberately omitted so the next run retries them.
    save_known_tickets(saved_tickets)

    if delivery_failures:
        raise RuntimeError(
            f"Failed to deliver {len(delivery_failures)} new ticket notification(s); "
            "they remain eligible for retry."
        )


if __name__ == "__main__":
    main()
