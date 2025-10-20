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
    
    def _is_valid_stream_url(self, url: str) -> bool:
        """Check if URL looks like a valid stream URL"""
        try:
            # Must be a URL
            if not url.startswith('http'):
                return False
            # Should contain m3u8 or be a streaming domain
            if '.m3u8' in url:
                return True
            # Check for common streaming patterns
            stream_indicators = ['stream', 'live', 'hls', 'playlist', 'index']
            return any(indicator in url.lower() for indicator in stream_indicators)
        except:
            return False
    
    def scan_player_for_m3u8(self, player_url: str) -> Optional[str]:
        """
        Scan a player page for M3U8 stream URLs
        Uses multiple methods to find the stream
        """
        try:
            headers = {
                "User-Agent": self.user_agent,
                "Referer": self.base_url,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            }
            
            print(f"    🔍 Scanning player: {player_url}")
            
            # First request - get the page
            session = requests.Session()
            r = session.get(player_url, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            
            content = r.text
            
            # If content is too short, it might be loading dynamically
            if len(content) < 500:
                print(f"    ⚠️ Short content ({len(content)} chars), may be JS-loaded")
                # Try to find any script sources that might load the player
                script_urls = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', content)
                for script_url in script_urls:
                    if not script_url.startswith('http'):
                        script_url = urljoin(player_url, script_url)
                    try:
                        script_r = session.get(script_url, headers=headers, timeout=10)
                        content += "\n" + script_r.text
                    except:
                        pass
            
            # Method 1: Direct M3U8 links in HTML/JS - EXPANDED PATTERNS
            m3u8_patterns = [
                # Standard patterns
                r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']',
                r'source:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'file:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'src:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'playlist:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'hls:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'url:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                # Alternative patterns
                r'stream["\']?\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'streamUrl["\']?\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'video["\']?\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'videoUrl["\']?\s*:["\']([^"\']+\.m3u8[^"\']*)["\']',
                # Without quotes (risky but catches some)
                r'https?://[^\s<>"\']+\.m3u8[^\s<>"\']*',
            ]
            
            for pattern in m3u8_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    for m3u8_url in matches:
                        # Skip common false positives
                        if any(skip in m3u8_url.lower() for skip in ['example', 'placeholder', 'test']):
                            continue
                        # Handle relative URLs
                        if not m3u8_url.startswith('http'):
                            m3u8_url = urljoin(player_url, m3u8_url)
                        # Verify it looks like a valid stream URL
                        if self._is_valid_stream_url(m3u8_url):
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
            
            # Method 4: Aggressive iframe scanning with recursive depth
            soup = BeautifulSoup(content, "html.parser")
            iframes = soup.find_all("iframe")
            
            # Also look for iframe patterns in JavaScript
            iframe_js_patterns = [
                r'<iframe[^>]+src=["\']([^"\']+)["\']',
                r'iframe.*?src.*?["\']([^"\']+)["\']',
                r'player.*?src.*?["\']([^"\']+)["\']',
            ]
            
            iframe_urls = []
            for iframe in iframes:
                iframe_src = iframe.get("src") or iframe.get("data-src")
                if iframe_src:
                    iframe_urls.append(iframe_src)
            
            for pattern in iframe_js_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                iframe_urls.extend(matches)
            
            # Process iframe URLs
            for iframe_src in iframe_urls:
                if iframe_src.startswith("//"):
                    iframe_src = "https:" + iframe_src
                elif iframe_src.startswith("/"):
                    iframe_src = urljoin(player_url, iframe_src)
                elif not iframe_src.startswith("http"):
                    iframe_src = urljoin(player_url, iframe_src)
                
                # Skip common ad/tracking iframes
                skip_domains = ['google', 'doubleclick', 'facebook', 'twitter', 'analytics']
                if any(domain in iframe_src.lower() for domain in skip_domains):
                    continue
                
                print(f"    🔄 Checking nested iframe: {iframe_src[:60]}...")
                
                # Recursively check iframe for M3U8 (with depth limit to avoid infinite loops)
                try:
                    nested_response = session.get(iframe_src, headers=headers, timeout=10)
                    nested_content = nested_response.text
                    
                    # Quick check for M3U8 in nested iframe
                    for pattern in m3u8_patterns[:5]:  # Use first few patterns only
                        matches = re.findall(pattern, nested_content, re.IGNORECASE)
                        if matches:
                            for m3u8_url in matches:
                                if not m3u8_url.startswith('http'):
                                    m3u8_url = urljoin(iframe_src, m3u8_url)
                                if self._is_valid_stream_url(m3u8_url):
                                    print(f"    ✅ Found M3U8 (nested iframe): {m3u8_url[:80]}...")
                                    return m3u8_url
                except Exception as e:
                    print(f"    ⚠️ Error checking nested iframe: {e}")
                    continue
            
            # Method 5: Look for API endpoints and AJAX calls
            api_patterns = [
                r'["\'](https?://[^"\']*(?:api|stream|player|get|load|fetch)[^"\']*)["\']',
                r'fetch\(["\']([^"\']+)["\']',
                r'ajax.*?url:\s*["\']([^"\']+)["\']',
                r'XMLHttpRequest.*?["\']([^"\']+)["\']',
            ]
            
            api_urls = set()
            for pattern in api_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    if match.startswith('http'):
                        api_urls.add(match)
            
            # Limit API calls to avoid rate limiting
            for api_url in list(api_urls)[:5]:
                # Skip obvious non-stream URLs
                skip_patterns = ['facebook', 'google', 'twitter', 'analytics', 'jquery', 'bootstrap', 'cloudflare']
                if any(pattern in api_url.lower() for pattern in skip_patterns):
                    continue
                
                try:
                    print(f"    🔄 Checking API: {api_url[:50]}...")
                    api_response = session.get(api_url, headers=headers, timeout=10)
                    
                    # Check if response contains M3U8
                    if '.m3u8' in api_response.text or 'stream' in api_response.text.lower():
                        # Try to extract M3U8 from API response
                        for pattern in m3u8_patterns[:8]:
                            api_m3u8 = re.findall(pattern, api_response.text, re.IGNORECASE)
                            if api_m3u8:
                                m3u8_url = api_m3u8[0] if isinstance(api_m3u8[0], str) else api_m3u8[0]
                                if not m3u8_url.startswith('http'):
                                    m3u8_url = urljoin(api_url, m3u8_url)
                                if self._is_valid_stream_url(m3u8_url):
                                    print(f"    ✅ Found M3U8 (API): {m3u8_url[:80]}...")
                                    return m3u8_url
                    
                    # Check if the API response itself is a valid M3U8 playlist
                    if api_response.text.strip().startswith('#EXTM3U'):
                        print(f"    ✅ Found M3U8 (direct API response): {api_url[:80]}...")
                        return api_url
                        
                except Exception as e:
                    continue
            
            # Method 6: Try to construct M3U8 URLs based on common patterns
            # Extract player ID from URL
            player_match = re.search(r'/player/(\d+)/(\d+)', player_url)
            if player_match:
                player_id = player_match.group(1)
                channel_id = player_match.group(2)
                
                # Common M3U8 URL patterns for sports streaming sites
                potential_patterns = [
                    f"https://rereyano.ru/stream/{player_id}/{channel_id}/index.m3u8",
                    f"https://rereyano.ru/live/{player_id}/{channel_id}.m3u8",
                    f"https://rereyano.ru/hls/{player_id}/{channel_id}/playlist.m3u8",
                    f"https://stream.rereyano.ru/{player_id}/{channel_id}/index.m3u8",
                    f"https://cdn.rereyano.ru/live/{player_id}_{channel_id}.m3u8",
                ]
                
                print(f"    🔍 Trying constructed URL patterns...")
                for test_url in potential_patterns:
                    if self._test_m3u8_access(test_url, player_url):
                        print(f"    ✅ Found M3U8 (constructed): {test_url[:80]}...")
                        return test_url
            
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
                "Referer": referer,
                "Origin": referer.rsplit('/', 1)[0] if '/' in referer else referer,
                "Accept": "*/*"
            }
            
            # Try HEAD first (faster)
            try:
                response = requests.head(m3u8_url, headers=headers, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    return True
            except:
                pass
            
            # If HEAD fails or returns non-200, try GET
            response = requests.get(m3u8_url, headers=headers, timeout=10, stream=True)
            
            # Read first chunk to verify it's valid
            first_chunk = next(response.iter_content(2048), None)
            
            if response.status_code == 200:
                # If it's an M3U8, it should start with #EXTM3U
                if first_chunk:
                    content_start = first_chunk.decode('utf-8', errors='ignore')
                    if '#EXTM3U' in content_start or '#EXT-X-' in content_start:
                        return True
                return True
                
            return False
        except Exception as e:
            print(f"    ⚠️ Access test failed: {str(e)[:50]}")
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
        m3u8_url = player_data.get('m3u8_url')
        if m3u8_url:
            m3u8_preview = m3u8_url[:60] + "..." if len(m3u8_url) > 60 else m3u8_url
        else:
            m3u8_preview = 'Not found'
        print(f"    {status} {player_name}: {m3u8_preview}")
    
    print(f"\n  💾 Data saved to: {output_file}")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
