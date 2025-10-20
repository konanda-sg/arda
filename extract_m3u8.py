#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_events_playwright.py
Scrapes https://rereyano.ru/ events, executes JS in player pages,
captures live .m3u8 requests, and stores results in events.json.
"""

import re
import json
import asyncio
from datetime import datetime
import requests
from playwright.async_api import async_playwright

BASE_URL = "https://rereyano.ru/"
OUTPUT_FILE = "events.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0"

PLAYER_MAP = {
    "CH1": "https://rereyano.ru/player/1/1",
    "CH2": "https://rereyano.ru/player/2/1",
    "CH3": "https://rereyano.ru/player/3/1",
    "CH4": "https://rereyano.ru/player/4/1",
}

EVENT_RE = re.compile(r"(\d{2}-\d{2}-\d{4})\s*\((\d{2}:\d{2})\)\s*([^:]+)\s*:\s*(.+?)\s*((?:\(CH[0-9]+[a-zA-Z]*\)\s*)+)")
CH_RE = re.compile(r"CH\d+[a-zA-Z]*")


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


def parse_events(html):
    events = []
    for match in EVENT_RE.finditer(html):
        date_str, time_str, league, teams, ch_block = match.groups()
        channels = CH_RE.findall(ch_block)
        try:
            iso_dt = datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %H:%M").isoformat()
        except:
            iso_dt = f"{date_str} {time_str}"

        ev = {
            "date": date_str,
            "time": time_str,
            "datetime": iso_dt,
            "competition": league.strip(),
            "teams": teams.strip(),
            "channels": [{"channel_code": ch, "iframe": guess_player_url(ch)} for ch in channels],
        }
        events.append(ev)
    return events


async def extract_m3u8_with_playwright(iframe_url):
    """Open iframe URL in headless Chromium, capture .m3u8 requests."""
    print(f"[PLAYWRIGHT] {iframe_url}")
    m3u8_links = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 720},
            extra_http_headers={"Referer": BASE_URL},
        )
        page = await context.new_page()

        page.on("request", lambda req: (
            m3u8_links.add(req.url)
            if ".m3u8" in req.url else None
        ))

        try:
            await page.goto(iframe_url, wait_until="networkidle", timeout=20000)
            await asyncio.sleep(6)
        except Exception as e:
            print(f"[WARN] Failed to load {iframe_url}: {e}")
        finally:
            await browser.close()

    return list(m3u8_links)


async def main():
    print("[INFO] Fetching main page…")
    html = requests.get(BASE_URL, headers={"User-Agent": USER_AGENT}).text
    events = parse_events(html)
    print(f"[INFO] Found {len(events)} events")

    for ev in events:
        for ch in ev["channels"]:
            iframe = ch["iframe"]
            links = await extract_m3u8_with_playwright(iframe)
            ch["headers"] = {
                "User-Agent": USER_AGENT,
                "Referer": BASE_URL,
                "Origin": "https://rereyano.ru",
                "Accept": "*/*",
            }
            ch["m3u8_links"] = links
            print(f"  → {ch['channel_code']}: {len(links)} streams")

    output = {
        "source": BASE_URL,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "events": events,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[✅] Saved {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
