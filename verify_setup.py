import os
from google.cloud import storage

from config import GCP_PROJECT_ID, GCS_BUCKET_NAME


# --- PLEASE EDIT THESE TWO VALUES ---
# ------------------------------------


def verify_setup():
    """
    A simple script to verify that the user's Google Cloud environment
    is set up correctly for the workshop.
    """
    print("--- Running Workshop Pre-Flight Check ---")

    # 1. Check for credentials
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print("❌ ERROR: The GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.")
        print("Please follow Step 5 in the pre-flight check guide to set it.")
        return

    print("- Checking authentication...")
    try:
        storage_client = storage.Client(project=GCP_PROJECT_ID)
        print("  - Authentication successful.")
    except Exception as e:
        print(f"❌ ERROR: Could not authenticate with Google Cloud. Error: {e}")
        print("Please ensure your service account key is valid and the environment variable is set correctly.")
        return

    # 2. Verify bucket access and perform a simple upload/delete
    print(f"- Checking access to bucket '{GCS_BUCKET_NAME}'...")
    try:
        bucket = storage_client.get_bucket(GCS_BUCKET_NAME)
        blob_name = "test_file.txt"
        blob = bucket.blob(blob_name)

        # Upload a test file
        print(f"  - Uploading '{blob_name}' to bucket...")
        blob.upload_from_string("This is a test file for the workshop setup.")
        print("  - Upload successful.")

        # Delete the test file
        print(f"  - Cleaning up by deleting '{blob_name}'...")
        blob.delete()
        print("  - Cleanup successful.")

    except Exception as e:
        print(f"❌ ERROR: An error occurred while accessing the bucket. Error: {e}")
        print("Please ensure your bucket name is correct and your service account has 'Storage Admin' permissions.")
        return

    # 3. Final success message
    print("\n✅ Setup Verification Successful!")
    print("- Successfully authenticated with Google Cloud.")
    print("- Successfully created and uploaded test_file.txt to your bucket.")
    print("- Successfully deleted the test file for cleanup.")
    print("\nYou are all set for the workshop!")


if __name__ == "__main__":
    if GCP_PROJECT_ID == "your-gcp-project-id-here" or GCS_BUCKET_NAME == "your-unique-bucket-name-here":
         print("❌ ERROR: Please edit the PROJECT_ID and BUCKET_NAME variables at the top of this script before running.")
    else:
        verify_setup()