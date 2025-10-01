from flask import Flask, jsonify, make_response,send_from_directory
from flask_cors import CORS
import subprocess, json, shlex, os, requests

app = Flask(__name__, static_folder="static")
CORS(app)

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



@app.get("/health")
def health():
    return {"ok": True}

@app.get("/config")
def get_config():
    return {
        "sentry_org_slug": SENTRY_ORG_SLUG,
        "sentry_project_slug": SENTRY_PROJECT_SLUG
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
