# -*- coding: utf-8 -*-
"""
Unit tests for the agent.py
This demonstrates how to test our agent's logic *without*
actually connecting to Google Cloud or Gemini.
"""

import unittest
import os
from unittest.mock import patch, MagicMock

from config import GCP_PROJECT_ID, GCS_BUCKET_NAME, REGION_NAME

# --- IMPORTANT ---
# We must set these *before* agent.py is imported,
# so the clients are initialized (or mocked) correctly.
os.environ['GCP_PROJECT'] = GCP_PROJECT_ID
os.environ['GCP_REGION'] = REGION_NAME
os.environ['BUCKET_NAME'] = GCS_BUCKET_NAME

import agent


class TestAgent(unittest.TestCase):

    def setUp(self):
        """Set up a test client for the Flask app."""
        agent.app.config['TESTING'] = True
        self.client = agent.app.test_client()

    @patch('agent.storage_client')
    @patch('agent.gemini_model')
    def test_diff_success_scenario(self, mock_gemini_model, mock_storage_client):
        """
        Tests the full "happy path" of a successful diff.
        We check:
        1. The correct files are downloaded.
        2. Gemini is called with the right content.
        3. The files are deleted (in `finally`).
        4. The correct response is returned.
        """
        print("\nRunning test_diff_success_scenario...")

        # --- 1. Configure Mocks ---

        # Mock file content
        mock_file1_content = '{"name": "Gil"}'
        mock_file2_content = '{"name": "Esti"}'

        # Mock GCS Blob
        mock_blob_file1 = MagicMock()
        mock_blob_file1.exists.return_value = True
        mock_blob_file1.download_as_text.return_value = mock_file1_content

        mock_blob_file2 = MagicMock()
        mock_blob_file2.exists.return_value = True
        mock_blob_file2.download_as_text.return_value = mock_file2_content

        # Mock GCS Bucket
        mock_bucket = MagicMock()
        # This makes bucket.blob("file1.json") return the mock for file 1
        mock_bucket.blob.side_effect = lambda name: {
            'file1.json': mock_blob_file1,
            'file2.json': mock_blob_file2
        }.get(name)

        # Mock Storage Client
        mock_storage_client.get_bucket.return_value = mock_bucket

        # Mock Gemini Response
        mock_gemini_response = MagicMock()
        mock_gemini_response.text = '{"name": {"old": "Gil", "new": "Esti"}}'
        mock_gemini_model.generate_content.return_value = mock_gemini_response

        # --- 2. Make the API Call ---
        response = self.client.post('/diff',
                                    json={'file1': 'file1.json', 'file2': 'file2.json'})

        # --- 3. Assert Results ---

        # Check that the response is correct
        self.assertEqual(response.status_code, 200)
        json_data = response.get_json()
        self.assertEqual(json_data['diff'], '{"name": {"old": "Gil", "new": "Esti"}}')

        # Check that files were "downloaded"
        mock_blob_file1.download_as_text.assert_called_once()
        mock_blob_file2.download_as_text.assert_called_once()

        # Check that Gemini was called with the correct content
        mock_gemini_model.generate_content.assert_called_once()
        call_args = mock_gemini_model.generate_content.call_args[0]
        self.assertIn(mock_file1_content, call_args[0])
        self.assertIn(mock_file2_content, call_args[0])

        # ** THE MOST IMPORTANT TEST **
        # Check that cleanup was performed
        mock_blob_file1.delete.assert_called_once()
        mock_blob_file2.delete.assert_called_once()
        print("Success!")

    @patch('agent.storage_client')
    @patch('agent.gemini_model')
    def test_cleanup_runs_on_gemini_failure(self, mock_gemini_model, mock_storage_client):
        """
        Tests that cleanup (file deletion) runs
        even if the Gemini call fails.
        """
        print("\nRunning test_cleanup_runs_on_gemini_failure...")

        # --- 1. Configure Mocks ---
        # (Same GCS setup as before)
        mock_blob_file1 = MagicMock()
        mock_blob_file1.exists.return_value = True
        mock_blob_file1.download_as_text.return_value = '{"a": 1}'

        mock_blob_file2 = MagicMock()
        mock_blob_file2.exists.return_value = True
        mock_blob_file2.download_as_text.return_value = '{"b": 2}'

        mock_bucket = MagicMock()
        mock_bucket.blob.side_effect = lambda name: {
            'file1.json': mock_blob_file1,
            'file2.json': mock_blob_file2
        }.get(name)

        mock_storage_client.get_bucket.return_value = mock_bucket

        # Mock Gemini to *fail*
        mock_gemini_model.generate_content.side_effect = Exception("Gemini API Error")

        # --- 2. Make the API Call ---
        response = self.client.post('/diff',
                                    json={'file1': 'file1.json', 'file2': 'file2.json'})

        # --- 3. Assert Results ---

        # Check that the response is an error
        self.assertEqual(response.status_code, 500)
        self.assertIn("internal server error", response.get_json()['error'])

        # ** THE MOST IMPORTANT TEST **
        # Check that cleanup *still* ran!
        mock_blob_file1.delete.assert_called_once()
        mock_blob_file2.delete.assert_called_once()
        print("Success!")

    @patch('agent.storage_client')
    def test_file_not_found(self, mock_storage_client):
        """Tests that we return a 404 if a file is missing."""
        print("\nRunning test_file_not_found...")

        # Mock GCS Blob (this one doesn't exist)
        mock_blob_file1 = MagicMock()
        mock_blob_file1.exists.return_value = False

        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob_file1
        mock_storage_client.get_bucket.return_value = mock_bucket

        # Make the API Call
        response = self.client.post('/diff',
                                    json={'file1': 'missing.json', 'file2': 'file2.json'})

        # Assert Results
        self.assertEqual(response.status_code, 404)
        self.assertIn("File not found", response.get_json()['error'])
        print("Success!")

    def test_health_check_endpoint(self):
        """Tests the new /health endpoint."""
        print("\nRunning test_health_check_endpoint...")
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})
        print("Success!")


if __name__ == '__main__':
    unittest.main()

