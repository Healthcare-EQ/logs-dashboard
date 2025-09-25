from flask import Flask, jsonify, make_response,send_from_directory
from flask_cors import CORS
import subprocess, json, shlex, os

app = Flask(__name__, static_folder="static")
CORS(app)

GCLOUD_CMD = (
    'gcloud logging read '
    '"resource.type=\\"global\\" resource.labels.project_id=\\"ihart-388018\\"" '
    '--project ihart-388018 '
    '--limit 50 '
    '--format=json '
    '--quiet'
)

GCLOUD_CMD_TEST = (
    'gcloud logging read '
    '"resource.type=\\"cloud_run_revision\\" '
    'resource.labels.project_id=\\"ihart-388018\\" '
    'resource.labels.service_name=\\"hceq-test-service-fuhsiyo-api\\" '
    'resource.labels.location=\\"us-central1\\"" '
    '--project ihart-388018 --limit 50 --format=json --quiet'
)



@app.get("/health")
def health():
    return {"ok": True}

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
            GCLOUD_CMD, shell=True, capture_output=True, text=True, env=env
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
