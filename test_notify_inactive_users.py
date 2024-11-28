import unittest
from unittest.mock import patch, MagicMock
import json
# from datetime import datetime, timedelta
from notify_inactive_users import (
    get_config,
    get_all_users,
    get_all_channels,
    check_user_activity,
    send_message,
    lambda_handler,
)

class TestLambdaFunction(unittest.TestCase):

    @patch("notify_inactive_users.boto3.client")
    def test_get_config(self, mock_boto_client):
        """Test retrieving configurations from AWS Secrets Manager."""
        mock_secrets_manager = MagicMock()
        mock_boto_client.return_value = mock_secrets_manager

        # Mock Secrets Manager response
        mock_secrets_manager.get_secret_value.return_value = {
            "SecretString": json.dumps({
                "SLACK_BOT_TOKEN": "xoxb-fake-token",
                "BASE_API_URL": "https://slack.com/api"
            })
        }

        # Mock environment variable
        with patch("os.environ.get", return_value="test/secret"):
            config = get_config()

        self.assertEqual(config["SLACK_BOT_TOKEN"], "xoxb-fake-token")
        self.assertIn("USERS_LIST_URL", config)
        self.assertIn("CONVERSATIONS_LIST_URL", config)

    @patch("notify_inactive_users.requests.get")
    def test_get_all_users(self, mock_requests):
        """Test retrieving all users from Slack."""
        # Mock API response
        mock_requests.return_value.json.return_value = {
            "members": [
                {"id": "U123", "is_bot": False, "deleted": False},
                {"id": "U456", "is_bot": True, "deleted": False},
                {"id": "U789", "is_bot": False, "deleted": True},
            ]
        }

        config = {"USERS_LIST_URL": "https://fake.url", "SLACK_BOT_TOKEN": "xoxb-fake-token"}
        users = get_all_users(config)

        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["id"], "U123")
        mock_requests.assert_called_with(
            "https://fake.url",
            headers={"Authorization": "Bearer xoxb-fake-token"}
        )

    @patch("notify_inactive_users.requests.get")
    def test_get_all_channels(self, mock_requests):
        """Test retrieving all channels from Slack."""
        # Mock API response
        mock_requests.return_value.json.return_value = {
            "channels": [{"id": "C123"}, {"id": "C456"}]
        }

        config = {"CONVERSATIONS_LIST_URL": "https://fake.url", "SLACK_BOT_TOKEN": "xoxb-fake-token"}
        channels = get_all_channels(config)

        self.assertEqual(len(channels), 2)
        self.assertEqual(channels[0]["id"], "C123")
        mock_requests.assert_called_with(
            "https://fake.url",
            headers={"Authorization": "Bearer xoxb-fake-token"}
        )

    @patch("notify_inactive_users.requests.get")
    def test_check_user_activity(self, mock_requests):
        """Test checking user activity in Slack channels."""
        # Mock API response
        mock_requests.return_value.json.return_value = {
            "messages": [
                {"user": "U123", "text": "Hello"},
                {"user": "U456", "text": "Hi"}
            ]
        }

        config = {"CONVERSATIONS_HISTORY_URL": "https://fake.url", "SLACK_BOT_TOKEN": "xoxb-fake-token"}
        user_id = "U123"
        channel_ids = ["C123", "C456"]

        active = check_user_activity(user_id, channel_ids, config)
        self.assertTrue(active)

        # Ensure the API was called
        mock_requests.assert_called_with(
            "https://fake.url",
            headers={"Authorization": "Bearer xoxb-fake-token"},
            params={"channel": "C123", "oldest": unittest.mock.ANY}
        )

    @patch("notify_inactive_users.requests.post")
    def test_send_message(self, mock_post):
        """Test sending a message to Slack."""
        # Mock API response
        mock_post.return_value.json.return_value = {"ok": True}

        config = {
            "POST_MESSAGE_URL": "https://fake.url",
            "SLACK_BOT_TOKEN": "xoxb-fake-token",
            "DEFAULT_MESSAGE_TEMPLATE": "Hello {user_name}"
        }
        user_id = "U123"
        user_name = "John Doe"

        response = send_message(user_id, user_name, config)
        self.assertTrue(response["ok"])
        mock_post.assert_called_with(
            "https://fake.url",
            headers={
                "Authorization": "Bearer xoxb-fake-token",
                "Content-Type": "application/json; charset=utf-8"
            },
            json={"channel": user_id, "text": "Hello John Doe"}
        )

    @patch("notify_inactive_users.get_config")
    @patch("notify_inactive_users.get_all_users")
    @patch("notify_inactive_users.get_all_channels")
    @patch("notify_inactive_users.check_user_activity")
    @patch("notify_inactive_users.send_message")
    def test_lambda_handler(self, mock_send_message, mock_check_activity, mock_get_channels, mock_get_users, mock_get_config):
        """Test the main Lambda function handler."""
        mock_get_config.return_value = {
            "SLACK_BOT_TOKEN": "xoxb-fake-token",
            "DEFAULT_DAYS_INACTIVE": 20
        }
        mock_get_users.return_value = [
            {"id": "U123", "name": "John Doe"},
            {"id": "U456", "name": "Jane Smith"}
        ]
        mock_get_channels.return_value = [{"id": "C123"}, {"id": "C456"}]
        mock_check_activity.side_effect = [False, True]  # U123 is inactive, U456 is active
        mock_send_message.return_value = {"ok": True}

        event = {}
        response = lambda_handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        self.assertIn("inactive_users", json.loads(response["body"]))
        self.assertEqual(len(json.loads(response["body"])["inactive_users"]), 1)
        mock_send_message.assert_called_once_with("U123", "John Doe", unittest.mock.ANY)

if __name__ == "__main__":
    unittest.main()
