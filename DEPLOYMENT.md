# YouTube Shorts Agent - Deployment Guide

## Overview

This agent downloads YouTube Shorts, uploads them to S3, and saves metadata to CMS. It's deployed on Vercel and triggered via n8n.

## Architecture

```
n8n (Scheduler) → Vercel API Endpoint → YouTube Agent → S3 + CMS
```

## Prerequisites

1. **GitHub Account** - For code repository
2. **Vercel Account** - For serverless deployment
3. **n8n Account** - For scheduling triggers
4. **AWS S3** - For video storage
5. **CMS** - For metadata storage

## Step 1: Push to GitHub

### 1.1 Initialize Git Repository

```bash
# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit: YouTube Shorts Agent"

# Create repository on GitHub, then:
git remote add origin https://github.com/your-username/youtube-agent.git
git branch -M main
git push -u origin main
```

### 1.2 Files to Include

Make sure these files are committed:
- `youtube_shorts_agent.py` - Main agent code
- `youtube_channels.json` - Channel configuration
- `api/trigger.py` - Vercel serverless function
- `vercel.json` - Vercel configuration
- `requirements.txt` - Python dependencies
- `.gitignore` - Git ignore rules

## Step 2: Deploy to Vercel

### 2.1 Connect GitHub to Vercel

1. Go to [vercel.com](https://vercel.com)
2. Click "New Project"
3. Import your GitHub repository
4. Select the repository

### 2.2 Configure Environment Variables

In Vercel Dashboard → Project Settings → Environment Variables, add:

```
S3_ACCESS_KEY_ID=your_access_key_here
S3_SECRET_ACCESS_KEY=your_secret_key_here
S3_BUCKET=video-dev-item
S3_KEY_PREFIX=public/cubework/youtube-shorts
S3_REGION=us-west-1
YT_CMS_BASE_URL=https://your-cms-url/api/graphql
YT_CMS_AUTH_TOKEN=tokens API-Key your-token-here
```

### 2.3 Deploy

1. Click "Deploy"
2. Wait for deployment to complete
3. Note your deployment URL: `https://your-project.vercel.app`

### 2.4 Test the Endpoint

```bash
curl https://your-project.vercel.app/api/trigger
```

You should get a JSON response.

## Step 3: Setup n8n Workflow

### 3.1 Create n8n Account

1. Sign up at [n8n.io](https://n8n.io) (cloud) or self-host
2. Create a new workflow

### 3.2 Create Schedule Trigger

1. Add **Schedule Trigger** node
2. Configure schedule:
   - **Cron Expression**: `0 * * * *` (every hour)
   - Or use UI: "Every hour"

### 3.3 Add HTTP Request Node

1. Add **HTTP Request** node after Schedule Trigger
2. Configure:
   - **Method**: `GET` or `POST`
   - **URL**: `https://your-project.vercel.app/api/trigger`
   - **Authentication**: None (or add headers if needed)

### 3.4 Optional: Add Error Handling

1. Add **IF** node to check response status
2. Add **Send Email** or **Slack** node for notifications
3. Add **Error Trigger** node for failures

### 3.5 Activate Workflow

1. Click "Active" toggle
2. Save workflow
3. Test manually first

## Step 4: Configure Channels

### 4.1 Edit Channel Configuration

Edit `youtube_channels.json`:

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

### 4.2 Commit and Push

```bash
git add youtube_channels.json
git commit -m "Update channel configuration"
git push
```

Vercel will auto-deploy on push.

## Step 5: Monitor and Debug

### 5.1 Vercel Logs

- Go to Vercel Dashboard → Your Project → Functions
- Click on `api/trigger.py`
- View logs and execution times

### 5.2 n8n Execution History

- Go to n8n → Executions
- View execution history
- Check for errors

### 5.3 Check S3 Bucket

- Verify files are uploading to S3
- Check path: `public/cubework/youtube-shorts/`

### 5.4 Check CMS

- Verify records are being created
- Check for duplicate prevention

## Troubleshooting

### Issue: Function Timeout

**Solution**: 
- Vercel free tier: 10s timeout
- Vercel Pro: Up to 300s timeout
- Consider downloading fewer videos per run

### Issue: yt-dlp Not Found

**Solution**:
- Vercel may not have yt-dlp installed
- Consider using GitHub Actions instead
- Or bundle yt-dlp binary

### Issue: Files Not Uploading to S3

**Solution**:
- Check S3 credentials in Vercel environment variables
- Verify S3 bucket permissions
- Check Vercel logs for errors

### Issue: CMS Errors

**Solution**:
- Verify CMS URL and auth token
- Check GraphQL schema matches code
- Review CMS logs

## Alternative: GitHub Actions (If Vercel Doesn't Work)

If Vercel has issues with yt-dlp, use GitHub Actions:

1. Create `.github/workflows/youtube-agent.yml`
2. Schedule with cron
3. Run agent in GitHub Actions runner
4. Trigger via n8n webhook or GitHub API

## Security Notes

- Never commit `.env` file
- Use Vercel environment variables for secrets
- Rotate S3 keys regularly
- Use read-only CMS tokens if possible

## Support

For issues:
1. Check Vercel logs
2. Check n8n execution history
3. Review agent logs in history file
4. Test endpoint manually with curl

