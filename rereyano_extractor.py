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
    
    def extract_iframe_from_player(self, player_url: str) -> Optional[str]:
        """Extract the main iframe URL from a player page"""
        try:
            headers = {
                "User-Agent": self.user_agent,
                "Referer": self.base_url,
            }
            
            print(f"    🔍 Getting iframe from player page...")
            
            r = requests.get(player_url, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            
            content = r.text
            
            # Parse HTML
            soup = BeautifulSoup(content, "html.parser")
            
            # Find all iframes
            iframes = soup.find_all("iframe")
            
            # Also search in JavaScript/HTML source
            iframe_patterns = [
                r'<iframe[^>]+src=["\']([^"\']+)["\']',
                r'iframe.*?src\s*=\s*["\']([^"\']+)["\']',
            ]
            
            iframe_urls = []
            
            # From HTML tags
            for iframe in iframes:
                src = iframe.get("src") or iframe.get("data-src")
                if src:
                    iframe_urls.append(src)
            
            # From regex patterns
            for pattern in iframe_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
                iframe_urls.extend(matches)
            
            # Filter and normalize
            skip_domains = ['google', 'doubleclick', 'facebook', 'analytics']
            
            for iframe_url in iframe_urls:
                # Normalize URL
                if iframe_url.startswith("//"):
                    iframe_url = "https:" + iframe_url
                elif iframe_url.startswith("/"):
                    iframe_url = urljoin(player_url, iframe_url)
                elif not iframe_url.startswith("http"):
                    continue
                
                # Skip ads
                if any(skip in iframe_url.lower() for skip in skip_domains):
                    continue
                
                print(f"    ✅ Found iframe: {iframe_url[:70]}...")
                return iframe_url
            
            print(f"    ❌ No iframe found")
            return None
            
        except Exception as e:
            print(f"    ❌ Error extracting iframe: {e}")
            return None
    
    def extract_m3u8_from_iframe(self, iframe_url: str, player_url: str) -> Optional[str]:
        """
        Extract M3U8 URL from iframe content
        This scans the iframe page for the actual M3U8 stream URL
        """
        try:
            headers = {
                "User-Agent": self.user_agent,
                "Referer": player_url,
                "Accept": "*/*",
            }
            
            print(f"    🔍 Extracting M3U8 from iframe...")
            
            r = requests.get(iframe_url, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            
            content = r.text
            
            # === METHOD 1: Direct M3U8 URL patterns ===
            m3u8_patterns = [
                # Standard patterns with quotes
                r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']',
                r'source["\']?\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'file["\']?\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'src["\']?\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'url["\']?\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'hls["\']?\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'playlist["\']?\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'stream["\']?\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                # Without quotes (catches URLs in plain text/JS)
                r'(https?://[^\s\'"()<>]+\.m3u8[^\s\'"()<>]*)',
            ]
            
            for pattern in m3u8_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    m3u8_url = match.strip()
                    
                    # Skip false positives
                    if any(skip in m3u8_url.lower() for skip in ['example', 'test', 'placeholder']):
                        continue
                    
                    # Must have .m3u8
                    if '.m3u8' in m3u8_url:
                        # Handle relative URLs
                        if not m3u8_url.startswith('http'):
                            m3u8_url = urljoin(iframe_url, m3u8_url)
                        
                        print(f"    ✅ Found M3U8: {m3u8_url[:80]}...")
                        return m3u8_url
            
            # === METHOD 2: Base64 encoded M3U8 ===
            base64_patterns = [
                r'atob\(["\']([A-Za-z0-9+/=]{30,})["\']',
                r'base64[,\s]+["\']([A-Za-z0-9+/=]{30,})["\']',
            ]
            
            for pattern in base64_patterns:
                matches = re.findall(pattern, content)
                for b64_str in matches:
                    try:
                        import base64
                        decoded = base64.b64decode(b64_str).decode('utf-8', errors='ignore')
                        
                        if '.m3u8' in decoded:
                            # Extract URL from decoded content
                            url_match = re.search(r'https?://[^\s\'"]+\.m3u8[^\s\'"]*', decoded)
                            if url_match:
                                m3u8_url = url_match.group(0)
                                print(f"    ✅ Found M3U8 (base64): {m3u8_url[:80]}...")
                                return m3u8_url
                    except:
                        continue
            
            # === METHOD 3: Check for API calls ===
            api_patterns = [
                r'fetch\(["\']([^"\']+)["\']',
                r'ajax.*?url\s*:\s*["\']([^"\']+)["\']',
                r'XMLHttpRequest.*?open\([^)]*["\']([^"\']+)["\']',
                r'["\']([^"\']*(?:api|stream|get|load)[^"\']*\.(?:php|json|txt)[^"\']*)["\']',
            ]
            
            api_urls = set()
            for pattern in api_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    if 'http' in match or match.startswith('/'):
                        api_urls.add(match)
            
            # Try API URLs (limit to 3)
            for api_url in list(api_urls)[:3]:
                if not api_url.startswith('http'):
                    api_url = urljoin(iframe_url, api_url)
                
                # Skip non-stream URLs
                skip = ['google', 'facebook', 'analytics', 'jquery', 'cloudflare']
                if any(s in api_url.lower() for s in skip):
                    continue
                
                try:
                    print(f"    🔄 Trying API: {api_url[:50]}...")
                    api_response = requests.get(api_url, headers=headers, timeout=10)
                    
                    # Check if it's a direct M3U8 playlist
                    if api_response.text.strip().startswith('#EXTM3U'):
                        print(f"    ✅ Found M3U8 (direct API): {api_url[:80]}...")
                        return api_url
                    
                    # Check if response contains M3U8 URL
                    if '.m3u8' in api_response.text:
                        for pattern in m3u8_patterns[:5]:
                            api_matches = re.findall(pattern, api_response.text, re.IGNORECASE)
                            if api_matches:
                                m3u8_url = api_matches[0]
                                if not m3u8_url.startswith('http'):
                                    m3u8_url = urljoin(api_url, m3u8_url)
                                print(f"    ✅ Found M3U8 (from API): {m3u8_url[:80]}...")
                                return m3u8_url
                except:
                    continue
            
            # === METHOD 4: Look in external scripts ===
            soup = BeautifulSoup(content, "html.parser")
            scripts = soup.find_all("script", src=True)
            
            for script in scripts[:3]:  # Limit to first 3 scripts
                script_url = script.get("src")
                if not script_url:
                    continue
                
                if not script_url.startswith('http'):
                    script_url = urljoin(iframe_url, script_url)
                
                # Skip common libraries
                if any(lib in script_url.lower() for lib in ['jquery', 'bootstrap', 'angular', 'react']):
                    continue
                
                try:
                    print(f"    🔄 Checking script: {script_url[:50]}...")
                    script_response = requests.get(script_url, headers=headers, timeout=10)
                    
                    # Look for M3U8 in script content
                    for pattern in m3u8_patterns[:5]:
                        script_matches = re.findall(pattern, script_response.text, re.IGNORECASE)
                        if script_matches:
                            m3u8_url = script_matches[0]
                            if not m3u8_url.startswith('http'):
                                m3u8_url = urljoin(script_url, m3u8_url)
                            if '.m3u8' in m3u8_url:
                                print(f"    ✅ Found M3U8 (external script): {m3u8_url[:80]}...")
                                return m3u8_url
                except:
                    continue
            
            print(f"    ❌ No M3U8 found in iframe")
            return None
            
        except Exception as e:
            print(f"    ❌ Error extracting M3U8: {e}")
            return None
    
    def get_player_stream(self, player_name: str, player_url: str) -> Dict[str, Any]:
        """Get complete stream info for a player"""
        print(f"\n  📺 {player_name}: {player_url}")
        
        # Step 1: Extract iframe URL from player page
        iframe_url = self.extract_iframe_from_player(player_url)
        
        if not iframe_url:
            return {
                "name": player_name,
                "player_url": player_url,
                "iframe_url": None,
                "m3u8_url": None,
                "status": "no_iframe",
                "extracted_at": datetime.utcnow().isoformat()
            }
        
        # Step 2: Extract M3U8 from iframe
        m3u8_url = self.extract_m3u8_from_iframe(iframe_url, player_url)
        
        # Step 3: Test accessibility
        is_accessible = False
        if m3u8_url:
            is_accessible = self._test_m3u8_access(m3u8_url, iframe_url)
            print(f"    🎯 Accessible: {is_accessible}")
        
        return {
            "name": player_name,
            "player_url": player_url,
            "iframe_url": iframe_url,
            "m3u8_url": m3u8_url,
            "is_accessible": is_accessible,
            "status": "success" if m3u8_url else "no_m3u8",
            "extracted_at": datetime.utcnow().isoformat()
        }
    
    def _test_m3u8_access(self, m3u8_url: str, referer: str) -> bool:
        """Test if M3U8 URL is accessible"""
        try:
            headers = {
                "User-Agent": self.user_agent,
                "Referer": referer,
                "Accept": "*/*"
            }
            
            # Try HEAD first
            response = requests.head(m3u8_url, headers=headers, timeout=10, allow_redirects=True)
            if response.status_code == 200:
                return True
            
            # Try GET
            response = requests.get(m3u8_url, headers=headers, timeout=10, stream=True)
            
            # Check if it's a valid M3U8
            chunk = next(response.iter_content(1024), None)
            if chunk and response.status_code == 200:
                content = chunk.decode('utf-8', errors='ignore')
                if '#EXTM3U' in content or '#EXT-X-' in content:
                    return True
                return True
            
            return False
        except:
            return False
    
    def extract_player_streams(self) -> Dict[str, Dict[str, Any]]:
        """Extract M3U8 streams from all player URLs"""
        player_streams = {}
        
        print(f"\n🎬 Extracting streams from {len(self.players)} players...")
        
        for player_name, player_url in self.players.items():
            player_data = self.get_player_stream(player_name, player_url)
            player_streams[player_name] = player_data
            
            # Small delay between requests
            time.sleep(1)
        
        return player_streams
    
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
        m3u8_url = player_data.get('m3u8_url')
        if m3u8_url:
            m3u8_preview = m3u8_url[:70] + "..." if len(m3u8_url) > 70 else m3u8_url
        else:
            m3u8_preview = 'Not found'
        print(f"    {status} {player_name}: {m3u8_preview}")
    
    print(f"\n  💾 Data saved to: {output_file}")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
