"""
Vercel Serverless Function - YouTube Shorts Agent Trigger
"""
import json
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from youtube_shorts_agent import YouTubeShortsAgent, load_channels_from_config

def handler_func(request):
    """Vercel serverless function handler."""
    try:
        # Get max downloads from query params (for n8n flexibility)
        max_downloads = 0  # Default: unlimited
        if hasattr(request, 'query') and request.query:
            max_downloads = int(request.query.get('max_downloads', 0))
        elif isinstance(request, dict) and 'query' in request:
            max_downloads = int(request['query'].get('max_downloads', 0))
        
        # Get environment variables
        config_path = Path("youtube_channels.json")
        download_dir = Path("/tmp/youtube_downloads")  # Use /tmp in serverless
        history_file = Path("/tmp/youtube_download_history.json")
        
        # Ensure download directory exists
        download_dir.mkdir(parents=True, exist_ok=True)
        
        # Load channels
        channels = load_channels_from_config(config_path)
        if not channels:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "error": "No channels configured",
                    "message": "Please configure channels in youtube_channels.json"
                })
            }
        
        # Create agent
        agent = YouTubeShortsAgent(
            download_dir=download_dir,
            history_file=history_file,
            channels=channels,
            max_downloads=max_downloads,
            quality="best",
        )
        
        # Run agent
        results = agent.run()
        total_downloaded = sum(len(videos) for videos in results.values())
        
        response_data = {
            "status": "success",
            "message": f"Downloaded {total_downloaded} new short(s)",
            "results": {
                channel: len(videos) 
                for channel, videos in results.items()
            },
            "timestamp": str(Path(__file__).stat().st_mtime) if Path(__file__).exists() else None
        }
        
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(response_data)
        }
        
    except Exception as exc:
        import traceback
        error_trace = traceback.format_exc()
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "error": str(exc),
                "type": type(exc).__name__,
                "traceback": error_trace
            })
        }


# Vercel Python runtime handler
def handler(request):
    """Main entry point for Vercel - called automatically."""
    return handler_func(request)

