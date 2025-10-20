import re
import json
import datetime
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://rereyano.ru/"
PLAYER_BASE = "https://rereyano.ru/player/"
OUTPUT_FILE = "data/events.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Accept": "*/*",
    "Referer": BASE_URL,
}

CHANNEL_TYPES = {
    1: "Cartel",
    2: "Hoca",
    3: "Caster",
    4: "WIGI"
}


def get_website_text():
    """Fetch main site content."""
    response = requests.get(BASE_URL, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.text


def parse_events(text):
    """Extract events with channel codes."""
    events = []
    pattern = re.compile(
        r"(\d{2}-\d{2}-\d{4}) \((\d{2}:\d{2})\) (.+?) : (.+?)  (.+)"
    )

    for line in text.splitlines():
        match = pattern.search(line)
        if match:
            date, time, competition, teams, channels_raw = match.groups()
            ch_codes = re.findall(r"CH\d+\w*", channels_raw)
            dt_obj = datetime.datetime.strptime(f"{date} {time}", "%d-%m-%Y %H:%M")

            events.append({
                "date": date,
                "time": time,
                "datetime": dt_obj.isoformat(),
                "competition": competition.strip(),
                "teams": teams.strip(),
                "channels": ch_codes,
            })

    return events


def extract_m3u8(iframe_url):
    """Extract m3u8 links from iframe using Playwright."""
    m3u8_links = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(extra_http_headers=HEADERS)
            page = context.new_page()
            page.goto(iframe_url, timeout=30000)

            # Capture network requests
            for request in page.context.requests:
                if ".m3u8" in request.url and request.url not in m3u8_links:
                    m3u8_links.append(request.url)

            # Backup: search page HTML
            html = page.content()
            found = re.findall(r"https?://[^'\"]+\.m3u8[^'\"]*", html)
            for url in found:
                if url not in m3u8_links:
                    m3u8_links.append(url)

            browser.close()
    except Exception as e:
        print(f"⚠️ Failed to extract {iframe_url}: {e}")

    return m3u8_links


def build_data():
    print("Fetching events from rereyano.ru ...")
    html_text = get_website_text()
    events = parse_events(html_text)
    final_data = []

    for event in events:
        channel_entries = []

        for ch_code in event["channels"]:
            match = re.search(r"CH(\d+)", ch_code)
            if not match:
                continue

            channel_id = match.group(1)

            # Dynamically generate iframes for each type
            for player_num, player_name in CHANNEL_TYPES.items():
                iframe_url = f"{PLAYER_BASE}{player_num}/{channel_id}"
                print(f"🎬 Extracting {player_name} -> {iframe_url}")

                m3u8_links = extract_m3u8(iframe_url)

                channel_entries.append({
                    "channel_code": ch_code,
                    "provider": player_name,
                    "iframe": iframe_url,
                    "headers": HEADERS,
                    "m3u8_links": m3u8_links,
                })

        event["channel_entries"] = channel_entries
        final_data.append(event)

    return final_data


def save_json(data):
    import os
    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved {len(data)} events to {OUTPUT_FILE}")


if __name__ == "__main__":
    data = build_data()
    save_json(data)
