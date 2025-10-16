import requests
import re
import json
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import sys

class SportsStreamExtractor:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
    def fetch_prog_data(self, url):
        """Fetch the prog.txt file content"""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"Error fetching prog.txt: {e}")
            return None
    
    def parse_prog_file(self, content):
        """Parse the prog.txt file to extract events and channels"""
        events = []
        current_event = None
        
        lines = content.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if line is an event (starts with timestamp or event marker)
            if '|' in line and not line.startswith('http'):
                # Parse event line
                parts = line.split('|')
                if len(parts) >= 2:
                    if current_event:
                        events.append(current_event)
                    
                    current_event = {
                        'time': parts[0].strip(),
                        'event_name': parts[1].strip(),
                        'channels': []
                    }
            
            # Check if line is a channel URL
            elif line.startswith('http') and current_event:
                current_event['channels'].append({
                    'url': line,
                    'iframe_url': None,
                    'm3u8_url': None
                })
        
        # Add the last event
        if current_event:
            events.append(current_event)
        
        return events
    
    def extract_iframe_from_url(self, url):
        """Extract iframe URL from the given URL"""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            # Look for iframe tags
            iframe_pattern = r'<iframe[^>]+src=["\']([^"\']+)["\']'
            iframes = re.findall(iframe_pattern, response.text, re.IGNORECASE)
            
            if iframes:
                return iframes[0]
            
            # Alternative: Look for embed URLs in JavaScript
            embed_pattern = r'["\']https?://[^"\']*embed[^"\']*["\']'
            embeds = re.findall(embed_pattern, response.text)
            if embeds:
                return embeds[0].strip('"\'')
            
            return None
        except Exception as e:
            print(f"Error extracting iframe from {url}: {e}")
            return None
    
    def extract_m3u8_from_iframe(self, iframe_url):
        """Extract M3U8 URL from iframe content"""
        try:
            response = requests.get(iframe_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            # Look for .m3u8 URLs
            m3u8_pattern = r'https?://[^\s<>"\']+\.m3u8[^\s<>"\']*'
            m3u8_urls = re.findall(m3u8_pattern, response.text)
            
            if m3u8_urls:
                return m3u8_urls[0]
            
            # Look for m3u8 in JavaScript variables
            js_pattern = r'["\']([^"\']*\.m3u8[^"\']*)["\']'
            js_m3u8 = re.findall(js_pattern, response.text)
            if js_m3u8:
                url = js_m3u8[0]
                if url.startswith('http'):
                    return url
                elif url.startswith('//'):
                    return 'https:' + url
                else:
                    # Relative URL - construct absolute URL
                    parsed = urlparse(iframe_url)
                    base_url = f"{parsed.scheme}://{parsed.netloc}"
                    return base_url + ('/' if not url.startswith('/') else '') + url
            
            return None
        except Exception as e:
            print(f"Error extracting m3u8 from {iframe_url}: {e}")
            return None
    
    def process_events(self, events):
        """Process all events and extract iframe and m3u8 URLs"""
        for event in events:
            print(f"\nProcessing event: {event['event_name']}")
            
            for i, channel in enumerate(event['channels']):
                print(f"  Channel {i+1}: {channel['url']}")
                
                # Extract iframe
                iframe_url = self.extract_iframe_from_url(channel['url'])
                if iframe_url:
                    channel['iframe_url'] = iframe_url
                    print(f"    Found iframe: {iframe_url}")
                    
                    # Extract m3u8 from iframe
                    m3u8_url = self.extract_m3u8_from_iframe(iframe_url)
                    if m3u8_url:
                        channel['m3u8_url'] = m3u8_url
                        print(f"    Found m3u8: {m3u8_url}")
                    else:
                        print(f"    No m3u8 found")
                else:
                    print(f"    No iframe found")
        
        return events
    
    def save_to_json(self, events, filename='streams_data.json'):
        """Save extracted data to JSON file"""
        output = {
            'extracted_at': datetime.utcnow().isoformat(),
            'total_events': len(events),
            'events': events
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Data saved to {filename}")
        return filename

def main():
    prog_url = "https://sportsonline.site/prog.txt"
    
    print("=== Sports Stream Extractor ===\n")
    print(f"Fetching data from: {prog_url}\n")
    
    extractor = SportsStreamExtractor()
    
    # Fetch prog.txt content
    content = extractor.fetch_prog_data(prog_url)
    if not content:
        print("Failed to fetch prog.txt")
        sys.exit(1)
    
    # Parse the file
    events = extractor.parse_prog_file(content)
    print(f"Found {len(events)} events\n")
    
    # Process events to extract iframes and m3u8 URLs
    processed_events = extractor.process_events(events)
    
    # Save to JSON
    extractor.save_to_json(processed_events)
    
    print("\n=== Extraction Complete ===")

if __name__ == "__main__":
    main()
