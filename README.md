# Logs Dashboard

A simple Flask web application for viewing Google Cloud Platform logs.

in future, will be able to see firebase, sentry and any other logs across gcp services in one place 

## Prerequisites

- Python 3.x
- Google Cloud SDK (`gcloud` CLI) installed and configured
- Required environment variables set

## Environment Variables

Set the following environment variables before running the application:


GOOGLE_APPLICATION_CREDENTIALS=path/to/your/service-account-key.json
CLOUDSDK_CORE_PROJECT=your-gcp-project-id

## Installation

1. Install required Python packages:
```bash
pip install flask flask-cors
```

2. Make sure Google Cloud SDK is installed and authenticated:
```bash
gcloud auth login
gcloud auth application-default login
```

## Running the Server

To start the server, run:

```bash
python server.py
```

The server will start on `http://127.0.0.1:5050`

## Usage

- Visit `http://127.0.0.1:5050` to access the dashboard
- The `/logs` endpoint provides JSON data from GCP logs
- The `/health` endpoint provides server health status

## Notes

- The application is configured to read logs from the `ihart-388018` project
- Logs are limited to 50 entries by default
- Make sure your service account has the necessary permissions to read logs (use log-viewer)
