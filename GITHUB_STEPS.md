# GitHub Deployment Steps

## Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. Repository name: `youtube-agent` (or your preferred name)
3. Description: "YouTube Shorts Agent - Automated download and upload"
4. Choose Public or Private
5. **DO NOT** initialize with README (we already have one)
6. Click "Create repository"

## Step 2: Push Code to GitHub

```bash
# Navigate to project directory
cd /Users/relavazhagan/Desktop/youtube_agent

# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit: YouTube Shorts Agent with Vercel deployment"

# Add remote (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/youtube-agent.git

# Push to GitHub
git branch -M main
git push -u origin main
```

## Step 3: Verify Files on GitHub

Check that these files are in the repository:
- ✅ `youtube_shorts_agent.py`
- ✅ `api/trigger.py`
- ✅ `vercel.json`
- ✅ `requirements.txt`
- ✅ `youtube_channels.json`
- ✅ `.gitignore`
- ✅ `README.md`
- ✅ `DEPLOYMENT.md`

**Important**: Make sure `.env` is NOT committed (it's in `.gitignore`)

## Step 4: Connect to Vercel

1. Go to https://vercel.com
2. Sign up/Login
3. Click "New Project"
4. Click "Import Git Repository"
5. Select your GitHub repository
6. Click "Import"

## Step 5: Configure Vercel

1. **Project Name**: Keep default or change
2. **Framework Preset**: Other
3. **Root Directory**: `./` (default)
4. **Build Command**: Leave empty
5. **Output Directory**: Leave empty
6. **Install Command**: Leave empty

## Step 6: Add Environment Variables

Before deploying, add environment variables:

1. In Vercel project settings, go to "Environment Variables"
2. Add each variable:

```
S3_ACCESS_KEY_ID
S3_SECRET_ACCESS_KEY
S3_BUCKET
S3_KEY_PREFIX
S3_REGION
YT_CMS_BASE_URL
YT_CMS_AUTH_TOKEN
```

3. Select "Production", "Preview", and "Development"
4. Click "Save"

## Step 7: Deploy

1. Click "Deploy"
2. Wait for deployment (usually 1-2 minutes)
3. Note your deployment URL: `https://your-project.vercel.app`

## Step 8: Test Deployment

```bash
curl https://your-project.vercel.app/api/trigger
```

You should get a JSON response.

## Step 9: Setup n8n Workflow

### Option A: n8n Cloud

1. Go to https://n8n.io
2. Sign up for free account
3. Create new workflow
4. Add "Schedule Trigger" node
5. Set to run every hour: `0 * * * *`
6. Add "HTTP Request" node
7. Set URL to: `https://your-project.vercel.app/api/trigger`
8. Method: GET
9. Activate workflow

### Option B: Self-hosted n8n

1. Install n8n (Docker recommended)
2. Follow same workflow steps as above

## Step 10: Monitor

- **Vercel Dashboard**: View function logs and executions
- **n8n**: View workflow execution history
- **S3**: Check bucket for uploaded videos
- **CMS**: Verify records are being created

## Troubleshooting

### Git Push Issues

```bash
# If remote already exists
git remote remove origin
git remote add origin https://github.com/YOUR_USERNAME/youtube-agent.git

# Force push (if needed, be careful!)
git push -u origin main --force
```

### Vercel Deployment Fails

- Check build logs in Vercel dashboard
- Verify all files are committed
- Check environment variables are set
- Ensure `vercel.json` is correct

### Function Timeout

- Vercel free: 10s timeout
- Vercel Pro: Up to 300s timeout
- Consider reducing `max_downloads` per run

## Next Steps

1. ✅ Code pushed to GitHub
2. ✅ Deployed to Vercel
3. ✅ Environment variables configured
4. ✅ n8n workflow created
5. ✅ Monitoring setup

Your agent is now running automatically! 🎉
