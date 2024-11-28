import unittest
from unittest.mock import patch, MagicMock
import json
from add_user_profile import (
    get_user_response_from_db,
    save_user_response_to_db,
    publish_home_view,
    send_message,
    lambda_handler,
    decode_payload,
)


class TestLambdaFunction(unittest.TestCase):
    @patch("add_user_profile.boto3.resource")  # Ensure the path matches your actual module!
    @patch.dict("os.environ", {"SLACK_USER_RESPONSE": "TestTable"})
    def test_get_user_response_from_db(self, mock_boto_resource):
        """Test fetching a user response from DynamoDB."""
        # Configure the mocked table
        mock_table = MagicMock()
        mock_boto_resource.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            "Item": {"user_id": "U123", "response": "Test response"}
        }

        # Call the function
        result = get_user_response_from_db("U123")

        # Assertions
        mock_boto_resource.assert_called_once_with("dynamodb")  # Check if boto3.resource was called
        mock_table.get_item.assert_called_once_with(Key={"user_id": "U123"})
        self.assertEqual(result, {"user_id": "U123", "response": "Test response"})

    @patch("add_user_profile.boto3.resource")
    @patch.dict("os.environ", {"SLACK_USER_RESPONSE": "TestTable"})
    def test_save_user_response_to_db(self, mock_boto_resource):
        """Test saving a user response to DynamoDB."""
        # Configure the mocked table
        mock_table = MagicMock()
        mock_boto_resource.return_value.Table.return_value = mock_table

        # Call the function
        save_user_response_to_db("U123", "Test response")

        # Assertions
        mock_boto_resource.assert_called_once_with("dynamodb")
        mock_table.put_item.assert_called_once_with(
            Item={
                "user_id": "U123",
                "response": "Test response",
                "timestamp": unittest.mock.ANY,  # Any timestamp
            }
        )

    @patch("add_user_profile.requests.post")
    def test_publish_home_view(self, mock_post):
        """Test publishing a home view to Slack."""
        mock_post.return_value.json.return_value = {"ok": True}
        response = publish_home_view("U123", "fake_token", existing_response="Test response")

        self.assertTrue(response["ok"])
        mock_post.assert_called_once_with(
            "https://slack.com/api/views.publish",
            headers={
                "Authorization": "Bearer fake_token",
                "Content-Type": "application/json",
            },
            json=unittest.mock.ANY,
        )

    @patch("add_user_profile.requests.post")
    def test_send_message(self, mock_post):
        """Test sending a message to a Slack user."""
        mock_post.return_value.json.return_value = {"ok": True}
        response = send_message("U123", "Hello!", "fake_token")

        self.assertTrue(response["ok"])
        mock_post.assert_called_once_with(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": "Bearer fake_token",
                "Content-Type": "application/json",
            },
            json={"channel": "U123", "text": "Hello!"},
        )

    @patch("add_user_profile.get_user_response_from_db")
    @patch("add_user_profile.publish_home_view")
    @patch("add_user_profile.get_secret")
    @patch.dict("os.environ", {"SECRET_NAME": "fake_secret", "SLACK_USER_RESPONSE": "TestTable"})
    def test_lambda_handler_app_home_opened(
        self, mock_get_secret, mock_publish_home_view, mock_get_user_response_from_db
    ):
        """Test Lambda handler for app_home_opened event."""
        mock_get_secret.return_value = {"SLACK_BOT_TOKEN": "fake_token"}
        mock_get_user_response_from_db.return_value = {"response": "Test response"}
        mock_publish_home_view.return_value = {"ok": True}

        event = {
            "body": json.dumps({
                "type": "event_callback",
                "event": {
                    "type": "app_home_opened",
                    "user": "U123"
                }
            }),
            "isBase64Encoded": False,
        }

        response = lambda_handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["body"], "Home view published")
        mock_get_secret.assert_called_once_with("fake_secret")
        mock_get_user_response_from_db.assert_called_once_with("U123")
        mock_publish_home_view.assert_called_once_with("U123", "fake_token", "Test response")

    def test_decode_payload(self):
        """Test decoding payload from the event."""
        payload = "payload=%7B%22key%22%3A%22value%22%7D"
        result = decode_payload(payload, is_base64_encoded=False)
        self.assertEqual(result, {"key": "value"})


if __name__ == "__main__":
    unittest.main()
