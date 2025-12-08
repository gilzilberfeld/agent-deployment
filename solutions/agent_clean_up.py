import os
from flask import Flask, request, jsonify
from google.cloud import storage
import vertexai
from vertexai.generative_models import GenerativeModel

# Initialize Flask app
app = Flask(__name__)

GCP_PROJECT_ID = "ADD YOUR PROJECT ID HERE"
GCS_BUCKET_NAME = "ADD YOUR BUCKET NAME HERE"
REGION_NAME = "europe-west1"
SERVICE_ACCOUNT_EMAIL = ""
PROMPT_FILE_PATH="external_prompt.txt"
FILE_1_NAME = "file1.json"
FILE_2_NAME = "file2.json"
GEMINI_MODEL = "gemini-2.5-flash"

# Initialize Google Cloud clients
# This will use the service account credentials automatically
try:
    storage_client = storage.Client()
    vertexai.init(project=GCP_PROJECT_ID, location=REGION_NAME, api_transport="rest")
    gemini_model = GenerativeModel(GEMINI_MODEL)
except Exception as e:
    print(f"ERROR: Failed to initialize Google Cloud clients: {e}")
    # In a real app, you might exit or have better error handling
    storage_client = None
    gemini_model = None


# --- Helper Functions ---

def download_file_from_gcs(file_name):
    """Downloads a file from the GCS bucket."""
    if not storage_client or not GCS_BUCKET_NAME:
        raise Exception("Storage client or bucket name not configured.")

    bucket = storage_client.get_bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(file_name)

    if not blob.exists():
        raise FileNotFoundError(f"File not found in bucket: {file_name}")

    print(f"Downloading file: {file_name}")
    return blob.download_as_text()


def delete_file_from_gcs(file_name):
    """Deletes a file from the GCS bucket."""
    if not storage_client or not GCS_BUCKET_NAME:
        raise Exception("Storage client or bucket name not configured.")

    bucket = storage_client.get_bucket(GCS_BUCKET_NAME)
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

    app.run(debug=True, host='127.0.0.1', port=int(os.environ.get('PORT', 8080)), use_reloader=False)

