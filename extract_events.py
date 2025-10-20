#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced event extractor for rereyano.ru
Includes iframe URLs and .m3u8 extraction with headers.
"""

import re
import json
import base64
from datetime import datetime
from urllib.parse import unquote
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://rereyano.ru/"
OUTPUT_FILE = "events.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Accept": "*/*",
    "Referer": BASE_URL,
}

PLAYER_MAP = {
    "CH1": "https://rereyano.ru/player/1/1",
    "CH2": "https://rereyano.ru/player/2/1",
    "CH3": "https://rereyano.ru/player/3/1",
    "CH4": "https://rereyano.ru/player/4/1",
}

# Regex patterns
EVENT_RE = re.compile(r"(\d{2}-\d{2}-\d{4})\s*\((\d{2}:\d{2})\)\s*([^:]+)\s*:\s*(.+?)\s*((?:\(CH[0-9]+[a-zA-Z]*\)\s*)+)")
CH_RE = re.compile(r"CH\d+[a-zA-Z]*")
M3U8_RE = re.compile(r"https?://[^\s'\"<>]+\.m3u8[^\s'\"<>]*")
BASE64_RE = re.compile(r"[A-Za-z0-9+/=]{40,}")

session = requests.Session()
session.headers.update(HEADERS)


def safe_get(url, timeout=12):
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"[WARN] {url} failed: {e}")
        return ""


def find_m3u8s(text):
    found = re.findall(M3U8_RE, text or "")
    return list(set(found))


def decode_base64_strings(text):
    urls = []
    for match in BASE64_RE.findall(text):
        try:
            dec = base64.b64decode(match + "==").decode("utf-8", errors="ignore")
            urls += find_m3u8s(dec)
        except Exception:
            continue
    return list(set(urls))


def extract_m3u8_from_iframe(iframe_url):
    html = safe_get(iframe_url)
    if not html:
        return []

    urls = find_m3u8s(html)
    urls += decode_base64_strings(html)

    # check <script> contents for embedded streams
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        txt = script.string or script.get_text() or ""
        urls += find_m3u8s(txt)
        urls += decode_base64_strings(txt)

    return list(set(urls))


def guess_player_url(ch_code):
    """Map CH code to known player endpoints."""
    num = re.search(r"CH(\d+)", ch_code)
    if not num:
        return PLAYER_MAP["CH4"]
    prefix = f"CH{num.group(1)[0]}"
    for key in PLAYER_MAP.keys():
        if prefix.startswith(key):
            return PLAYER_MAP[key]
    return PLAYER_MAP["CH4"]


def parse_events(main_html):
    events = []
    for match in EVENT_RE.finditer(main_html):
        date_str, time_str, league, teams, ch_block = match.groups()
        channels = CH_RE.findall(ch_block)
        iso_dt = f"{date_str} {time_str}"
        try:
            iso_dt = datetime.strptime(iso_dt, "%d-%m-%Y %H:%M").isoformat()
        except:
            pass

        ev = {
            "date": date_str,
            "time": time_str,
            "datetime": iso_dt,
            "competition": league.strip(),
            "teams": teams.strip(),
            "channels": [],
        }

        for ch in channels:
            iframe_url = guess_player_url(ch)
            m3u8s = extract_m3u8_from_iframe(iframe_url)
            ch_entry = {
                "channel_code": ch,
                "iframe": iframe_url,
                "headers": HEADERS,
                "m3u8_links": m3u8s,
            }
            ev["channels"].append(ch_entry)

        events.append(ev)
    return events


def main():
    print("[INFO] Fetching main site…")
    html = safe_get(BASE_URL)
    if not html:
        print("[ERROR] Could not fetch main site.")
        return

    events = parse_events(html)
    print(f"[INFO] Extracted {len(events)} events")

    data = {
        "source": BASE_URL,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "events": events,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[OK] Saved → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
