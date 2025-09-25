import os
import time
from dotenv import load_dotenv
from google.cloud import logging_v2

# 1. Load environment variables from .env
load_dotenv()

project_id = os.getenv("CLOUDSDK_CORE_PROJECT")
key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

if not project_id or not key_path:
    raise RuntimeError("Missing CLOUDSDK_CORE_PROJECT or GOOGLE_APPLICATION_CREDENTIALS in .env")

print(f"Using project: {project_id}")
print(f"Using service account key: {key_path}")

# 2. Initialize Cloud Logging client
client = logging_v2.Client(project=project_id)

# 3. Filter for ERROR logs (customize as needed)
log_filter = 'severity>=ERROR'

print("Tailing logs... Press Ctrl+C to stop.\n")

# 4. Simple polling loop (updates continuously)
while True:
    try:
        entries = client.list_entries(
            filter_=log_filter,
            order_by=logging_v2.DESCENDING,
            page_size=10,
        )
        for entry in entries:
            ts = entry.timestamp.isoformat() if entry.timestamp else "n/a"
            payload = entry.payload if entry.payload else ""
            print(f"[{ts}] {entry.severity}: {payload}")
    except Exception as e:
        print(f"Error while fetching logs: {e}")

    time.sleep(5)  # poll every 5 seconds
