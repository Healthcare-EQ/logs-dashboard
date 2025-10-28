# Logs Dashboard

A comprehensive dashboard to view GCP logs, Sentry events, and Firebase users in one place.

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install flask flask-cors requests python-dotenv firebase-admin google-auth
   ```

2. **Create `.env` file:**
   ```bash
   # GCP Configuration
   FIREBASE_PROJECT_ID=your-firebase-project-id
   FIREBASE_CREDENTIALS=C:\path\to\your\firebase-service-account.json
   
   # Sentry Configuration (Optional)
   SENTRY_ORG_SLUG=your-org-slug
   SENTRY_PROJECT_SLUG=your-project-slug  
   SENTRY_AUTH_TOKEN=your-auth-token
   ```

3. **Run the server:**
   ```bash
   python server.py
   ```

4. **Open dashboard:**
   Visit `http://127.0.0.1:5050`

## Features

- **GCP Logs**: Shows production Cloud Run logs with filtering
- **Firebase Users**: Lists Firebase Authentication users sorted by last sign-in
- **Sentry Logs**: Shows Sentry events with detailed user information
- **Real-time**: Auto-refresh every 10 seconds
- **Filtering**: Search and filter by severity level
- **Responsive**: Works on desktop and mobile

## Firebase Setup

### 1. Connect Firebase to Google Cloud
- Go to Firebase Console → Project Settings → General
- Click "Add project to Google Cloud" if not already connected

### 2. Create Service Account
1. Go to Google Cloud Console → IAM & Admin → Service Accounts
2. Create new service account with these roles:
   - `Firebase Authentication Admin`
   - `Viewer`
   - `Service Account Token Creator`
3. Download JSON key file

### 3. Configure Environment
```bash
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_CREDENTIALS=C:\path\to\your\service-account.json
```

## Sentry Setup (Optional)

To get Sentry credentials:
1. Go to https://sentry.io/settings/auth-tokens/
2. Create a token with `project:read` scope
3. Get org/project slugs from your Sentry dashboard URLs

## Debugging

If Firebase users aren't showing:
1. Visit `http://127.0.0.1:5050/firebase-debug` to check configuration
2. Ensure service account has proper permissions
3. Verify Firebase project is connected to Google Cloud
4. Check Flask server console for error messages
