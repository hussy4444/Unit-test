import unittest
from unittest.mock import patch, MagicMock
import base64
from add_user_profile import get_secret , get_user_response_from_db,save_user_response_to_db, publish_home_view, send_message, decode_payload ,lambda_handler

class TestGetSecret(unittest.TestCase):
    @patch("add_user_profile.boto3.client")  # Mock boto3 SecretsManager client
    @patch.dict("os.environ", {"SLACK_USER_RESPONSE": "TestTable"})
    def test_get_secret(self, mock_boto_client):
        # Mock the Secrets Manager client
        mock_secrets_manager = MagicMock()
        mock_boto_client.return_value = mock_secrets_manager

        # Mock response from Secrets Manager
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": '{"SLACK_BOT_TOKEN": "fake-token"}'
        }

        # Call the function
        secret_name = "my-secret-name"
        result = get_secret(secret_name)

        # Assertions
        mock_boto_client.assert_called_once_with("secretsmanager")  # Ensure boto3 client is called
        mock_secrets_manager.get_secret_value.assert_called_once_with(SecretId=secret_name)  # Ensure SecretId matches
        self.assertEqual(result, {"SLACK_BOT_TOKEN": "fake-token"})  # Check returned secret


    @patch("add_user_profile.boto3.resource")  # Mock boto3 DynamoDB resource
    @patch.dict("os.environ", {"SLACK_USER_RESPONSE": "TestTable"})  # Mock environment variable
    def test_get_user_response_from_db(self, mock_dynamo_resource):
        # Mock the DynamoDB resource and the table
        mock_table = MagicMock()
        mock_dynamo_resource.return_value.Table.return_value = mock_table  # Mock Table method

        # Mock the response from DynamoDB's get_item method
        mock_table.get_item.return_value = {"Item": {"user_id": "U123", "response": "Test response"}}

        # Call the function
        user_id = "U123"
        result = get_user_response_from_db(user_id)

        # Assertions
        mock_dynamo_resource.assert_called_once_with("dynamodb")  # Ensure boto3.resource is called
        mock_table.get_item.assert_called_once_with(Key={"user_id": user_id})  # Ensure the correct key is queried
        self.assertEqual(result, {"user_id": "U123", "response": "Test response"})  # Check the returned result


    @patch("add_user_profile.boto3.resource")  # Mock the boto3 resource method
    def test_save_user_response_to_db_success(self, mock_boto_resource):
        """Test saving a user response to DynamoDB."""
        # Create a mock Table object
        mock_table = MagicMock()
        mock_boto_resource.return_value.Table.return_value = mock_table

        # Test data
        user_id = "U123"
        response = "Test response"

        # Call the function
        save_user_response_to_db(user_id, response)

        # Assertions
        # Check if put_item was called with the expected arguments
        mock_table.put_item.assert_called_once_with(
            Item={
                "user_id": user_id,
                "response": response,
                "timestamp": unittest.mock.ANY,  # We can match ANY for the timestamp as it's dynamically generated
            }
        )

    @patch("add_user_profile.requests.post")
    def test_publish_home_view_with_existing_response(self, mock_post):
        """Test publishing a home view to Slack when there is an existing response."""

        # Mock response from Slack API
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_post.return_value = mock_response

        # Test data
        user_id = "U123"
        slack_token = "fake_token"
        existing_response = "Test response"

        # Call the function
        result = publish_home_view(user_id, slack_token, existing_response)

        # Assertions
        self.assertTrue(result["ok"])

        # Expected blocks structure
        expected_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "👋 Welcome to the Frum Finance App! \n\n 📝 Profile Question: How did you first find frum.finance?"
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"\n Your response: {existing_response}"
                }
            }
        ]

        # Check that requests.post was called with the correct URL, headers, and payload
        mock_post.assert_called_once_with(
            'https://slack.com/api/views.publish',
            headers={
                'Authorization': f'Bearer {slack_token}',
                'Content-Type': 'application/json'
            },
            json={
                "user_id": user_id,
                "view": {
                    "type": "home",
                    "blocks": expected_blocks
                }
            }
        )

    @patch('add_user_profile.requests.post')  # Patch requests.post in your module
    def test_send_message_success(self, mock_post):
        """Test sending a message successfully to Slack."""

        # Mock the response from Slack API
        mock_post.return_value.json.return_value = {"ok": True, "message": {"text": "Test message sent"}}

        # Call the function
        response = send_message("U123", "Test message", "fake_token")

        # Assert that the response is as expected
        self.assertEqual(response, {"ok": True, "message": {"text": "Test message sent"}})

        # Ensure that the requests.post was called with the correct arguments
        mock_post.assert_called_once_with(
            'https://slack.com/api/chat.postMessage',
            headers={'Authorization': 'Bearer fake_token', 'Content-Type': 'application/json'},
            json={'channel': 'U123', 'text': 'Test message'}
        )

    @patch("urllib.parse.unquote")
    def test_decode_base64_encoded_payload(self, mock_unquote):
        """Test decoding when the payload is base64 encoded."""
        payload = base64.b64encode("payload=%7B%22key%22%3A%20%22value%22%7D".encode()).decode("utf-8")
        is_base64_encoded = True

        # Expected decoded payload after base64 and URL decoding
        expected_result = {"key": "value"}

        # Mock URL decoding to simulate behavior
        mock_unquote.return_value = "payload={\"key\": \"value\"}"

        result = decode_payload(payload, is_base64_encoded)

        # Assert that the result is as expected
        self.assertEqual(result, expected_result)


    @patch("add_user_profile.get_secret")
    @patch("add_user_profile.get_user_response_from_db")
    @patch("add_user_profile.publish_home_view")
    @patch("add_user_profile.send_message")
    @patch("add_user_profile.decode_payload")
    @patch.dict("os.environ", {"SECRET_NAME": "my-secret-name"})
    def test_url_verification(self, mock_decode, mock_send_message, mock_publish, mock_get_user_response, mock_get_secret):
        """Test URL verification event from Slack."""

        # Prepare the event for URL verification
        event = {
            "body": '{"type": "url_verification", "challenge": "test_challenge"}',  # This needs to be a string that will be parsed into a dict
            "isBase64Encoded": False
        }

        # Mock the get_secret function
        mock_get_secret.return_value = {"SLACK_BOT_TOKEN": "fake_token"}

        # Call the lambda_handler
        response = lambda_handler(event, None)
        print("response",response)

        # Assertions
        self.assertEqual(response['statusCode'], 200)
        self.assertEqual(response['body'], 'test_challenge')  # Verify that challenge is returned

        # Ensure that get_secret was called to retrieve the bot token
        mock_get_secret.assert_called_once_with("my-secret-name")



if __name__ == "__main__":
    unittest.main()
