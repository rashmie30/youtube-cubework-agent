# YouTube Shorts Agent

Automated agent that downloads YouTube Shorts from configured channels, uploads them to S3, and saves metadata to CMS.

## Features

- ✅ Downloads YouTube Shorts from multiple channels
- ✅ Uploads videos to AWS S3
- ✅ Saves metadata to CMS (GraphQL)
- ✅ Prevents duplicate downloads
- ✅ Auto-deletes local files after S3 upload
- ✅ CMS tracking to prevent duplicate uploads
- ✅ Deployable on Vercel
- ✅ Triggerable via n8n or cron

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Install yt-dlp (required)
pip install yt-dlp
# Or: brew install yt-dlp

# Configure channels
# Edit youtube_channels.json

# Run agent
python3 youtube_shorts_agent.py

# Or with scheduler
python3 youtube_agent_scheduler.py --interval 3600
```

### Deploy to Vercel

See [DEPLOYMENT.md](./DEPLOYMENT.md) for complete deployment guide.

Quick steps:
1. Push to GitHub
2. Connect to Vercel
3. Set environment variables
4. Deploy
5. Setup n8n workflow to trigger endpoint

## Configuration

### Channels (`youtube_channels.json`)

```json
{
  "channels": [
    {
      "channel_id": "https://www.youtube.com/@cubework_us/shorts",
      "name": "Cubework US",
      "enabled": true
    }
  ]
}
```

### Environment Variables

Required for S3 and CMS:

```bash
S3_ACCESS_KEY_ID=your_key
S3_SECRET_ACCESS_KEY=your_secret
S3_BUCKET=your-bucket
S3_KEY_PREFIX=public/cubework/youtube-shorts
YT_CMS_BASE_URL=https://your-cms/api/graphql
YT_CMS_AUTH_TOKEN=your-token
```

## Usage

### Manual Trigger

```bash
# Local
python3 youtube_shorts_agent.py

# Vercel endpoint
curl https://your-project.vercel.app/api/trigger
```

### Scheduled (n8n)

1. Create n8n workflow
2. Add Schedule Trigger (cron: `0 * * * *`)
3. Add HTTP Request node → `https://your-project.vercel.app/api/trigger`
4. Activate workflow

## Project Structure

```
.
├── api/
│   └── trigger.py          # Vercel serverless function
├── youtube_shorts_agent.py # Main agent code
├── youtube_channels.json   # Channel configuration
├── youtube_agent_scheduler.py # Scheduler (local)
├── vercel.json            # Vercel configuration
├── requirements.txt       # Python dependencies
└── DEPLOYMENT.md         # Deployment guide
```

## How It Works

1. **Download**: Fetches new shorts from configured channels
2. **Upload**: Uploads to S3 (deletes local file after)
3. **Save**: Saves metadata to CMS with YouTube and S3 URLs
4. **Track**: Prevents duplicates via history file and CMS checks

## Requirements

- Python 3.9+
- yt-dlp (YouTube downloader)
- AWS S3 credentials
- CMS GraphQL endpoint

## License

MIT

