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

import os
from flask import Flask, request, jsonify
from google.cloud import storage
import vertexai
from vertexai.generative_models import GenerativeModel

from config import GCP_PROJECT_ID, REGION_NAME, GCS_BUCKET_NAME, PROMPT_FILE_PATH

# --- Configuration ---

# Initialize Flask app
app = Flask(__name__)

# Get environment variables
# We set this during deployment
GCP_PROJECT_ID = os.environ.get('GCP_PROJECT', GCP_PROJECT_ID)
GCP_REGION = os.environ.get('GCP_REGION', REGION_NAME)
BUCKET_NAME = os.environ.get('BUCKET_NAME', GCS_BUCKET_NAME)

# Initialize Google Cloud clients
# This will use the service account credentials automatically
try:
    storage_client = storage.Client()
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION)
    gemini_model = GenerativeModel("gemini-1.5-flash-001")
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


def get_gemini_diff(prompt_template, file1_content, file2_content):
    """Sends file contents to Gemini and asks for a diff."""
    if not gemini_model:
        raise Exception("Gemini model not initialized.")

    prompt = prompt_template.format(
        content1=file1_content,
        content2=file2_content
    )

    print("Generating content with Gemini...")
    response = gemini_model.generate_content(prompt)

    # Clean up the response from Gemini
    raw_text = response.text.strip()
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

        try:
            print(f"Loading prompt from GCS: {PROMPT_FILE_PATH}")
            prompt_template = download_file_from_gcs(PROMPT_FILE_PATH)
        except FileNotFoundError:
            print(f"CRITICAL ERROR: Prompt file not found at {PROMPT_FILE_PATH}")
            return jsonify({"error": "Configuration error: Prompt template not found."}), 500
        except Exception as e:
            print(f"CRITICAL ERROR: Could not load prompt: {e}")
            return jsonify({"error": "Configuration error: Could not load prompt."}), 500

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
        return jsonify({"diff": diff_result_text}), 200

    except Exception as e:
        # General error handler
        print(f"An unexpected error occurred: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500

    finally:
        # 5. Clean up files
        # This `finally` block ensures cleanup runs
        # even if an error happened in step 3.
        # We only cleanup if the files were successfully downloaded.
        print("Entering cleanup block...")
        try:
            if file1_name:
                delete_file_from_gcs(file1_name)
            if file2_name:
                delete_file_from_gcs(file2_name)
        except Exception as e:
            # Don't fail the request if cleanup fails, just log it.
            print(f"Warning: Cleanup failed for {file1_name} or {file2_name}: {e}")


@app.route("/health", methods=['GET'])
def health_check():
    """
    An advanced health check that also tests connectivity
    to the Gemini API.
    """
    try:
        # Test Gemini connection with a simple, harmless query
        print("Testing Gemini connectivity...")
        gemini_model.generate_content("test")
        print("Gemini connectivity successful.")
        return jsonify({"status": "ok", "dependencies": {"gemini": "ok"}}), 200
    except Exception as e:
        print(f"HEALTH CHECK FAILED: {e}")
        # 503 Service Unavailable is the standard response
        return jsonify({"status": "error", "dependencies": {"gemini": "failed"}}), 503

# This allows us to run the app locally for testing
if __name__ == "__main__":
    # For local testing, we need to set these variables
    # (In production, Cloud Run sets them for us)
    os.environ['GCP_PROJECT'] = GCP_PROJECT_ID  # Replace with your project ID
    os.environ['BUCKET_NAME'] = GCS_BUCKET_NAME  # Replace with your bucket name

    # You MUST set GOOGLE_APPLICATION_CREDENTIALS in your terminal
    # before running this for local testing.

    app.run(debug=True, host='127.0.0.1', port=int(os.environ.get('PORT', 8080)), use_reloader=False)

