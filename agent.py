# -*- coding: utf-8 -*-
"""
Gemini JSON Diff Agent
This is a simple Flask web server that:
1. Receives a POST request with two filenames.
2. Downloads those files from a Google Cloud Storage bucket.
3. Sends the file contents to Gemini to get a diff.
4. Deletes the files from the bucket (for cleanup).
5. Returns the diff as a JSON response.
"""
import json
import os
from flask import Flask, request, jsonify
from google.cloud import storage
import vertexai
from vertexai.generative_models import GenerativeModel
from config import GCP_PROJECT_ID, REGION_NAME, GCS_BUCKET_NAME, GEMINI_MODEL

# --- Configuration ---

# Initialize Flask app
app = Flask(__name__)

#os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\GitHub\Workshops\agent-deployment\test-project-475514-ab4418b1ca87.json"
# Get environment variables
# We set this during deployment
GCP_PROJECT_ID = os.environ.get('GCP_PROJECT', GCP_PROJECT_ID)
GCP_REGION = os.environ.get('GCP_REGION', REGION_NAME)
BUCKET_NAME = os.environ.get('BUCKET_NAME', GCS_BUCKET_NAME)

print(f"✅ SUCCESS: Auth initialized for project {GCP_PROJECT_ID}")
# Initialize Google Cloud clients
# This will use the service account credentials automatically
try:
    storage_client = storage.Client()
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)
    gemini_model = GenerativeModel(GEMINI_MODEL)
except Exception as e:
    print(f"ERROR: Failed to initialize Google Cloud clients: {e}")
    # In a real app, you might exit or have better error handling
    storage_client = None
    gemini_model = None


# --- Helper Functions ---

def download_file_from_gcs(file_name):
    """Downloads a file from the GCS bucket."""
    if not storage_client or not BUCKET_NAME:
        raise Exception("Storage client or bucket name not configured.")

    bucket = storage_client.get_bucket(BUCKET_NAME)
    blob = bucket.blob(file_name)

    if not blob.exists():
        raise FileNotFoundError(f"File not found in bucket: {file_name}")

    print(f"Downloading file: {file_name}")
    return blob.download_as_text()


def delete_file_from_gcs(file_name):
    """Deletes a file from the GCS bucket."""
    if not storage_client or not BUCKET_NAME:
        raise Exception("Storage client or bucket name not configured.")

    bucket = storage_client.get_bucket(BUCKET_NAME)
    blob = bucket.blob(file_name)

    if blob.exists():
        print(f"Cleaning up file: {file_name}")
        blob.delete()
    else:
        print(f"Warning: File already deleted or never existed: {file_name}")


def get_gemini_diff(file1_content, file2_content):
    """Sends file contents to Gemini and asks for a diff."""
    if not gemini_model:
        raise Exception("Gemini model not initialized.")

    # This prompt is key to our agent's quality!
    prompt = f"""
    You are an expert JSON comparison agent.
    Analyze the two JSON objects below.
    Return a JSON object that only describes the differences.
    If there are no differences, return an empty JSON object {{}}.

    File 1:
    {file1_content}

    File 2:
    {file2_content}

    Respond with only the differences - keys and their values - in JSON format. For example:
    {{
        "key1": "In file1 is: value_for_key1_in_file1, in file2 is: value_for_key1_in_file2",
        "key2": "In file1 is: value_for_key2_in_file1, in file2 is: value_for_key2_in_file2",
    }}
    """

    print("Generating content with Gemini...")
    response = gemini_model.generate_content(prompt)

    # Clean up the response from Gemini
    raw_text = response.text.strip()
    print (f"Clean Gemini response: {raw_text}")
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:-3].strip()

    return raw_text


# --- Main API Endpoint ---

@app.route("/diff", methods=['POST'])
def handle_diff_request():
    """Main endpoint to handle the diff request."""
    file1_name = None
    file2_name = None
    try:
        # 1. Get request data
        data = request.get_json()
        file1_name = data.get('file1')
        file2_name = data.get('file2')

        if not file1_name or not file2_name:
            return jsonify({"error": "Missing 'file1' or 'file2' in request"}), 400

        # 2. Download files from GCS
        try:
            file1_content = download_file_from_gcs(file1_name)
            file2_content = download_file_from_gcs(file2_name)
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404

        # 3. Get diff from Gemini
        diff_result_text = get_gemini_diff(file1_content, file2_content)

        # 4. Return the successful response
        # result = jsonify({"diff": diff_result_text})
        result = jsonify({"diff": json.loads(diff_result_text)})
        return result, 200

    except Exception as e:
        # General error handler
        print(f"An unexpected error occurred: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500



@app.route("/health", methods=['GET'])
def health_check():
    """A simple health check endpoint."""
    # This proves the server is running.
    # A more advanced check would test dependencies (e.g., talk to GCS).
    return jsonify({"status": "ok"}), 200


# This allows us to run the app locally for testing
if __name__ == "__main__":
    # For local testing, we need to set these variables
    # (In production, Cloud Run sets them for us)
    os.environ['GCP_PROJECT'] = GCP_PROJECT_ID  # Replace with your project ID
    os.environ['BUCKET_NAME'] = GCS_BUCKET_NAME  # Replace with your bucket name

    # You MUST set GOOGLE_APPLICATION_CREDENTIALS in your terminal
    # before running this for local testing.

    # Check if we are running in Cloud Run
    # Cloud Run always sets the 'PORT' environment variable.
    # If 'PORT' is set, we use 0.0.0.0 (public access for container).
    # If 'PORT' is NOT set, we assume local testing and use 127.0.0.1 (private loopback).

    server_port = os.environ.get("PORT", "8081")

    if os.environ.get("K_SERVICE"):  # 'K_SERVICE' is automatically set by Cloud Run
        # PROD MODE (Cloud Run)
        print(f"🚀 Starting in CLOUD mode on port {server_port}")
        app.run(host="0.0.0.0", port=int(server_port))
    else:
        # LOCAL DEV MODE
        print(f"💻 Starting in LOCAL mode on port {server_port}")
        # We need to manually load credentials for local dev if not using 'gcloud auth application-default login'
        # But for this workshop, we assume they rely on the environment variable set in their terminal.
        app.run(debug=True, host="127.0.0.1", port=int(server_port))
