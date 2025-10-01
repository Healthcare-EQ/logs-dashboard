# Logs Dashboard

A simple dashboard to view GCP and Sentry logs side by side.

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install flask flask-cors requests
   ```

2. **Set environment variables:**
   ```bash
   # GCP 
   export GOOGLE_APPLICATION_CREDENTIALS=path/to/your/service-account-key.json
   export CLOUDSDK_CORE_PROJECT=ihart-388018
   
   # Sentry 
   export SENTRY_ORG_SLUG=your-org-slug
   export SENTRY_PROJECT_SLUG=your-project-slug  
   export SENTRY_AUTH_TOKEN=your-auth-token
   ```

3. **Run the server:**
   ```bash
   python server.py
   ```

4. **Open dashboard:**
   Visit `http://127.0.0.1:5050`

## Features

- **GCP Logs** (left): Shows production Cloud Run logs (INFO level and above)
- **Sentry Logs** (right): Shows Sentry events with user-friendly formatting
- **Real-time**: Auto-refresh every 10 seconds
- **Filtering**: Search and filter by severity level
- **Responsive**: Works on desktop and mobile

## Sentry Setup (Optional)

To get Sentry credentials:
1. Go to https://sentry.io/settings/auth-tokens/
2. Create a token with `project:read` scope
3. Get org/project slugs from your Sentry dashboard URLs
