#!/usr/bin/env python3
"""
YouTube Shorts Agent - Downloads shorts from specified channels using yt-dlp.

Features:
- Downloads YouTube Shorts from configured channels
- Tracks downloaded videos to avoid duplicates
- Monitors channels for new shorts
- Can be run periodically or triggered manually
- Supports multiple channels
- Configurable download directory and quality settings
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import quote

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        pass  # Optional dependency

try:
    from tqdm import tqdm
except ImportError:
    # Fallback if tqdm is not installed
    def tqdm(iterable=None, desc=None, total=None, unit=None, **kwargs):
        if iterable is None:
            class FakeTqdm:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
                def update(self, n=1):
                    pass
                def set_description(self, desc=None):
                    pass
            return FakeTqdm()
        return iterable

try:
    import boto3
    from botocore.exceptions import ClientError, BotoCoreError
except ImportError:
    boto3 = None
    ClientError = Exception
    BotoCoreError = Exception

try:
    import requests
except ImportError:
    requests = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ChannelConfig:
    """Configuration for a YouTube channel."""
    channel_id: str  # Channel ID or handle (e.g., @channelname or UC...)
    name: str  # Friendly name for logging
    enabled: bool = True


@dataclass
class DownloadedVideo:
    """Metadata for a downloaded video."""
    video_id: str
    channel_id: str
    title: str
    url: str
    downloaded_at: str
    file_path: str
    s3_url: Optional[str] = None


class YouTubeShortsAgent:
    """Agent for downloading YouTube Shorts from channels."""
    
    def __init__(
        self,
        download_dir: Path,
        history_file: Path,
        channels: List[ChannelConfig],
        *,
        max_downloads: int = 0,  # 0 = unlimited
        quality: str = "best",
        format_filter: str = "short",  # Filter for shorts only
    ):
        self.download_dir = download_dir
        self.history_file = history_file
        self.channels = [ch for ch in channels if ch.enabled]
        self.max_downloads = max_downloads
        self.quality = quality
        self.format_filter = format_filter
        
        # Ensure directories exist
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load download history
        self.downloaded_videos: Set[str] = self._load_history()
        self.cms_uploaded_videos: Set[str] = self._load_cms_history()
        
        # Initialize S3 and CMS clients if credentials are available
        self.s3_client = None
        self.s3_bucket = None
        self.s3_key_prefix = None
        self.s3_region = None
        self._init_s3()
        
        self.cms_base_url = None
        self.cms_auth_token = None
        self._init_cms()
    
    def _init_s3(self) -> None:
        """Initialize S3 client if credentials are available."""
        if boto3 is None:
            logger.warning("boto3 not installed. S3 upload will be skipped.")
            return
        
        access_key_id = os.getenv("S3_ACCESS_KEY_ID")
        secret_access_key = os.getenv("S3_SECRET_ACCESS_KEY")
        bucket = os.getenv("S3_BUCKET")
        key_prefix = os.getenv("S3_KEY_PREFIX", "")
        region = os.getenv("S3_REGION", "us-east-1")
        
        if not all([access_key_id, secret_access_key, bucket]):
            logger.warning("S3 credentials not found in environment. S3 upload will be skipped.")
            return
        
        try:
            # Create initial client to get bucket region
            temp_client = boto3.client(
                's3',
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name=region
            )
            
            # Get actual bucket region
            try:
                bucket_location = temp_client.get_bucket_location(Bucket=bucket)
                actual_region = bucket_location.get('LocationConstraint')
                # If LocationConstraint is None or empty, it means us-east-1
                if not actual_region:
                    actual_region = "us-east-1"
                # Recreate client with correct region
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=access_key_id,
                    aws_secret_access_key=secret_access_key,
                    region_name=actual_region
                )
                self.s3_region = actual_region
                logger.info(f"Detected bucket region: {actual_region}")
            except Exception as e:
                # Fallback to provided region if we can't detect it
                logger.warning(f"Could not detect bucket region, using {region}: {e}")
                self.s3_client = temp_client
                self.s3_region = region
            
            self.s3_bucket = bucket
            self.s3_key_prefix = key_prefix.rstrip('/')
            logger.info(f"S3 initialized: bucket={bucket}, prefix={key_prefix}, region={self.s3_region}")
        except Exception as exc:
            logger.error(f"Failed to initialize S3 client: {exc}")
            self.s3_client = None
            self.s3_region = None
    
    def _init_cms(self) -> None:
        """Initialize CMS configuration if available."""
        if requests is None:
            logger.warning("requests not installed. CMS integration will be skipped.")
            return
        
        base_url = os.getenv("YT_CMS_BASE_URL")
        auth_token = os.getenv("YT_CMS_AUTH_TOKEN")
        
        if not base_url or not auth_token:
            logger.warning("CMS credentials not found in environment. CMS integration will be skipped.")
            return
        
        self.cms_base_url = base_url.rstrip('/')
        self.cms_auth_token = auth_token
        logger.info(f"CMS initialized: base_url={base_url}")
    
    def _upload_to_s3(self, file_path: Path, video_id: str) -> Optional[str]:
        """Upload a video file to S3 and return the S3 URL."""
        if not self.s3_client or not self.s3_bucket:
            return None
        
        try:
            # Construct S3 key
            filename = file_path.name
            s3_key = f"{self.s3_key_prefix}/{filename}" if self.s3_key_prefix else filename
            
            # Upload file
            logger.info(f"Uploading {filename} to S3...")
            self.s3_client.upload_file(
                str(file_path),
                self.s3_bucket,
                s3_key,
                ExtraArgs={'ContentType': 'video/mp4'}
            )
            
            # Construct S3 URL (always use standard format without region)
            encoded_key = quote(s3_key, safe='/')
            s3_url = f"https://{self.s3_bucket}.s3.amazonaws.com/{encoded_key}"
            
            logger.info(f"✅ Uploaded to S3: {s3_url}")
            
            # Delete local file after successful S3 upload
            try:
                file_path.unlink()
                logger.info(f"🗑️  Deleted local file: {filename}")
            except OSError as exc:
                logger.warning(f"Failed to delete local file {filename}: {exc}")
            
            return s3_url
            
        except (ClientError, BotoCoreError, OSError) as exc:
            logger.error(f"Failed to upload {file_path} to S3: {exc}")
            return None
    
    def _check_video_in_cms(self, youtube_url: str) -> bool:
        """Check if video already exists in CMS by YouTube URL."""
        if not self.cms_base_url or not self.cms_auth_token:
            return False
        
        if requests is None:
            return False
        
        try:
            # Query to check if video exists
            query = """
            query CheckYoutube($where: JSON!) {
                youtubes(where: $where, limit: 1) {
                    id
                    originalYtLink
                }
            }
            """
            
            variables = {
                "where": {
                    "originalYtLink": youtube_url
                }
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": self.cms_auth_token
            }
            
            payload = {
                "query": query,
                "variables": variables
            }
            
            response = requests.post(
                self.cms_base_url,
                json=payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if "errors" in result:
                    logger.debug(f"CMS check error: {result['errors']}")
                    return False
                youtubes = result.get("data", {}).get("youtubes", [])
                return len(youtubes) > 0
            
            return False
        except Exception as exc:
            logger.debug(f"Error checking CMS: {exc}")
            return False
    
    def _save_to_cms(self, video: DownloadedVideo) -> bool:
        """Save video metadata (YouTube and S3 links) to CMS."""
        if not self.cms_base_url or not self.cms_auth_token:
            return False
        
        if requests is None:
            logger.warning("requests library not available. Cannot save to CMS.")
            return False
        
        # Only save to CMS if we have an S3 URL (bucketLink is required)
        if not video.s3_url:
            logger.warning(f"Skipping CMS save for {video.title}: No S3 URL available")
            return False
        
        # Check if already uploaded to CMS
        if video.video_id in self.cms_uploaded_videos:
            logger.info(f"⏭️  Skipping CMS save for {video.title}: Already uploaded")
            return True
        
        # Check if video exists in CMS by YouTube URL
        if self._check_video_in_cms(video.url):
            logger.info(f"⏭️  Skipping CMS save for {video.title}: Already exists in CMS")
            self.cms_uploaded_videos.add(video.video_id)
            self._save_cms_history(video.video_id)
            return True
        
        try:
            # GraphQL mutation to create YouTube record
            # Based on schema introspection:
            # - Mutation: createYoutube
            # - Input type: mutationYoutubeInput
            # - Required fields: originalYtLink, bucketLink
            # - Status: _status enum (draft or published)
            mutation = """
            mutation CreateYoutube($data: mutationYoutubeInput!) {
                createYoutube(data: $data, draft: false) {
                    id
                    originalYtLink
                    bucketLink
                    createdAt
                }
            }
            """
            
            # Build variables matching the schema
            variables = {
                "data": {
                    "originalYtLink": video.url,
                    "bucketLink": video.s3_url,  # Required field
                    "_status": "published"  # Publish the video
                }
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": self.cms_auth_token
            }
            
            payload = {
                "query": mutation,
                "variables": variables
            }
            
            response = requests.post(
                self.cms_base_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if "errors" in result:
                    logger.error(f"CMS error: {result['errors']}")
                    return False
                logger.info(f"✅ Saved to CMS: {video.title}")
                # Track successful CMS upload
                self.cms_uploaded_videos.add(video.video_id)
                self._save_cms_history(video.video_id)
                return True
            else:
                logger.error(f"CMS request failed: {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.RequestException as exc:
            logger.error(f"Failed to save to CMS: {exc}")
            return False
        except Exception as exc:
            logger.error(f"Unexpected error saving to CMS: {exc}")
            return False
    
    def _load_cms_history(self) -> Set[str]:
        """Load videos that have been uploaded to CMS."""
        if not self.history_file.exists():
            return set()
        
        try:
            with self.history_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                # Get videos that have s3_url (meaning they were uploaded)
                cms_videos = {
                    video["video_id"] 
                    for video in data.get("videos", []) 
                    if video.get("s3_url") and video.get("s3_url") != None
                }
                return cms_videos
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            logger.warning(f"Failed to load CMS history: {exc}")
            return set()
    
    def _save_cms_history(self, video_id: str) -> None:
        """Mark a video as uploaded to CMS in history file."""
        if not self.history_file.exists():
            return
        
        try:
            with self.history_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Update the video entry to mark as CMS uploaded
            videos = data.get("videos", [])
            for video in videos:
                if video.get("video_id") == video_id:
                    video["cms_uploaded"] = True
                    break
            
            with self.history_file.open("w", encoding="utf-8") as f:
                json.dump({"videos": videos, "last_updated": datetime.now().isoformat()}, f, indent=2)
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug(f"Failed to save CMS history: {exc}")
    
    def _load_history(self) -> Set[str]:
        """Load previously downloaded video IDs from history file."""
        if not self.history_file.exists():
            return set()
        
        try:
            with self.history_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return {video["video_id"] for video in data.get("videos", [])}
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            logger.warning(f"Failed to load history file: {exc}. Starting fresh.")
            return set()
    
    def _save_history(self, video: DownloadedVideo) -> None:
        """Append a downloaded video to history."""
        videos = []
        if self.history_file.exists():
            try:
                with self.history_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    videos = data.get("videos", [])
            except (json.JSONDecodeError, OSError):
                videos = []
        
        videos.append(asdict(video))
        
        try:
            with self.history_file.open("w", encoding="utf-8") as f:
                json.dump({"videos": videos, "last_updated": datetime.now().isoformat()}, f, indent=2)
        except OSError as exc:
            logger.error(f"Failed to save history: {exc}")
    
    def _check_yt_dlp_installed(self) -> bool:
        """Check if yt-dlp is installed."""
        try:
            result = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def _get_channel_videos(self, channel_config: ChannelConfig, max_results: int = 50) -> List[Dict[str, str]]:
        """Fetch recent videos from a channel using yt-dlp."""
        # Handle different channel ID formats
        channel_id = channel_config.channel_id
        
        # If it's already a full URL (including /shorts), use it directly
        if channel_id.startswith("http://") or channel_id.startswith("https://"):
            channel_url = channel_id
        # If it's a shorts URL path, use it directly
        elif "/shorts" in channel_id:
            if channel_id.startswith("/"):
                channel_url = f"https://www.youtube.com{channel_id}"
            elif channel_id.startswith("@"):
                channel_url = f"https://www.youtube.com/{channel_id}/shorts"
            else:
                channel_url = f"https://www.youtube.com/{channel_id}/shorts"
        # Handle @channelname format
        elif channel_id.startswith("@"):
            # Prefer shorts page if available
            channel_url = f"https://www.youtube.com/{channel_id}/shorts"
        # Handle UC channel ID format
        elif channel_id.startswith("UC"):
            channel_url = f"https://www.youtube.com/channel/{channel_id}"
        else:
            # Assume it's a channel handle or ID
            channel_url = f"https://www.youtube.com/{channel_id}/shorts"
        
        # Use yt-dlp to get channel video list with JSON output
        # First, get playlist info
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--print", "%(id)s|%(title)s|%(duration)s",
            "--no-download",
            "--playlist-end", str(max_results),
            channel_url
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to fetch videos from {channel_config.name}: {result.stderr}")
                return []
            
            videos = []
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if not line or "|" not in line:
                    continue
                
                parts = line.split("|", 2)
                if len(parts) < 2:
                    continue
                
                video_id = parts[0].strip()
                title = parts[1].strip() if len(parts) > 1 else ""
                duration_str = parts[2].strip() if len(parts) > 2 else "0"
                
                # Parse duration (can be in seconds or HH:MM:SS format)
                duration = 0
                try:
                    if ":" in duration_str:
                        # HH:MM:SS or MM:SS format
                        time_parts = duration_str.split(":")
                        if len(time_parts) == 3:
                            duration = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2])
                        elif len(time_parts) == 2:
                            duration = int(time_parts[0]) * 60 + int(time_parts[1])
                    else:
                        duration = float(duration_str)
                except (ValueError, IndexError):
                    # If duration parsing fails, we'll fetch full info for this video
                    duration = None
                
                # Filter for shorts (duration <= 60 seconds or None to check later)
                if duration is None or duration <= 60:
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    videos.append({
                        "id": video_id,
                        "title": title,
                        "url": video_url,
                        "duration": duration,
                    })
            
            # If we got videos but some have unknown duration, fetch full info
            # This is needed because flat-playlist might not have duration
            if videos:
                # Fetch detailed info for videos with unknown duration
                videos_to_check = [v for v in videos if v.get("duration") is None]
                if videos_to_check:
                    logger.info(f"Fetching detailed info for {len(videos_to_check)} video(s)...")
                    checked_videos = self._get_video_details(videos_to_check)
                    # Update videos list with checked durations
                    for i, video in enumerate(videos):
                        if video.get("duration") is None:
                            checked = next((v for v in checked_videos if v["id"] == video["id"]), None)
                            if checked:
                                video["duration"] = checked.get("duration", 0)
                    
                    # Re-filter to only include shorts
                    videos = [v for v in videos if v.get("duration", 0) <= 60]
            
            return videos
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout fetching videos from {channel_config.name}")
            return []
        except Exception as exc:
            logger.error(f"Error fetching videos from {channel_config.name}: {exc}")
            return []
    
    def _get_video_details(self, videos: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Get detailed info for videos (including duration)."""
        checked = []
        with tqdm(total=len(videos), desc="Fetching video details", unit="video") as pbar:
            for video in videos:
                try:
                    cmd = [
                        "yt-dlp",
                        "--dump-json",
                        "--no-download",
                        video["url"]
                    ]
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        duration = data.get("duration", 0)
                        checked.append({
                            "id": video["id"],
                            "title": data.get("title", video["title"]),
                            "url": video["url"],
                            "duration": duration,
                        })
                except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError) as exc:
                    logger.debug(f"Could not get details for {video['id']}: {exc}")
                finally:
                    pbar.update(1)
        return checked
    
    
    def _download_video(
        self,
        video_id: str,
        video_url: str,
        video_title: str,
        channel_config: ChannelConfig,
        pbar: Optional[tqdm] = None
    ) -> Optional[Path]:
        """Download a video using yt-dlp."""
        # Sanitize filename
        safe_title = re.sub(r'[^\w\s-]', '', video_title)[:100]
        safe_title = re.sub(r'[-\s]+', '-', safe_title)
        
        # Create channel-specific directory
        channel_dir = self.download_dir / channel_config.name
        channel_dir.mkdir(parents=True, exist_ok=True)
        
        output_template = str(channel_dir / f"{video_id}_{safe_title}.%(ext)s")
        
        # Use yt-dlp's progress hook for better progress display
        cmd = [
            "yt-dlp",
            "-f", self.quality,
            "-o", output_template,
            "--no-playlist",
            "--no-warnings",
            video_url
        ]
        
        try:
            if pbar:
                pbar.set_description(f"Downloading: {video_title[:40]}")
            
            # Run download
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"Download failed for {video_id}: {result.stderr}")
                return None
            
            # Find the downloaded file
            for ext in ["mp4", "webm", "mkv"]:
                potential_file = channel_dir / f"{video_id}_{safe_title}.{ext}"
                if potential_file.exists():
                    return potential_file
            
            # Fallback: list files in channel_dir and find the newest
            files = list(channel_dir.glob(f"{video_id}_*"))
            if files:
                return max(files, key=lambda p: p.stat().st_mtime)
            
            logger.warning(f"Downloaded file not found for {video_id}")
            return None
            
        except subprocess.TimeoutExpired:
            logger.error(f"Download timeout for {video_id}")
            return None
        except Exception as exc:
            logger.error(f"Error downloading {video_id}: {exc}")
            return None
    
    def _process_channel(self, channel_config: ChannelConfig) -> List[DownloadedVideo]:
        """Process a single channel and download new shorts."""
        logger.info(f"\n{'='*70}")
        logger.info(f"Processing channel: {channel_config.name} ({channel_config.channel_id})")
        logger.info(f"{'='*70}")
        
        videos = self._get_channel_videos(channel_config, max_results=50)
        logger.info(f"Found {len(videos)} short videos in channel")
        
        new_videos = [v for v in videos if v["id"] not in self.downloaded_videos]
        logger.info(f"Found {len(new_videos)} new shorts to download")
        
        if not new_videos:
            logger.info("No new shorts found")
            return []
        
        # Apply max downloads limit
        if self.max_downloads > 0:
            new_videos = new_videos[:self.max_downloads]
        
        downloaded = []
        # Create progress bar for downloads
        with tqdm(
            total=len(new_videos),
            desc=f"Downloading from {channel_config.name}",
            unit="video",
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
        ) as pbar:
            for video in new_videos:
                video_id = video["id"]
                video_url = video["url"]
                video_title = video["title"]
                
                file_path = self._download_video(video_id, video_url, video_title, channel_config, pbar)
                
                if file_path:
                    # Upload to S3
                    s3_url = None
                    if self.s3_client:
                        s3_url = self._upload_to_s3(file_path, video_id)
                    
                    downloaded_video = DownloadedVideo(
                        video_id=video_id,
                        channel_id=channel_config.channel_id,
                        title=video_title,
                        url=video_url,
                        downloaded_at=datetime.now().isoformat(),
                        file_path=str(file_path),
                        s3_url=s3_url
                    )
                    
                    # Save to CMS
                    if self.cms_base_url:
                        self._save_to_cms(downloaded_video)
                    
                    # Save to history
                    self._save_history(downloaded_video)
                    self.downloaded_videos.add(video_id)
                    downloaded.append(downloaded_video)
                    logger.info(f"✅ Downloaded: {video_title}")
                else:
                    logger.warning(f"❌ Failed to download: {video_title}")
                
                # Update progress bar after each video (success or failure)
                pbar.update(1)
        
        return downloaded
    
    def run(self) -> Dict[str, List[DownloadedVideo]]:
        """Run the agent and download new shorts from all channels."""
        if not self._check_yt_dlp_installed():
            raise RuntimeError(
                "yt-dlp is not installed. Install it with: pip install yt-dlp\n"
                "Or visit: https://github.com/yt-dlp/yt-dlp"
            )
        
        results = {}
        # Progress bar for overall channel processing
        with tqdm(
            total=len(self.channels),
            desc="Processing channels",
            unit="channel",
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"
        ) as channel_pbar:
            for channel in self.channels:
                try:
                    channel_pbar.set_description(f"Processing {channel.name}")
                    downloaded = self._process_channel(channel)
                    results[channel.name] = downloaded
                    channel_pbar.update(1)
                except Exception as exc:
                    logger.error(f"Error processing channel {channel.name}: {exc}")
                    results[channel.name] = []
                    channel_pbar.update(1)
        
        return results


def load_channels_from_config(config_path: Path) -> List[ChannelConfig]:
    """Load channel configurations from a JSON file."""
    if not config_path.exists():
        logger.warning(f"Config file {config_path} not found. Creating default.")
        default_config = {
            "channels": [
                {
                    "channel_id": "@example",
                    "name": "Example Channel",
                    "enabled": False
                }
            ]
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2)
        return []
    
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            channels = []
            for ch in data.get("channels", []):
                # Filter out unknown fields (like "comment") before creating ChannelConfig
                channel_data = {
                    "channel_id": ch.get("channel_id", ""),
                    "name": ch.get("name", ""),
                    "enabled": ch.get("enabled", True)
                }
                # Only create if required fields are present
                if channel_data["channel_id"] and channel_data["name"]:
                    channels.append(ChannelConfig(**channel_data))
            return channels
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.error(f"Failed to load config: {exc}")
        return []


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="YouTube Shorts Agent - Download shorts from channels"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("youtube_channels.json"),
        help="Path to channel configuration JSON file"
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=Path("downloaded_shorts"),
        help="Directory to save downloaded videos"
    )
    parser.add_argument(
        "--history-file",
        type=Path,
        default=Path("youtube_download_history.json"),
        help="Path to download history JSON file"
    )
    parser.add_argument(
        "--max-downloads",
        type=int,
        default=0,
        help="Maximum number of videos to download per run (0 = unlimited)"
    )
    parser.add_argument(
        "--quality",
        type=str,
        default="best",
        help="Video quality (best, worst, bestvideo+bestaudio, etc.)"
    )
    parser.add_argument(
        "--channel",
        type=str,
        action="append",
        help="Add a channel to monitor (format: channel_id:name or just channel_id)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without actually downloading"
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    """Main entry point."""
    args = parse_args(argv)
    load_dotenv()
    
    # Load channels from config file
    channels = load_channels_from_config(args.config)
    
    # Add channels from command line if provided
    if args.channel:
        for channel_arg in args.channel:
            if ":" in channel_arg:
                channel_id, name = channel_arg.split(":", 1)
            else:
                channel_id = channel_arg
                name = channel_id
            channels.append(ChannelConfig(
                channel_id=channel_id.strip(),
                name=name.strip(),
                enabled=True
            ))
    
    if not channels:
        logger.error("No channels configured. Use --channel or edit the config file.")
        logger.info(f"Config file location: {args.config}")
        return 1
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No downloads will be performed")
        logger.info(f"Would monitor {len(channels)} channel(s):")
        for ch in channels:
            logger.info(f"  - {ch.name} ({ch.channel_id})")
        return 0
    
    try:
        agent = YouTubeShortsAgent(
            download_dir=args.download_dir,
            history_file=args.history_file,
            channels=channels,
            max_downloads=args.max_downloads,
            quality=args.quality,
        )
        
        logger.info("Starting YouTube Shorts Agent...")
        results = agent.run()
        
        total_downloaded = sum(len(videos) for videos in results.values())
        logger.info(f"\n{'='*70}")
        logger.info(f"✅ Complete! Downloaded {total_downloaded} new short(s)")
        logger.info(f"{'='*70}")
        
        for channel_name, videos in results.items():
            if videos:
                logger.info(f"  {channel_name}: {len(videos)} video(s)")
        
        return 0
        
    except Exception as exc:
        logger.error(f"Agent failed: {exc}", exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

