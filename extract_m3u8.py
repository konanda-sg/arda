import requests
import json
import re
from datetime import datetime
from playwright.sync_api import sync_playwright
import time

def fetch_schedule(url):
    """Fetch the schedule from the text file"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error fetching schedule: {e}")
        return None

def parse_schedule(content):
    """Parse the schedule text to extract events"""
    events = []
    lines = content.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or '|' not in line:
            continue
        
        try:
            # Split by pipe
            parts = line.split('|')
            if len(parts) >= 2:
                time_and_event = parts[0].strip()
                url = parts[1].strip()
                
                # Extract time and event name
                time_match = re.match(r'(\d{2}:\d{2})\s+(.*)', time_and_event)
                if time_match:
                    event_time = time_match.group(1)
                    event_name = time_match.group(2)
                    
                    events.append({
                        'time': event_time,
                        'name': event_name,
                        'embed_url': url
                    })
        except Exception as e:
            print(f"Error parsing line '{line}': {e}")
            continue
    
    return events

def extract_m3u8_from_iframe(embed_url, timeout=30):
    """Extract M3U8 URL from iframe using Playwright"""
    m3u8_url = None
    referer = None
    headers = {}
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            # Intercept network requests
            def handle_request(request):
                nonlocal m3u8_url, referer, headers
                url = request.url
                
                # Check if it's an M3U8 request
                if '.m3u8' in url:
                    m3u8_url = url
                    referer = request.headers.get('referer', embed_url)
                    headers = dict(request.headers)
                    print(f"Found M3U8: {url}")
            
            page.on('request', handle_request)
            
            # Navigate to the page
            print(f"Loading: {embed_url}")
            page.goto(embed_url, wait_until='networkidle', timeout=timeout * 1000)
            
            # Wait a bit for video player to initialize
            time.sleep(5)
            
            # Try to find and click play button if exists
            try:
                play_selectors = [
                    'button[aria-label*="play" i]',
                    'button.vjs-big-play-button',
                    '.play-button',
                    'button[title*="play" i]',
                    '[class*="play"]'
                ]
                
                for selector in play_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            page.locator(selector).first.click(timeout=2000)
                            print(f"Clicked play button: {selector}")
                            time.sleep(3)
                            break
                    except:
                        continue
            except Exception as e:
                print(f"No play button found or error clicking: {e}")
            
            # Wait for M3U8 to load
            wait_time = 0
            max_wait = 10
            while not m3u8_url and wait_time < max_wait:
                time.sleep(1)
                wait_time += 1
            
            browser.close()
            
    except Exception as e:
        print(f"Error extracting M3U8 from {embed_url}: {e}")
    
    return {
        'm3u8_url': m3u8_url,
        'referer': referer or embed_url,
        'headers': {
            'User-Agent': headers.get('user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
            'Referer': referer or embed_url,
            'Origin': '/'.join(embed_url.split('/')[:3]) if embed_url else ''
        }
    }

def main():
    schedule_url = "https://sportsonline.sn/prog.txt"
    
    print("Fetching schedule...")
    content = fetch_schedule(schedule_url)
    
    if not content:
        print("Failed to fetch schedule")
        return
    
    print("Parsing schedule...")
    events = parse_schedule(content)
    print(f"Found {len(events)} events")
    
    results = []
    
    for idx, event in enumerate(events, 1):
        print(f"\n[{idx}/{len(events)}] Processing: {event['name']} at {event['time']}")
        
        m3u8_data = extract_m3u8_from_iframe(event['embed_url'])
        
        event_data = {
            'time': event['time'],
            'name': event['name'],
            'embed_url': event['embed_url'],
            'm3u8_url': m3u8_data['m3u8_url'],
            'referer': m3u8_data['referer'],
            'headers': m3u8_data['headers'],
            'extracted_at': datetime.utcnow().isoformat() + 'Z'
        }
        
        results.append(event_data)
        
        # Small delay between requests
        time.sleep(2)
    
    # Save to JSON
    output_file = 'streams.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'updated_at': datetime.utcnow().isoformat() + 'Z',
            'total_events': len(results),
            'events': results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Saved {len(results)} events to {output_file}")
    
    # Print summary
    successful = sum(1 for r in results if r['m3u8_url'])
    print(f"Successfully extracted M3U8 for {successful}/{len(results)} events")

if __name__ == "__main__":
    main()
