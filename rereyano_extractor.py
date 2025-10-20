import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse
import time

class RereYanoExtractor:
    def __init__(self):
        self.base_url = "https://rereyano.ru"
        self.name = "RereYano"
        self.timeout = 30
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        # Player URLs mapping
        self.players = {
            "Cartel": f"{self.base_url}/player/1/1",
            "hoca": f"{self.base_url}/player/2/1",
            "Caster": f"{self.base_url}/player/3/1",
            "WIGI": f"{self.base_url}/player/4/1"
        }
    
    def parse_event_line(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Parse event line like:
        20-10-2025 (15:00) Pro League : Standard Liège - Antwerp  (CH153fr)
        """
        try:
            # Pattern: DATE (TIME) LEAGUE : TEAMS (CHANNELS)
            pattern = r'(\d{2}-\d{2}-\d{4})\s+\((\d{2}:\d{2})\)\s+([^:]+):\s+([^(]+)\s+(\(CH\d+\w+\)(?:\s*\(CH\d+\w+\))*)'
            
            match = re.match(pattern, line.strip())
            if not match:
                return None
            
            date_str, time_str, league, teams, channels_str = match.groups()
            
            # Extract all channels
            channels = re.findall(r'CH(\d+)(\w+)', channels_str)
            
            event = {
                "date": date_str,
                "time": time_str,
                "datetime": f"{date_str} {time_str}",
                "league": league.strip(),
                "teams": teams.strip(),
                "channels": [{"id": ch_id, "lang": lang} for ch_id, lang in channels],
                "raw_line": line.strip()
            }
            
            return event
        except Exception as e:
            print(f"    ⚠️ Error parsing line: {e}")
            return None
    
    def get_events(self) -> List[Dict[str, Any]]:
        """Extract all events from the main page"""
        events = []
        
        try:
            print(f"🔍 Fetching events from {self.base_url}...")
            
            headers = {
                "User-Agent": self.user_agent
            }
            r = requests.get(self.base_url, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            
            # Parse the plain text content
            content = r.text
            
            # Split by lines
            lines = content.split('\n')
            
            event_count = 0
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check if line looks like an event (starts with date)
                if re.match(r'\d{2}-\d{2}-\d{4}', line):
                    event = self.parse_event_line(line)
                    if event:
                        event_count += 1
                        events.append(event)
                        print(f"  ✅ [{event_count}] {event['teams']} - {event['league']}")
            
            print(f"\n✅ Successfully extracted {len(events)} events")
            
        except requests.RequestException as e:
            print(f"❌ Request error: {e}")
        except Exception as e:
            print(f"❌ Extraction error: {e}")
        
        return events
    
    def scan_player_for_m3u8(self, player_url: str) -> Optional[str]:
        """
        Scan a player page for M3U8 stream URLs
        Uses multiple methods to find the stream
        """
        try:
            headers = {
                "User-Agent": self.user_agent,
                "Referer": self.base_url
            }
            
            print(f"    🔍 Scanning player: {player_url}")
            r = requests.get(player_url, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            
            content = r.text
            
            # Method 1: Direct M3U8 links in HTML/JS
            m3u8_patterns = [
                r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']',
                r'source:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'src:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'playlist:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'hls:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'url:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            ]
            
            for pattern in m3u8_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    m3u8_url = matches[0]
                    # Handle relative URLs
                    if not m3u8_url.startswith('http'):
                        m3u8_url = urljoin(player_url, m3u8_url)
                    print(f"    ✅ Found M3U8 (direct): {m3u8_url[:80]}...")
                    return m3u8_url
            
            # Method 2: Base64 encoded M3U8
            base64_pattern = r'atob\(["\']([A-Za-z0-9+/=]+)["\']\)'
            base64_matches = re.findall(base64_pattern, content)
            for b64 in base64_matches:
                try:
                    import base64
                    decoded = base64.b64decode(b64).decode('utf-8')
                    if '.m3u8' in decoded or 'http' in decoded:
                        # Check if it's a URL
                        url_in_decoded = re.findall(r'https?://[^\s\'"]+', decoded)
                        if url_in_decoded:
                            potential_m3u8 = url_in_decoded[0]
                            if '.m3u8' in potential_m3u8 or 'stream' in potential_m3u8:
                                print(f"    ✅ Found M3U8 (base64): {potential_m3u8[:80]}...")
                                return potential_m3u8
                except:
                    continue
            
            # Method 3: JSON embedded data
            json_patterns = [
                r'"url":\s*"([^"]+\.m3u8[^"]*)"',
                r'"stream":\s*"([^"]+\.m3u8[^"]*)"',
                r'"hls":\s*"([^"]+\.m3u8[^"]*)"',
                r'"source":\s*"([^"]+\.m3u8[^"]*)"',
                r'"file":\s*"([^"]+\.m3u8[^"]*)"',
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    m3u8_url = matches[0].replace('\\/', '/')
                    if not m3u8_url.startswith('http'):
                        m3u8_url = urljoin(player_url, m3u8_url)
                    print(f"    ✅ Found M3U8 (JSON): {m3u8_url[:80]}...")
                    return m3u8_url
            
            # Method 4: Check for iframes that might contain streams
            soup = BeautifulSoup(content, "html.parser")
            iframes = soup.find_all("iframe")
            
            for iframe in iframes:
                iframe_src = iframe.get("src") or iframe.get("data-src")
                if iframe_src:
                    if iframe_src.startswith("//"):
                        iframe_src = "https:" + iframe_src
                    elif iframe_src.startswith("/"):
                        iframe_src = urljoin(player_url, iframe_src)
                    
                    # Recursively check iframe for M3U8
                    print(f"    🔄 Checking nested iframe: {iframe_src[:60]}...")
                    nested_m3u8 = self.scan_player_for_m3u8(iframe_src)
                    if nested_m3u8:
                        return nested_m3u8
            
            # Method 5: Look for API endpoints
            api_patterns = [
                r'["\'](https?://[^"\']*(?:api|stream|player|get)[^"\']*)["\']',
            ]
            
            for pattern in api_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for api_url in matches[:3]:  # Limit to first 3 to avoid too many requests
                    try:
                        if 'facebook' in api_url or 'google' in api_url or 'twitter' in api_url:
                            continue
                        
                        api_response = requests.get(api_url, headers=headers, timeout=10)
                        if '.m3u8' in api_response.text:
                            api_m3u8 = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', api_response.text)
                            if api_m3u8:
                                print(f"    ✅ Found M3U8 (API): {api_m3u8[0][:80]}...")
                                return api_m3u8[0]
                    except:
                        continue
            
            print(f"    ❌ No M3U8 found")
            return None
            
        except Exception as e:
            print(f"    ❌ Error scanning player: {e}")
            return None
    
    def extract_player_streams(self) -> Dict[str, Dict[str, Any]]:
        """Extract M3U8 streams from all player URLs"""
        player_streams = {}
        
        print(f"\n🎬 Extracting streams from {len(self.players)} players...")
        
        for player_name, player_url in self.players.items():
            print(f"\n  📺 {player_name}: {player_url}")
            
            m3u8_url = self.scan_player_for_m3u8(player_url)
            
            player_data = {
                "name": player_name,
                "player_url": player_url,
                "m3u8_url": m3u8_url,
                "extracted_at": datetime.utcnow().isoformat(),
                "status": "success" if m3u8_url else "not_found"
            }
            
            # Test accessibility if M3U8 found
            if m3u8_url:
                is_accessible = self._test_m3u8_access(m3u8_url, player_url)
                player_data["is_accessible"] = is_accessible
                print(f"    🎯 Accessible: {is_accessible}")
            
            player_streams[player_name] = player_data
            
            # Small delay to avoid rate limiting
            time.sleep(1)
        
        return player_streams
    
    def _test_m3u8_access(self, m3u8_url: str, referer: str) -> bool:
        """Test if the M3U8 URL is accessible"""
        try:
            headers = {
                "User-Agent": self.user_agent,
                "Referer": referer
            }
            response = requests.head(m3u8_url, headers=headers, timeout=10, allow_redirects=True)
            if response.status_code == 200:
                return True
            
            # If HEAD fails, try GET
            response = requests.get(m3u8_url, headers=headers, timeout=10, stream=True)
            next(response.iter_content(1024), None)
            return response.status_code == 200
        except:
            return False
    
    def create_full_dataset(self) -> Dict[str, Any]:
        """Create complete dataset with events and player streams"""
        print("="*60)
        print("🏆 RereYano Sports Stream Extractor")
        print("="*60 + "\n")
        
        # Extract events
        events = self.get_events()
        
        # Extract player streams
        player_streams = self.extract_player_streams()
        
        # Count successful extractions
        m3u8_count = sum(1 for p in player_streams.values() if p.get('m3u8_url'))
        accessible_count = sum(1 for p in player_streams.values() if p.get('is_accessible'))
        
        # Prepare output
        output_data = {
            "extractor": "RereYano",
            "website": self.base_url,
            "last_updated": datetime.utcnow().isoformat(),
            "total_events": len(events),
            "total_players": len(player_streams),
            "m3u8_extracted": m3u8_count,
            "accessible_streams": accessible_count,
            "events": events,
            "player_streams": player_streams,
            "player_urls": self.players
        }
        
        return output_data

def main():
    extractor = RereYanoExtractor()
    
    # Create full dataset
    data = extractor.create_full_dataset()
    
    # Save to JSON
    output_file = 'rereyano_data.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Print summary
    print("\n" + "="*60)
    print("📊 Extraction Summary:")
    print("="*60)
    print(f"  📅 Total Events: {data['total_events']}")
    print(f"  📺 Total Players: {data['total_players']}")
    print(f"  🎬 M3U8 Extracted: {data['m3u8_extracted']}")
    print(f"  ✅ Accessible: {data['accessible_streams']}")
    
    print(f"\n  Player Streams:")
    for player_name, player_data in data['player_streams'].items():
        status = "✅" if player_data.get('m3u8_url') else "❌"
        m3u8_preview = player_data.get('m3u8_url', 'Not found')
        if m3u8_preview != 'Not found':
            m3u8_preview = m3u8_preview[:60] + "..."
        print(f"    {status} {player_name}: {m3u8_preview}")
    
    print(f"\n  💾 Data saved to: {output_file}")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
