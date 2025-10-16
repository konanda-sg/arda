import requests
import re
import json
from datetime import datetime
from urllib.parse import urlparse, urljoin, unquote
import sys
import time
import base64

class SportsStreamExtractor:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://sportzonline.st/'
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
            
            # Skip channel identifier lines
            if re.match(r'^(HD|BR|PT)\d+\s+(ENGLISH|BRAZILIAN|SPANISH|GERMAN|ITALIAN|POLISH|ROMANIAN)', line):
                continue
            
            # Parse event lines: TIME   Event Name | URL
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
                    existing_event['channels'].append({
                        'url': url,
                        'm3u8_url': None,
                        'status': 'pending'
                    })
                else:
                    events.append({
                        'time': time_str,
                        'event_name': event_name,
                        'channels': [{
                            'url': url,
                            'm3u8_url': None,
                            'status': 'pending'
                        }],
                        'line_number': line_num
                    })
        
        print(f"\n✓ Parsed {len(events)} events")
        total_channels = sum(len(event['channels']) for event in events)
        print(f"  Total channels: {total_channels}")
        
        return events
    
    def decode_obfuscated_content(self, content):
        """Try to decode common obfuscation methods"""
        decoded_parts = []
        
        # Method 1: Detect and decode base64 encoded strings
        base64_pattern = r'(?:atob|base64_decode)\s*\(\s*["\']([A-Za-z0-9+/=]+)["\']\s*\)'
        base64_matches = re.findall(base64_pattern, content)
        for match in base64_matches:
            try:
                decoded = base64.b64decode(match).decode('utf-8', errors='ignore')
                decoded_parts.append(decoded)
            except:
                pass
        
        # Method 2: Detect packed JavaScript (eval(function(p,a,c,k,e,d)))
        packed_pattern = r'eval\(function\(p,a,c,k,e,d\).*?\}\((.*?)\)\)'
        packed_matches = re.findall(packed_pattern, content, re.DOTALL)
        if packed_matches:
            # We found packed code but can't easily unpack it without JS engine
            # Instead, look for patterns within the packed code
            pass
        
        # Method 3: Look for hex encoded strings
        hex_pattern = r'\\x([0-9a-fA-F]{2})'
        hex_matches = re.findall(hex_pattern, content)
        if hex_matches:
            try:
                hex_string = ''.join(chr(int(h, 16)) for h in hex_matches)
                decoded_parts.append(hex_string)
            except:
                pass
        
        # Method 4: URL encoded strings
        url_encoded_pattern = r'(?:decodeURIComponent|unescape)\s*\(\s*["\']([^"\']+)["\']\s*\)'
        url_matches = re.findall(url_encoded_pattern, content)
        for match in url_matches:
            try:
                decoded = unquote(match)
                decoded_parts.append(decoded)
            except:
                pass
        
        return ' '.join(decoded_parts) + ' ' + content
    
    def extract_m3u8_advanced(self, content, url):
        """Advanced M3U8 extraction with multiple methods"""
        
        # Decode any obfuscated content first
        full_content = self.decode_obfuscated_content(content)
        
        # Method 1: Direct .m3u8 URLs (most common)
        m3u8_patterns = [
            r'https?://[^\s<>"\'`]+\.m3u8(?:\?[^\s<>"\'`]*)?',
            r'["\']([^"\']*\.m3u8[^"\']*)["\']',
        ]
        
        for pattern in m3u8_patterns:
            matches = re.findall(pattern, full_content, re.IGNORECASE)
            if matches:
                for match in matches:
                    # Clean up the URL
                    m3u8_url = match.strip('"\'` ')
                    # Validate it's a proper URL
                    if m3u8_url.startswith('http') and '.m3u8' in m3u8_url:
                        # Prefer master playlists
                        if 'master' in m3u8_url.lower():
                            return m3u8_url
                        # Return first valid m3u8
                        return m3u8_url
        
        # Method 2: Look for common player configurations
        player_patterns = [
            r'source\s*:\s*["\']([^"\']+)["\']',
            r'file\s*:\s*["\']([^"\']+)["\']',
            r'src\s*:\s*["\']([^"\']+)["\']',
            r'hlsUrl\s*:\s*["\']([^"\']+)["\']',
            r'stream\s*:\s*["\']([^"\']+)["\']',
            r'video\s*:\s*["\']([^"\']+)["\']',
            r'playlist\s*:\s*["\']([^"\']+)["\']',
            r'url\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        ]
        
        for pattern in player_patterns:
            matches = re.findall(pattern, full_content, re.IGNORECASE)
            for match in matches:
                if '.m3u8' in match:
                    # Handle relative URLs
                    if match.startswith('//'):
                        return 'https:' + match
                    elif match.startswith('/'):
                        parsed = urlparse(url)
                        return f"{parsed.scheme}://{parsed.netloc}{match}"
                    elif match.startswith('http'):
                        return match
        
        # Method 3: Look for data attributes
        data_patterns = [
            r'data-src=["\']([^"\']+)["\']',
            r'data-url=["\']([^"\']+)["\']',
            r'data-file=["\']([^"\']+)["\']',
            r'data-stream=["\']([^"\']+)["\']',
        ]
        
        for pattern in data_patterns:
            matches = re.findall(pattern, full_content, re.IGNORECASE)
            for match in matches:
                if '.m3u8' in match or 'stream' in match.lower():
                    if match.startswith('http'):
                        return match
        
        # Method 4: Look for fetch/ajax calls with potential stream URLs
        fetch_patterns = [
            r'fetch\s*\(\s*["\']([^"\']+)["\']',
            r'ajax\s*\(\s*[{]?\s*url\s*:\s*["\']([^"\']+)["\']',
            r'\.get\s*\(\s*["\']([^"\']+)["\']',
        ]
        
        for pattern in fetch_patterns:
            matches = re.findall(pattern, full_content, re.IGNORECASE)
            for match in matches:
                if any(x in match.lower() for x in ['stream', 'play', 'm3u8', 'video']):
                    if match.startswith('http'):
                        return match
        
        return None
    
    def extract_m3u8_from_page(self, url):
        """Extract M3U8 URL from channel page"""
        try:
            print(f"    Fetching: {url[:70]}...")
            
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            response.raise_for_status()
            
            content = response.text
            
            # Try advanced extraction on main page
            m3u8_url = self.extract_m3u8_advanced(content, url)
            if m3u8_url:
                print(f"    ✓ Found M3U8 in main page: {m3u8_url[:70]}")
                return m3u8_url
            
            # If not found, try to extract and follow iframe
            iframe_patterns = [
                r'<iframe[^>]+src=["\']([^"\']+)["\']',
                r'<iframe[^>]+src=([^\s>]+)',
            ]
            
            iframe_url = None
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
                    break
            
            if iframe_url:
                print(f"    → Following iframe: {iframe_url[:70]}...")
                time.sleep(0.3)  # Small delay
                
                try:
                    iframe_response = requests.get(iframe_url, headers=self.headers, timeout=15, allow_redirects=True)
                    iframe_response.raise_for_status()
                    
                    iframe_content = iframe_response.text
                    m3u8_url = self.extract_m3u8_advanced(iframe_content, iframe_url)
                    
                    if m3u8_url:
                        print(f"    ✓ Found M3U8 in iframe: {m3u8_url[:70]}")
                        return m3u8_url
                except Exception as e:
                    print(f"    ✗ Error fetching iframe: {e}")
            
            print(f"    ✗ No M3U8 found")
            return None
            
        except Exception as e:
            print(f"    ✗ Error: {e}")
            return None
    
    def process_events(self, events, max_channels_per_event=3):
        """Process all events and extract M3U8 URLs"""
        total_channels = sum(len(event['channels']) for event in events)
        processed = 0
        
        print(f"\nProcessing {len(events)} events with {total_channels} total channels")
        print(f"(Limiting to {max_channels_per_event} channels per event)\n")
        
        for event_idx, event in enumerate(events, 1):
            print(f"[{event_idx}/{len(events)}] {event['time']} - {event['event_name'][:50]}")
            
            channels_to_process = event['channels'][:max_channels_per_event]
            
            for channel_idx, channel in enumerate(channels_to_process, 1):
                processed += 1
                print(f"  [{channel_idx}/{len(channels_to_process)}]", end=" ")
                
                m3u8_url = self.extract_m3u8_from_page(channel['url'])
                
                if m3u8_url:
                    channel['m3u8_url'] = m3u8_url
                    channel['status'] = 'success'
                else:
                    channel['status'] = 'failed'
                
                # Rate limiting
                time.sleep(0.8)
            
            print()  # Empty line between events
        
        print(f"✓ Processed {processed} channels")
        return events
    
    def save_to_json(self, events, filename='streams_data.json'):
        """Save extracted data to JSON file"""
        total_channels = sum(len(event['channels']) for event in events)
        successful = sum(1 for event in events for ch in event['channels'] if ch['status'] == 'success')
        failed = sum(1 for event in events for ch in event['channels'] if ch['status'] == 'failed')
        
        output = {
            'extracted_at': datetime.utcnow().isoformat() + 'Z',
            'total_events': len(events),
            'total_channels': total_channels,
            'statistics': {
                'successful': successful,
                'failed': failed,
                'success_rate': f"{(successful/total_channels*100):.1f}%" if total_channels > 0 else "0%"
            },
            'events': events
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*60}")
        print(f"✓ Data saved to {filename}")
        print(f"{'='*60}")
        print(f"Events: {len(events)}")
        print(f"Total channels processed: {total_channels}")
        print(f"Successful extractions: {successful} ({(successful/total_channels*100):.1f}%)")
        print(f"Failed extractions: {failed}")
        print(f"{'='*60}\n")
        
        return filename

def main():
    prog_url = "https://sportsonline.sn/prog.txt"
    
    print("=" * 60)
    print("Advanced Sports Stream Extractor")
    print("=" * 60)
    print(f"Source: {prog_url}\n")
    
    extractor = SportsStreamExtractor()
    
    # Fetch prog.txt
    content = extractor.fetch_prog_data(prog_url)
    if not content:
        print("\n✗ Failed to fetch prog.txt")
        sys.exit(1)
    
    # Parse events
    events = extractor.parse_prog_file(content)
    
    if not events:
        print("\n✗ No events found")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"Starting extraction for {len(events)} events")
    print(f"{'='*60}\n")
    
    # Process events
    processed_events = extractor.process_events(events)
    
    # Save results
    extractor.save_to_json(processed_events)

if __name__ == "__main__":
    main()
