#!/usr/bin/env python3
"""
extract_events.py

- Scrapes https://rereyano.ru/ for event lines (date/time, competition, teams, channel codes)
- For each channel code it will attempt to fetch m3u8s by visiting the provided player URLs
  and using multiple heuristics (regex for .m3u8, JSON 'sources' arrays, base64 decoding, etc).
- Writes/overwrites events.json with structured output.

Run: python3 extract_events.py
"""

import re
import json
import base64
import time
from datetime import datetime
from urllib.parse import unquote
import requests
from bs4 import BeautifulSoup

# CONFIG
BASE_URL = "https://rereyano.ru/"
# Player endpoints you provided (order preserved)
PLAYER_URLS = [
    "https://rereyano.ru/player/1/1",
    "https://rereyano.ru/player/2/1",
    "https://rereyano.ru/player/3/1",
    "https://rereyano.ru/player/4/1",
]
OUTPUT_FILE = "events.json"
USER_AGENT = "Mozilla/5.0 (compatible; extractor/1.0; +https://github.com/)"

# Requests session with reasonable defaults
s = requests.Session()
s.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/json,*/*"})

# Regex patterns
DATE_LINE_RE = re.compile(
    r"(\d{2}-\d{2}-\d{4})\s*\(\s*(\d{2}:\d{2})\s*\)\s*([^:]+)\s*:\s*([^()]+?)\s*(?:\(([^)]*)\))?",
    re.UNICODE,
)
CH_CODE_RE = re.compile(r"\(CH[0-9]+[a-zA-Z]*\)")
M3U8_RE = re.compile(r"https?://[^\s'\"<>]+?\.m3u8\b")
BASE64_RE = re.compile(r"(?:(?:['\"])|(?:\b))([A-Za-z0-9+/=]{40,})")  # possible base64-ish long strings

def safe_get(url, timeout=12):
    try:
        resp = s.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp
    except Exception as e:
        # print debug info but keep going
        print(f"[WARN] GET {url} failed: {e}")
        return None

def find_m3u8s_in_text(text):
    found = set(re.findall(M3U8_RE, text or ""))
    return list(found)

def try_extract_from_script_text(text):
    """
    Try to locate common JS/JSON player structures like:
      sources: [{file:"...m3u8"}, ...]
      "file":"...m3u8"
    Or detect base64 strings in the page and decode & search for m3u8 inside them.
    """
    results = set()

    # direct .m3u8 matches
    for m in find_m3u8s_in_text(text):
        results.add(m)

    # JSON-like "file":"...m3u8"
    for m in re.findall(r'["\']file["\']\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']', text, re.IGNORECASE):
        results.add(m)

    # sources array: sources:[{file:"..."}]
    for m in re.findall(r'["\']sources["\']\s*:\s*(\[[^\]]+\])', text, re.IGNORECASE | re.DOTALL):
        try:
            # try to make a valid json from single quotes
            j = m.replace("'", '"')
            js = json.loads(j)
            for item in js:
                if isinstance(item, dict):
                    for v in item.values():
                        if isinstance(v, str) and ".m3u8" in v:
                            results.add(v)
        except Exception:
            # fallback to regex inside
            for mm in re.findall(r'https?://[^"\']+?\.m3u8', m):
                results.add(mm)

    # Try to detect long base64-like strings and decode them
    for b64match in BASE64_RE.findall(text):
        # only attempt decode if contains '=' or length is multiple of 4
        try:
            # clean
            cand = b64match.strip().strip("'\"")
            if len(cand) % 4 != 0:
                # pad
                pad = 4 - (len(cand) % 4)
                cand += "=" * pad
            decoded = base64.b64decode(cand, validate=False)
            try:
                decoded_text = decoded.decode("utf-8", errors="ignore")
                for mm in find_m3u8s_in_text(decoded_text):
                    results.add(mm)
            except Exception:
                pass
        except Exception:
            pass

    return list(results)


def extract_player_m3u8(player_url):
    """
    Visit a player URL and attempt several strategies to extract m3u8 playlist URLs.
    Returns list of unique m3u8 URLs found.
    """
    print(f"[INFO] probing player: {player_url}")
    m3u8s = set()

    resp = safe_get(player_url)
    if resp and resp.text:
        page = resp.text

        # 1) search page text directly
        for m in find_m3u8s_in_text(page):
            m3u8s.add(m)

        # 2) parse scripts and do deeper inspections
        soup = BeautifulSoup(page, "html.parser")
        # a) look at <script> contents
        for script in soup.find_all("script"):
            txt = script.string or script.get_text() or ""
            for m in try_extract_from_script_text(txt):
                m3u8s.add(m)

        # b) Look for iframe or embed tags inside page
        for ifr in soup.find_all(["iframe", "embed", "source"]):
            src = ifr.get("src") or ifr.get("data-src") or ifr.get("data")
            if src:
                # if src itself contains m3u8, collect it
                for m in find_m3u8s_in_text(src):
                    m3u8s.add(m)
                # if src is another page, fetch and parse recursively (small depth)
                if src.startswith("http"):
                    sub = safe_get(src)
                    if sub and sub.text:
                        for m in find_m3u8s_in_text(sub.text):
                            m3u8s.add(m)
                        for m in try_extract_from_script_text(sub.text):
                            m3u8s.add(m)

        # c) search for typical embed URLs that are base64 encoded in query param
        # e.g. ?r=BASE64ENCODED
        for match in re.findall(r"[?&]r=([A-Za-z0-9_\-=%]+)", page):
            try:
                dec = unquote(match)
                # if contains percent-encoding or base64, try both
                # try base64
                try:
                    b = base64.b64decode(dec + "==", validate=False)
                    decoded_text = b.decode("utf-8", errors="ignore")
                    for m in find_m3u8s_in_text(decoded_text):
                        m3u8s.add(m)
                except Exception:
                    pass
            except Exception:
                pass

    # Try common patterns via HEAD/OPTIONS (some hosts expose playlist url from known channels)
    # (we avoid too many requests; optional)

    return sorted(m3u8s)


def parse_events_from_main_page(text):
    """
    Parse the main listing page lines for event entries of the form:
    20-10-2025 (15:00) Pro League : Standard Liège - Antwerp  (CH153fr)
    """
    events = []
    # Replace special dashes etc and normalize
    txt = text.replace("\xa0", " ").replace("\u2013", "-").replace("\u2014", " - ")
    # Split by lines and look for date patterns
    lines = txt.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = DATE_LINE_RE.search(line)
        if m:
            date_str, time_str, competition, teams, maybe_channel_block = m.groups()
            # Extract channel codes (all CH... tokens)
            codes = re.findall(r"CH[0-9]+[a-zA-Z]*", (maybe_channel_block or ""))
            # Teams may contain extra parenthetical pieces - strip trailing whitespace
            teams = teams.strip()
            comp = competition.strip()
            # Build event dict
            try:
                dt_obj = datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %H:%M")
                iso_dt = dt_obj.isoformat()
            except Exception:
                iso_dt = f"{date_str} {time_str}"
            events.append({
                "date": date_str,
                "time": time_str,
                "datetime": iso_dt,
                "competition": comp,
                "teams": teams,
                "channels": codes,
            })
    return events


def main():
    print("[INFO] fetching main site:", BASE_URL)
    resp = safe_get(BASE_URL)
    if not resp:
        print("[ERROR] Could not fetch main page.")
        return

    # parse events from main page text
    page_text = resp.text
    events = parse_events_from_main_page(page_text)
    print(f"[INFO] found {len(events)} events on page")

    # For each event, for each channel code try to probe each player URL
    for ev in events:
        ev["channel_entries"] = []
        for code in ev["channels"]:
            # For this site we don't have a direct mapping of CHxxx to specific player number,
            # so attempt to probe each known player URL and see what m3u8s are found.
            channel_entry = {
                "channel_code": code,
                "probes": []
            }
            for purl in PLAYER_URLS:
                m3u8s = []
                try:
                    m3u8s = extract_player_m3u8(purl)
                except Exception as e:
                    print(f"[WARN] probe failed for {purl}: {e}")
                channel_entry["probes"].append({
                    "player_url": purl,
                    "m3u8s": m3u8s
                })
                # small delay to avoid hammering
                time.sleep(0.7)
            ev["channel_entries"].append(channel_entry)

    # Save output
    payload = {
        "source": BASE_URL,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "events": events
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    print(f"[INFO] wrote {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
