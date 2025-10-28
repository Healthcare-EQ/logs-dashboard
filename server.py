from flask import Flask, jsonify, make_response,send_from_directory, request
from flask_cors import CORS
import subprocess, json, shlex, os, requests
from dotenv import load_dotenv
from typing import List, Dict, Any
from datetime import datetime, timezone

# Optional Google auth import for Firebase Admin REST
try:
    import google.auth
    from google.auth.transport.requests import Request as GoogleAuthRequest
except Exception:  # pragma: no cover
    google = None

# Optional Firebase Admin SDK
try:
    import firebase_admin
    from firebase_admin import auth as fb_auth
    from firebase_admin import credentials as fb_credentials
except Exception:  # pragma: no cover
    firebase_admin = None

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__, static_folder="static")
CORS(app)

# If FIREBASE_CREDENTIALS is provided, map it to GOOGLE_APPLICATION_CREDENTIALS for google-auth
firebase_creds_path = os.getenv("FIREBASE_CREDENTIALS")
if firebase_creds_path and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = firebase_creds_path

GCLOUD_CMD = (
    'gcloud logging read '
    '"resource.type=\\"global\\" resource.labels.project_id=\\"ihart-388018\\"" '
    '--project ihart-388018 '
    '--limit 500 '
    '--format=json '
    '--quiet'
)

GCLOUD_CMD_PROD = (
    'gcloud logging read '
    '"resource.type=\\"cloud_run_revision\\" '
    'resource.labels.project_id=\\"ihart-388018\\" '
    'resource.labels.service_name=\\"hceq-prod-na-ne2-fuh-api\\" '
    'resource.labels.location=\\"northamerica-northeast2\\"" '
    '--project ihart-388018 --limit 500 --format=json --quiet'
)

# Sentry API Configuration
SENTRY_API_BASE = "https://sentry.io/api/0"
SENTRY_ORG_SLUG = os.getenv("SENTRY_ORG_SLUG", "your-org-slug")
SENTRY_PROJECT_SLUG = os.getenv("SENTRY_PROJECT_SLUG", "your-project-slug")
SENTRY_AUTH_TOKEN = os.getenv("SENTRY_AUTH_TOKEN", "your-auth-token")

# Firebase Configuration
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "your-firebase-project-id")



_FIREBASE_APP = None

def _initialize_firebase_admin():
    """Initialize Firebase Admin SDK similarly to the provided example.

    Lookup order for credentials:
      1) FIREBASE_CREDENTIALS_JSON (inline JSON)
      2) FIREBASE_CREDENTIALS (file path)
      3) GOOGLE_APPLICATION_CREDENTIALS / ADC
    """
    global _FIREBASE_APP
    if _FIREBASE_APP is not None:
        return _FIREBASE_APP

    if firebase_admin is None:
        return None

    try:
        cred_obj = None
        json_inline = os.environ.get("FIREBASE_CREDENTIALS_JSON")
        file_path = os.environ.get("FIREBASE_CREDENTIALS") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

        if json_inline:
            info = json.loads(json_inline)
            cred_obj = fb_credentials.Certificate(info)
        elif file_path:
            cred_obj = fb_credentials.Certificate(file_path)
        else:
            # Fallback to ADC
            cred_obj = fb_credentials.ApplicationDefault()

        options = {"projectId": FIREBASE_PROJECT_ID} if FIREBASE_PROJECT_ID and FIREBASE_PROJECT_ID != "your-firebase-project-id" else None

        try:
            # Use a deterministic app name so we can reuse it
            app_name = f"default:{FIREBASE_PROJECT_ID}" if options else "default"
            _FIREBASE_APP = firebase_admin.get_app(app_name)  # type: ignore[attr-defined]
        except Exception:
            _FIREBASE_APP = firebase_admin.initialize_app(cred_obj, options=options, name=app_name)  # type: ignore[arg-type]

        return _FIREBASE_APP
    except Exception:
        return None

@app.get("/firebase-debug")
def firebase_debug():
    """Debug endpoint to check Firebase configuration and connectivity."""
    debug_info = {
        "firebase_admin_available": firebase_admin is not None,
        "fb_auth_available": fb_auth is not None,
        "firebase_project_id": FIREBASE_PROJECT_ID,
        "firebase_credentials_env": bool(os.environ.get("FIREBASE_CREDENTIALS")),
        "google_app_creds_env": bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")),
        "firebase_credentials_path": os.environ.get("FIREBASE_CREDENTIALS"),
        "google_app_creds_path": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
    }
    
    # Try to initialize Firebase and get more details
    try:
        admin_app = _initialize_firebase_admin()
        debug_info["firebase_app_initialized"] = admin_app is not None
        debug_info["firebase_app_name"] = getattr(admin_app, 'name', None) if admin_app else None
        
        # Try to get project info
        if admin_app:
            try:
                # This will fail if no users, but that's ok for debugging
                user_count = 0
                for _ in fb_auth.list_users(app=admin_app).iterate_all():
                    user_count += 1
                    if user_count >= 1:  # Just check if we can access users
                        break
                debug_info["can_access_users"] = True
                debug_info["user_count_sample"] = user_count
            except Exception as e:
                debug_info["can_access_users"] = False
                debug_info["user_access_error"] = str(e)
    except Exception as e:
        debug_info["firebase_app_initialized"] = False
        debug_info["firebase_init_error"] = str(e)
    
    return jsonify(debug_info)

@app.get("/config")
def get_config():
    return {
        "sentry_org_slug": SENTRY_ORG_SLUG,
        "sentry_project_slug": SENTRY_PROJECT_SLUG,
        "firebase_project_id": FIREBASE_PROJECT_ID
    }

@app.get("/sentry-logs")
def get_sentry_logs():
    try:
        # Check if Sentry configuration is set
        if SENTRY_AUTH_TOKEN == "your-auth-token" or SENTRY_ORG_SLUG == "your-org-slug" or SENTRY_PROJECT_SLUG == "your-project-slug":
            return make_response(
                jsonify({
                    "error": "Sentry configuration not set. Please set SENTRY_AUTH_TOKEN, SENTRY_ORG_SLUG, and SENTRY_PROJECT_SLUG environment variables."
                }),
                400
            )

        # Sentry API endpoint for events
        url = f"{SENTRY_API_BASE}/projects/{SENTRY_ORG_SLUG}/{SENTRY_PROJECT_SLUG}/events/"
        
        headers = {
            "Authorization": f"Bearer {SENTRY_AUTH_TOKEN}",
            "Content-Type": "application/json"
        }
        
        params = {
            "limit": 50,  # Limit to 50 events
            "sort": "-timestamp"  # Sort by newest first
        }

        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code != 200:
            return make_response(
                jsonify({
                    "error": f"Sentry API request failed",
                    "status_code": response.status_code,
                    "response": response.text[:1000]
                }),
                response.status_code
            )

        data = response.json()
        
        # Transform Sentry events to match the expected format
        transformed_events = []
        for event in data:
            transformed_event = {
                "timestamp": event.get("dateCreated"),
                "severity": "ERROR" if event.get("level") == "error" else event.get("level", "INFO").upper(),
                "logName": f"sentry/{event.get('id', 'unknown')}",
                "textPayload": event.get("message", ""),
                "jsonPayload": {
                    "event_id": event.get("id"),
                    "level": event.get("level"),
                    "platform": event.get("platform"),
                    "culprit": event.get("culprit"),
                    "title": event.get("title"),
                    "user": event.get("user"),
                    "tags": event.get("tags", {}),
                    "contexts": event.get("contexts", {}),
                    "extra": event.get("extra", {})
                },
                "resource": {
                    "type": "sentry",
                    "labels": {
                        "project_id": SENTRY_PROJECT_SLUG,
                        "organization": SENTRY_ORG_SLUG
                    }
                },
                "insertId": event.get("id"),
                "trace": event.get("contexts", {}).get("trace", {}).get("trace_id")
            }
            transformed_events.append(transformed_event)

        return jsonify(transformed_events)

    except requests.exceptions.RequestException as e:
        return make_response(
            jsonify({"error": f"Sentry API request failed: {str(e)}"}),
            500
        )
    except Exception as e:
        return make_response(jsonify({"error": str(e)}), 500)

@app.get("/firebase-logs")
def get_firebase_logs():
    try:
        # Check if Firebase configuration is set
        if FIREBASE_PROJECT_ID == "your-firebase-project-id":
            return make_response(
                jsonify({
                    "error": "Firebase configuration not set. Please set FIREBASE_PROJECT_ID environment variable."
                }),
                400
            )

        # Firebase logs command using gcloud
        firebase_cmd = (
            f'gcloud logging read '
            f'"resource.type=\\"firebase_database\\" OR resource.type=\\"firebase_auth\\" OR resource.type=\\"firebase_functions\\" '
            f'resource.labels.project_id=\\"{FIREBASE_PROJECT_ID}\\"" '
            f'--project {FIREBASE_PROJECT_ID} '
            f'--limit 50 '
            f'--format=json '
            f'--quiet'
        )

        # Ensure PATH includes gcloud
        env = os.environ.copy()
        
        proc = subprocess.run(
            firebase_cmd, shell=True, capture_output=True, text=True, env=env
        )

        if proc.returncode != 0:
            return make_response(
                jsonify({
                    "error": "Firebase gcloud command failed",
                    "returncode": proc.returncode,
                    "stderr": proc.stderr,
                    "stdout": proc.stdout
                }),
                500
            )

        # Parse JSON safely
        try:
            data = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError as e:
            return make_response(
                jsonify({
                    "error": "Failed to parse JSON from Firebase gcloud output",
                    "message": str(e),
                    "raw_stdout": proc.stdout[:2000],
                    "stderr": proc.stderr[:2000]
                }),
                500
            )

        return jsonify(data)

    except FileNotFoundError:
        return make_response(
            jsonify({"error": "`gcloud` not found. Confirm PATH and installation."}),
            500
        )
    except Exception as e:
        return make_response(jsonify({"error": str(e)}), 500)


def _get_google_access_token(scopes: List[str]) -> str:
    """Acquire an access token using Application Default Credentials.

    Requires `GOOGLE_APPLICATION_CREDENTIALS` to point to a service account JSON
    or the environment to provide default credentials. Scope must include
    identitytoolkit for Firebase Auth Admin API.
    """
    if not google:
        raise RuntimeError(
            "google-auth not installed. Install 'google-auth' to use /firebase-users."
        )
    credentials, _ = google.auth.default(scopes=scopes)
    if not credentials.valid:
        credentials.refresh(GoogleAuthRequest())
    return credentials.token


@app.get("/firebase-users")
def list_firebase_users():
    """List Firebase Auth users (Admin SDK preferred) and their last sign-in time.

    Query params:
      - q: optional case-insensitive filter on displayName or email
      - page_size: optional int (default 1000, max 1000)
    """
    try:
        if FIREBASE_PROJECT_ID == "your-firebase-project-id":
            return make_response(
                jsonify({
                    "error": "Firebase configuration not set. Please set FIREBASE_PROJECT_ID and GOOGLE_APPLICATION_CREDENTIALS."
                }),
                400,
            )

        q = (request.args.get("q") or "").strip().lower()
        users: List[Dict[str, Any]] = []

        # Try Admin SDK first (matching the given sample approach)
        admin_app = _initialize_firebase_admin()
        if admin_app and fb_auth is not None:
            try:
                count = 0
                for user in fb_auth.list_users(app=admin_app).iterate_all():
                    email = getattr(user, "email", "") or ""
                    display_name = getattr(user, "display_name", "") or ""
                    uid = getattr(user, "uid", "") or ""
                    last_login_time = getattr(user, "user_metadata", None)
                    # Normalize last sign-in
                    if last_login_time and getattr(last_login_time, "last_sign_in_timestamp", None):
                        try:
                            ms = int(last_login_time.last_sign_in_timestamp)
                            dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
                            last_login_iso = dt.isoformat()
                        except Exception:
                            last_login_iso = ""
                    else:
                        last_login_iso = ""

                    if q:
                        hay = f"{display_name} {email}".lower()
                        if q not in hay:
                            continue

                    users.append({
                        "uid": uid,
                        "email": email,
                        "displayName": display_name,
                        "lastSignInTime": last_login_iso,
                    })
                    count += 1
                    if count >= 1000:
                        break

                # Sort by lastSignInTime descending; missing/empty go last
                try:
                    users.sort(key=lambda u: u.get("lastSignInTime") or "", reverse=True)
                except Exception:
                    pass
                return jsonify({"users": users})
            except Exception as e:
                # Fall back to REST path below, but log the error for debugging
                print(f"Firebase Admin SDK failed: {e}")
                pass

        # Acquire access token with appropriate scope for Admin v2 API (REST fallback)
        token_identity = _get_google_access_token(["https://www.googleapis.com/auth/identitytoolkit"]) 

        # Admin v2 list accounts endpoint (batchGet)
        # Docs: https://cloud.google.com/identity-platform/docs/reference/rest/v2/projects.accounts/batchGet
        page_size = 1000
        base_admin = "https://identitytoolkit.googleapis.com/admin/v2"
        url = f"{base_admin}/projects/{FIREBASE_PROJECT_ID}/accounts:batchGet?pageSize={page_size}"
        headers = {
            "Authorization": f"Bearer {token_identity}",
            "Accept": "application/json",
        }

        users = users or []
        next_page_token = None
        # Iterate one page only by default for simplicity and performance
        # Can be extended to paginate if needed
        if next_page_token:
            pass

        tried_urls = [url]
        resp = requests.get(url, headers=headers, timeout=30)
        # If 404, try again using numeric project number (some endpoints require it)
        if resp.status_code == 404:
            try:
                token_cloud = _get_google_access_token(["https://www.googleapis.com/auth/cloud-platform.read-only"])
                crm_url = f"https://cloudresourcemanager.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}"
                crm_headers = {"Authorization": f"Bearer {token_cloud}", "Accept": "application/json"}
                crm_resp = requests.get(crm_url, headers=crm_headers, timeout=20)
                if crm_resp.status_code == 200:
                    project_number = (crm_resp.json() or {}).get("projectNumber")
                    if project_number:
                        url_num = f"{base_admin}/projects/{project_number}/accounts:batchGet?pageSize={page_size}"
                        tried_urls.append(url_num)
                        resp = requests.get(url_num, headers=headers, timeout=30)
                # else: fall through and return original 404 below
            except Exception:
                pass

        # If still failing, optionally try legacy Identity Toolkit v3 with API key
        if resp.status_code != 200:
            api_key = os.getenv("FIREBASE_API_KEY") or os.getenv("FIREBASE_WEB_API_KEY")
            legacy_payload = None
            legacy_status = None
            legacy_url = None
            if api_key:
                legacy_url = f"https://identitytoolkit.googleapis.com/identitytoolkit/v3/relyingparty/downloadAccount?key={api_key}"
                tried_urls.append(legacy_url)
                try:
                    # POST with body; maxResults up to 1000
                    legacy_resp = requests.post(legacy_url, json={"maxResults": page_size}, timeout=30)
                    legacy_status = legacy_resp.status_code
                    if legacy_resp.status_code == 200:
                        legacy_payload = legacy_resp.json() or {}
                        resp = legacy_resp  # reuse below parsing path using legacy_payload
                except Exception:
                    pass

            if resp.status_code != 200:
                # FINAL FALLBACK: derive last sign-in times from Cloud Logging (firebase_auth)
                try:
                    env = os.environ.copy()
                    auth_logs_cmd = (
                        f'gcloud logging read '
                        f'"resource.type=\\"firebase_auth\\" '
                        f'resource.labels.project_id=\\"{FIREBASE_PROJECT_ID}\\"" '
                        f'--project {FIREBASE_PROJECT_ID} '
                        f'--limit 1000 '
                        f'--format=json '
                        f'--quiet'
                    )
                    proc = subprocess.run(
                        auth_logs_cmd, shell=True, capture_output=True, text=True, env=env
                    )
                    users_from_logs: Dict[str, Dict[str, Any]] = {}
                    if proc.returncode == 0:
                        try:
                            entries = json.loads(proc.stdout or "[]")
                        except Exception:
                            entries = []

                        def extract_email(entry: Dict[str, Any]) -> str:
                            jp = entry.get('jsonPayload') or {}
                            pp = entry.get('protoPayload') or {}
                            email = (
                                jp.get('email') or
                                (jp.get('user') or {}).get('email') or
                                jp.get('userEmail') or
                                (pp.get('authenticationInfo') or {}).get('principalEmail') or
                                ''
                            )
                            if isinstance(email, str):
                                return email
                            return ''

                        def looks_like_signin(entry: Dict[str, Any]) -> bool:
                            pp = entry.get('protoPayload') or {}
                            method = str(pp.get('methodName') or '').lower()
                            if 'signin' in method or 'sign_in' in method or 'sign-in' in method:
                                return True
                            tp = str(entry.get('textPayload') or '').lower()
                            if 'sign in' in tp or 'login' in tp or 'signed in' in tp:
                                return True
                            return False

                        for e in entries:
                            if not looks_like_signin(e):
                                continue
                            email = extract_email(e)
                            if not email:
                                continue
                            ts = e.get('timestamp') or e.get('receiveTimestamp') or e.get('@timestamp') or ''
                            # Keep max timestamp per email
                            prev = users_from_logs.get(email)
                            if not prev or str(ts) > str(prev.get('lastSignInTime') or ''):
                                users_from_logs[email] = {
                                    'uid': '',
                                    'email': email,
                                    'displayName': email,
                                    'lastSignInTime': ts or '',
                                }

                        derived_users = list(users_from_logs.values())

                        # Apply q filter here
                        if q:
                            derived_users = [u for u in derived_users if q in f"{u.get('displayName','')} {u.get('email','')}".lower()]

                        return jsonify({"users": derived_users})

                except Exception:
                    pass

                return make_response(
                    jsonify({
                        "error": "Firebase Admin API request failed",
                        "status_code": resp.status_code,
                        "response": resp.text[:500],
                        "tried_urls": tried_urls,
                        "hint": "If you see 404, enable Identity Platform API or set FIREBASE_API_KEY to use legacy downloadAccount. Fallback to logs also failed or found no sign-ins.",
                        "legacy_status": legacy_status,
                    }),
                    resp.status_code,
                )

        payload = resp.json() or {}
        # Support both Admin v2 (accounts) and legacy v3 (users) shapes
        accounts = payload.get("accounts") or payload.get("users") or []
        for acct in accounts:
            email = acct.get("email") or ""
            display_name = acct.get("displayName") or ""
            # Admin v2 returns RFC3339 times under 'lastLoginTime' and 'createdAt'
            # Legacy v3 returns ms since epoch under 'lastLoginAt'
            last_login_time = acct.get("lastLoginTime") or acct.get("lastLoginAt") or ""
            # Normalize numeric millis to RFC3339 if needed
            if isinstance(last_login_time, (int, float)) or (
                isinstance(last_login_time, str) and last_login_time.isdigit()
            ):
                try:
                    ms = int(last_login_time)
                    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
                    last_login_time = dt.isoformat()
                except Exception:
                    pass
            uid = acct.get("localId") or acct.get("uid") or ""

            if q:
                hay = f"{display_name} {email}".lower()
                if q not in hay:
                    continue

            users.append({
                "uid": uid,
                "email": email,
                "displayName": display_name,
                "lastSignInTime": last_login_time,
            })

        # Sort by lastSignInTime descending; missing/empty go last
        try:
            users.sort(key=lambda u: u.get("lastSignInTime") or "", reverse=True)
        except Exception:
            pass
        return jsonify({"users": users})

    except RuntimeError as e:
        return make_response(
            jsonify({
                "error": str(e),
                "hint": "Set GOOGLE_APPLICATION_CREDENTIALS to a service account JSON with Firebase Admin access.",
            }),
            500,
        )
    except Exception as e:
        return make_response(jsonify({"error": str(e)}), 500)

@app.get("/")
def index():
    # Serve static/index.html when the user visits http://127.0.0.1:5050/
    return send_from_directory("static", "index.html")    

@app.get("/logs")
def get_logs():
    try:
        # Ensure PATH includes gcloud (adjust if needed)
        env = os.environ.copy()
        # env["PATH"] = r"C:\Program Files\Google\Cloud SDK\google-cloud-sdk\bin;" + env["PATH"]

        proc = subprocess.run(
            GCLOUD_CMD_PROD, shell=True, capture_output=True, text=True, env=env
        )

        if proc.returncode != 0:
            # Surface CLI error details to the client
            return make_response(
                jsonify({
                    "error": "gcloud command failed",
                    "returncode": proc.returncode,
                    "stderr": proc.stderr,
                    "stdout": proc.stdout
                }),
                500
            )

        # Parse JSON safely
        try:
            data = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError as e:
            return make_response(
                jsonify({
                    "error": "Failed to parse JSON from gcloud output",
                    "message": str(e),
                    "raw_stdout": proc.stdout[:2000],  # snippet for debugging
                    "stderr": proc.stderr[:2000]
                }),
                500
            )

        return jsonify(data)

    except FileNotFoundError:
        return make_response(
            jsonify({"error": "`gcloud` not found. Confirm PATH and installation."}),
            500
        )
    except Exception as e:
        return make_response(jsonify({"error": str(e)}), 500)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
