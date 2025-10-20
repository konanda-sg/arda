import requests
import re
import json
from datetime import datetime

OUTPUT_FILE = "data/events.json"
BASE_URL = "https://rereyano.ru/player"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Accept": "*/*",
    "Referer": "https://rereyano.ru/"
}

# Sample event data (replace this with your real fetch)
EVENTS = [
    {
        "date": "20-10-2025",
        "time": "15:00",
        "competition": "Pro League",
        "teams": "Standard Liège - Antwerp",
        "channel_code": "CH153fr"
    },
    {
        "date": "21-10-2025",
        "time": "03:10",
        "competition": "Liga Betplay Dimayor",
        "teams": "I",
        "channel_code": "CH56es"
    }
]

CHANNEL_NAMES = ["Cartel", "Hoca", "Caster", "WIGI"]

def extract_m3u8_from_html(html):
    """
    Extracts m3u8 URLs from any JavaScript or HTML source tags.
    """
    patterns = [
        r'https?://[^\s\'"<>]+\.m3u8',
        r'src\s*=\s*"([^"]+\.m3u8)"',
        r'file:\s*"([^"]+\.m3u8)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def fetch_m3u8_links(channel_id):
    """
    Fetches all 4 player links and extracts m3u8 if found.
    """
    results = []
    for i, name in enumerate(CHANNEL_NAMES, start=1):
        url = f"{BASE_URL}/{i}/{channel_id}"
        print(f"🎬 Extracting {name} -> {url}")
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            m3u8_url = extract_m3u8_from_html(r.text)
            result = {
                "channel_code": f"CH{channel_id}",
                "iframe": url,
                "headers": HEADERS,
                "m3u8_links": [m3u8_url] if m3u8_url else []
            }
            results.append(result)
        except Exception as e:
            print(f"⚠️ Failed to extract {url}: {e}")
    return results


def main():
    all_events = []
    for event in EVENTS:
        code = event.get("channel_code", "")
        channel_id = re.sub(r"\D", "", code)
        if not channel_id:
            continue

        channel_entries = fetch_m3u8_links(channel_id)
        all_events.append({
            "date": event["date"],
            "time": event["time"],
            "datetime": datetime.strptime(
                f"{event['date']} {event['time']}", "%d-%m-%Y %H:%M"
            ).isoformat(),
            "competition": event["competition"],
            "teams": event["teams"],
            "channels": [c["channel_code"] for c in channel_entries],
            "channel_entries": channel_entries
        })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_events, f, ensure_ascii=False, indent=2)

    print(f"✅ Extraction complete. Saved {len(all_events)} events to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
