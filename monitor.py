from urllib.parse import urljoin

import requests, bs4, json, os

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")
BASE_URL = "https://dltlly.com"
TICKETS_URL = urljoin(BASE_URL, "/collections/tickets")

if DISCORD_WEBHOOK is None:
    raise RuntimeError("DISCORD_WEBHOOK_URL environment variable is not set")
try:
    with open("known_tickets.json", 'r', encoding="utf-8") as fh:
        known_tickets = json.load(fh)
except FileNotFoundError:
    print("The file does not exist!")
    known_tickets = []

response = requests.get(TICKETS_URL, timeout=15)
response.raise_for_status()

soup = bs4.BeautifulSoup(response.text, "html.parser")

events_section = soup.find(
    "section",
    {"class": "shopify-section shopify-section--main-collection"}
)

if events_section is None:
    raise RuntimeError("Could not find events section")

events = events_section.find_all(
    "div",
    {"class": "product-card__info"}
)

event_list = []

for event in events:
    a_tag = event.find("a")
    if a_tag is None:
        continue

    relative_url = a_tag.get("href")
    if relative_url is None:
        continue

    ticket_url = urljoin(BASE_URL, relative_url)

    price_element = event.find("sale-price")
    if price_element is None:
        price_text = "Price unavailable"
    else:
        accessibility_text = price_element.find(
            "span",
            {"class": "sr-only"}
        )
        if accessibility_text is not None:
            accessibility_text.decompose()

        price_text = (
            price_element
            .get_text(strip=True)
            .removeprefix("ab ")
        )

    ticket = {
        "title": a_tag.get_text(strip=True),
        "url": ticket_url,
        "price": price_text
    }

    event_list.append(ticket)

if not event_list:
    raise RuntimeError("No tickets were extracted; refusing to overwrite saved state")

known_urls = set()
for ticket in known_tickets:
    if "url" in ticket:
        known_urls.add(ticket["url"])

changes = 0
for ticket in event_list:
    if ticket["url"] not in known_urls:
        print(f"New ticket found: {ticket['title']} - {ticket['price']} - {ticket['url']}")
        if DISCORD_WEBHOOK:
            payload = {
                "content": f"New ticket found: {ticket['title']} - {ticket['price']} - {ticket['url']}"
            }
            response = requests.post(DISCORD_WEBHOOK, json=payload)
            if response.status_code != 204:
                print(f"Failed to send Discord notification: {response.status_code} - {response.text}")
        changes += 1
if changes == 0:
    print("No new tickets found.")
with open("known_tickets.json", 'w', encoding="utf-8") as fh:
    json.dump(event_list, fh, indent=2, ensure_ascii=False)

