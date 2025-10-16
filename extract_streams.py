import requests
import re
import json
from datetime import datetime
from urllib.parse import urlparse, urljoin
import sys
import time

class SportsStreamExtractor:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
    def fetch_prog_data(self, url):
        """Fetch the prog.txt file content"""
        try:
            print(f"Fetching: {url}")
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            print(f"✓ Fetched {len(response.text)} characters")
            return response.text
        except Exception as e:
            print(f"✗ Error fetching prog.txt: {e}")
            return None
    
    def parse_prog_file(self, content):
        """Parse the prog.txt file to extract events and channels"""
        events = []
        lines = content.strip().split('\n')
        
        print(f"\nParsing {len(lines)} lines...")
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            
            # Skip header lines and non-event lines
            if line.startswith('=') or line.startswith('*') or line.startswith('𝐑𝐄𝐀𝐃') or \
               line.startswith('𝐈𝐌𝐏𝐎𝐑𝐓𝐀𝐍𝐓') or line.startswith('𝐔𝐏𝐃𝐀𝐓𝐄') or \
               'LAST UPDATE' in line or 'INFO:' in line or 'EMAIL:' in line or \
               'CHANNELS https://' in line or 'IMPORTANT: USE' in line or \
               line in ['THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY']:
                continue
            
            # Skip channel identifier lines (HD1, BR1, etc.)
            if re.match(r'^(HD|BR|PT)\d+\s+(ENGLISH|BRAZILIAN|SPANISH|GERMAN|ITALIAN|POLISH|ROMANIAN)', line):
                continue
            
            # Parse event lines: TIME   Event Name | URL
            # Pattern: starts with time (HH:MM), has text, pipe, then URL
            match = re.match(r'^(\d{2}:\d{2})\s+(.+?)\s*\|\s*(https?://\S+)', line)
            
            if match:
                time_str = match.group(1)
                event_name = match.group(2).strip()
                url = match.group(3).strip()
                
                # Check if this event already exists
                existing_event = None
                for event in events:
                    if event['time'] == time_str and event['event_name'] == event_name:
                        existing_event = event
                        break
                
                if existing_event:
                    # Add channel to existing event
                    existing_event['channels'].append({
                        'url': url,
                        'iframe_url': None,
                        'm3u8_url': None,
                        'status': 'pending'
                    })
                    print(f"  Added channel to existing event: {event_name[:40]} at {time_str}")
                else:
                    # Create new event
                    events.append({
                        'time': time_str,
                        'event_name': event_name,
                        'channels': [{
                            'url': url,
                            'iframe_url': None,
                            'm3u8_url': None,
                            'status': 'pending'
                        }],
                        'line_number': line_num
                    })
                    print(f"  Found event at line {line_num}: {event_name[:40]} at {time_str}")
        
        print(f"\n✓ Parsed {len(events)} events with channels")
        
        # Print summary
        total_channels = sum(len(event['channels']) for event in events)
        print(f"  Total channels: {total_channels}")
        
        return events
    
    def extract_iframe_from_url(self, url):
        """Extract iframe URL from the given URL"""
        try:
            print(f"    Fetching page: {url[:60]}...")
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            response.raise_for_status()
            
            content = response.text
            
            # Method 1: Standard iframe tags
            iframe_patterns = [
                r'<iframe[^>]+src=["\']([^"\']+)["\']',
                r'<iframe[^>]+src=([^\s>]+)',
                r'src=["\']([^"\']*embed[^"\']*)["\']',
            ]
            
            for pattern in iframe_patterns:
                iframes = re.findall(pattern, content, re.IGNORECASE)
                if iframes:
                    iframe_url = iframes[0].strip()
                    # Handle relative URLs
                    if iframe_url.startswith('//'):
                        iframe_url = 'https:' + iframe_url
                    elif iframe_url.startswith('/'):
                        parsed = urlparse(url)
                        iframe_url = f"{parsed.scheme}://{parsed.netloc}{iframe_url}"
                    elif not iframe_url.startswith('http'):
                        iframe_url = urljoin(url, iframe_url)
                    
                    print(f"    ✓ Found iframe: {iframe_url[:60]}")
                    return iframe_url
            
            # Method 2: Look for player URLs in JavaScript
            js_patterns = [
                r'["\']https?://[^"\']*(?:embed|player)[^"\']*["\']',
                r'player["\']?\s*:\s*["\']([^"\']+)["\']',
                r'source["\']?\s*:\s*["\']([^"\']+)["\']',
            ]
            
            for pattern in js_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    for match in matches:
                        url_match = match.strip('"\'')
                        if 'embed' in url_match or 'player' in url_match:
                            print(f"    ✓ Found player URL: {url_match[:60]}")
                            return url_match
            
            print(f"    ✗ No iframe found")
            return None
            
        except Exception as e:
            print(f"    ✗ Error extracting iframe: {e}")
            return None
    
    def extract_m3u8_from_iframe(self, iframe_url):
        """Extract M3U8 URL from iframe content"""
        try:
            print(f"      Fetching iframe: {iframe_url[:60]}...")
            response = requests.get(iframe_url, headers=self.headers, timeout=15, allow_redirects=True)
            response.raise_for_status()
            
            content = response.text
            
            # Method 1: Direct .m3u8 URLs
            m3u8_pattern = r'https?://[^\s<>"\']+\.m3u8(?:\?[^\s<>"\']*)?'
            m3u8_urls = re.findall(m3u8_pattern, content)
            
            if m3u8_urls:
                # Prefer master playlist
                for url in m3u8_urls:
                    if 'master' in url.lower() or 'playlist' in url.lower():
                        print(f"      ✓ Found M3U8 (master): {url[:60]}")
                        return url
                print(f"      ✓ Found M3U8: {m3u8_urls[0][:60]}")
                return m3u8_urls[0]
            
            # Method 2: Look in JavaScript variables
            js_patterns = [
                r'["\']([^"\']*\.m3u8[^"\']*)["\']',
                r'source["\']?\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'file["\']?\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'hlsUrl["\']?\s*:\s*["\']([^"\']+)["\']',
            ]
            
            for pattern in js_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    url = matches[0]
                    # Handle relative URLs
                    if url.startswith('//'):
                        url = 'https:' + url
                    elif url.startswith('/'):
                        parsed = urlparse(iframe_url)
                        url = f"{parsed.scheme}://{parsed.netloc}{url}"
                    elif not url.startswith('http'):
                        url = urljoin(iframe_url, url)
                    
                    if '.m3u8' in url:
                        print(f"      ✓ Found M3U8 (JS): {url[:60]}")
                        return url
            
            print(f"      ✗ No M3U8 found")
            return None
            
        except Exception as e:
            print(f"      ✗ Error extracting m3u8: {e}")
            return None
    
    def process_events(self, events, max_channels_per_event=3):
        """Process all events and extract iframe and m3u8 URLs"""
        total_channels = sum(len(event['channels']) for event in events)
        processed = 0
        
        for event_idx, event in enumerate(events, 1):
            print(f"\n[{event_idx}/{len(events)}] Processing: {event['event_name'][:50]}")
            
            for channel_idx, channel in enumerate(event['channels'][:max_channels_per_event], 1):
                processed += 1
                print(f"  Channel {channel_idx}/{len(event['channels'])}: {channel['url'][:60]}")
                
                # Extract iframe
                iframe_url = self.extract_iframe_from_url(channel['url'])
                if iframe_url:
                    channel['iframe_url'] = iframe_url
                    channel['status'] = 'iframe_found'
                    
                    # Small delay to avoid rate limiting
                    time.sleep(0.5)
                    
                    # Extract m3u8 from iframe
                    m3u8_url = self.extract_m3u8_from_iframe(iframe_url)
                    if m3u8_url:
                        channel['m3u8_url'] = m3u8_url
                        channel['status'] = 'complete'
                    else:
                        channel['status'] = 'no_m3u8'
                else:
                    channel['status'] = 'no_iframe'
                
                # Small delay between requests
                time.sleep(0.5)
        
        print(f"\n✓ Processed {processed} channels")
        return events
    
    def save_to_json(self, events, filename='streams_data.json'):
        """Save extracted data to JSON file"""
        # Calculate statistics
        total_channels = sum(len(event['channels']) for event in events)
        complete = sum(1 for event in events for ch in event['channels'] if ch['status'] == 'complete')
        iframe_only = sum(1 for event in events for ch in event['channels'] if ch['status'] == 'iframe_found')
        no_iframe = sum(1 for event in events for ch in event['channels'] if ch['status'] == 'no_iframe')
        
        output = {
            'extracted_at': datetime.utcnow().isoformat() + 'Z',
            'total_events': len(events),
            'total_channels': total_channels,
            'statistics': {
                'complete': complete,
                'iframe_only': iframe_only,
                'no_iframe': no_iframe,
                'success_rate': f"{(complete/total_channels*100):.1f}%" if total_channels > 0 else "0%"
            },
            'events': events
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Data saved to {filename}")
        print(f"  Events: {len(events)}")
        print(f"  Total channels: {total_channels}")
        print(f"  Complete (with M3U8): {complete}")
        print(f"  Iframe only: {iframe_only}")
        print(f"  Failed: {no_iframe}")
        
        return filename

def main():
    prog_url = "https://sportsonline.sn/prog.txt"
    
    print("=" * 60)
    print("Sports Stream Extractor")
    print("=" * 60)
    print(f"\nSource: {prog_url}\n")
    
    extractor = SportsStreamExtractor()
    
    # Fetch prog.txt content
    content = extractor.fetch_prog_data(prog_url)
    if not content:
        print("\n✗ Failed to fetch prog.txt")
        sys.exit(1)
    
    # Parse the file
    events = extractor.parse_prog_file(content)
    
    if not events:
        print("\n✗ No events found in prog.txt")
        print("This could mean:")
        print("  - The file format has changed")
        print("  - The file is empty")
        print("  - The parsing logic needs adjustment")
        sys.exit(1)
    
    print(f"\n{'=' * 60}")
    print(f"Starting extraction for {len(events)} events")
    print(f"{'=' * 60}")
    
    # Process events to extract iframes and m3u8 URLs
    processed_events = extractor.process_events(events)
    
    # Save to JSON
    extractor.save_to_json(processed_events)
    
    print(f"\n{'=' * 60}")
    print("Extraction Complete")
    print(f"{'=' * 60}\n")

if __name__ == "__main__":
    main()
