import unittest
from unittest.mock import patch, MagicMock
import os
import json
from datetime import datetime, timedelta
from notify_inactive_users import get_config,get_all_users,get_all_channels,check_user_activity,send_message,lambda_handler

class TestGetConfig(unittest.TestCase):

    @patch("boto3.client")
    @patch.dict("os.environ", {"SECRET_NAME": "my-secret-name"})
    def test_get_config_success(self, mock_boto_client):
        """Test success scenario where configuration is retrieved from Secrets Manager."""
        
        # Prepare mock response for Secrets Manager
        mock_secrets_manager = MagicMock()
        mock_boto_client.return_value = mock_secrets_manager
        mock_secrets_manager.get_secret_value.return_value = {
            'SecretString': json.dumps({
                "SLACK_BOT_TOKEN": "fake_token"
            })
        }
        
        # Call the function
        config = get_config()
        
        # Assertions
        self.assertIsNotNone(config)
        self.assertEqual(config['SLACK_BOT_TOKEN'], "fake_token")
        self.assertIn('USERS_LIST_URL', config)
        self.assertIn('CONVERSATIONS_LIST_URL', config)
        self.assertIn('CONVERSATIONS_HISTORY_URL', config)
        self.assertIn('POST_MESSAGE_URL', config)
        self.assertEqual(config['DEFAULT_DAYS_INACTIVE'], 3)  # Replace with actual default
        mock_secrets_manager.get_secret_value.assert_called_once_with(SecretId='my-secret-name')


    @patch("requests.get")
    def test_get_all_users_success(self, mock_requests_get):
        """Test success scenario for getting all users from Slack."""
        
        # Prepare mock response for Slack API
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'members': [
                {'id': 'U123', 'name': 'user1', 'is_bot': False, 'deleted': False},
                {'id': 'U124', 'name': 'user2', 'is_bot': False, 'deleted': False},
                {'id': 'U125', 'name': 'user3', 'is_bot': True, 'deleted': False},  # This is a bot
                {'id': 'U126', 'name': 'user4', 'is_bot': False, 'deleted': True},   # This user is deleted
            ]
        }
        mock_requests_get.return_value = mock_response
        
        # Prepare a mock config
        config = {
            'USERS_LIST_URL': 'https://slack.com/api/users.list',
            'SLACK_BOT_TOKEN': 'fake_token'
        }
        
        # Call the function
        users = get_all_users(config)
        
        # Assertions
        self.assertEqual(len(users), 2)  # Should only return user1 and user2
        self.assertEqual(users[0]['id'], 'U123')
        self.assertEqual(users[1]['id'], 'U124')
        mock_requests_get.assert_called_once_with(
            config['USERS_LIST_URL'],
            headers={'Authorization': f"Bearer {config['SLACK_BOT_TOKEN']}"}
        )    

    
    @patch("requests.get")
    def test_get_all_channels_success(self, mock_requests_get):
        """Test success scenario for getting all channels from Slack."""
        
        # Prepare mock response for Slack API
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'channels': [
                {'id': 'C123', 'name': 'channel1'},
                {'id': 'C124', 'name': 'channel2'}
            ]
        }
        mock_requests_get.return_value = mock_response
        
        # Prepare a mock config
        config = {
            'CONVERSATIONS_LIST_URL': 'https://slack.com/api/conversations.list',
            'SLACK_BOT_TOKEN': 'fake_token'
        }
        
        # Call the function
        channels = get_all_channels(config)
        
        # Assertions
        self.assertEqual(len(channels), 2)  # Should return two channels
        self.assertEqual(channels[0]['id'], 'C123')
        self.assertEqual(channels[1]['id'], 'C124')
        mock_requests_get.assert_called_once_with(
            config['CONVERSATIONS_LIST_URL'],
            headers={'Authorization': f"Bearer {config['SLACK_BOT_TOKEN']}"}
        )

    @patch("requests.get")
    def test_check_user_activity_success(self, mock_requests_get):
        """Test scenario where user activity is found in a channel."""
        
        # Prepare mock response for Slack API to simulate user activity
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'messages': [
                {'user': 'U123', 'text': 'Hello, world!', 'ts': str((datetime.now() - timedelta(days=1)).timestamp())}
            ]
        }
        mock_requests_get.return_value = mock_response
        
        # Prepare mock config
        config = {
            'CONVERSATIONS_HISTORY_URL': 'https://slack.com/api/conversations.history',
            'SLACK_BOT_TOKEN': 'fake_token',
            'DEFAULT_DAYS_INACTIVE': 3
        }
        
        # Call the function
        is_active = check_user_activity('U123', ['C123'], config)
        
        # Assertions
        self.assertTrue(is_active)  # User activity should be found
        mock_requests_get.assert_called_once_with(
            config['CONVERSATIONS_HISTORY_URL'],
            headers={'Authorization': f"Bearer {config['SLACK_BOT_TOKEN']}"},
            params={'channel': 'C123', 'oldest': int((datetime.now() - timedelta(days=3)).timestamp())}
        )

    @patch("requests.post")
    def test_send_message_success(self, mock_requests_post):
        """Test success scenario for sending a message to a user."""
        
        # Prepare mock response for Slack API
        mock_response = MagicMock()
        mock_response.json.return_value = {'ok': True}
        mock_requests_post.return_value = mock_response
        
        # Prepare mock config
        config = {
            'POST_MESSAGE_URL': 'https://slack.com/api/chat.postMessage',
            'SLACK_BOT_TOKEN': 'fake_token',
            'DEFAULT_MESSAGE_TEMPLATE': "Hello {user_name}, this is a reminder."
        }
        
        # Call the function
        response = send_message('U123', 'JohnDoe', config)
        
        # Assertions
        self.assertTrue(response['ok'])  # Verify that the message was successfully sent
        mock_requests_post.assert_called_once_with(
            config['POST_MESSAGE_URL'],
            headers={'Authorization': f"Bearer {config['SLACK_BOT_TOKEN']}", 'Content-Type': 'application/json; charset=utf-8'},
            json={
                'channel': 'U123',
                'text': "Hello JohnDoe, this is a reminder."
            }
        )

    @patch("notify_inactive_users.get_config")
    @patch("notify_inactive_users.get_all_users")
    @patch("notify_inactive_users.get_all_channels")
    @patch("notify_inactive_users.check_user_activity")
    @patch("notify_inactive_users.send_message")
    @patch("time.sleep", return_value=None)  # Mock time.sleep to avoid delays during tests
    def test_lambda_handler_success(self, mock_sleep, mock_send_message, mock_check_activity, mock_get_channels, mock_get_users, mock_get_config):
        # Mock the configuration
        mock_get_config.return_value = {
            'SLACK_BOT_TOKEN': 'fake_token',
            'USERS_LIST_URL': 'https://slack.com/api/users.list',
            'CONVERSATIONS_LIST_URL': 'https://slack.com/api/conversations.list',
            'DEFAULT_DAYS_INACTIVE': 30,
            'DEFAULT_MESSAGE_TEMPLATE': "Reminder: Hello {user_name}, you're inactive."
        }
        
        # Mock the list of users
        mock_get_users.return_value = [
            {'id': 'U123', 'name': 'JohnDoe'},
            {'id': 'U456', 'name': 'JaneSmith'}
        ]
        
        # Mock the list of channels
        mock_get_channels.return_value = [
            {'id': 'C123', 'name': 'general'},
            {'id': 'C456', 'name': 'random'}
        ]
        
        # Mock user activity check (return False for both users, meaning they're inactive)
        mock_check_activity.return_value = False
        
        # Mock the send_message function to return a successful response
        mock_send_message.return_value = {'ok': True}
        
        # Call the Lambda handler
        event = {}  # Add any necessary event details
        context = {}  # Add any necessary context details
        response = lambda_handler(event, context)
        
        # Assertions
        self.assertEqual(response['statusCode'], 200)
        self.assertIn('inactive_users', response['body'])
        
        # Parse the inactive users from the response body
        inactive_users = json.loads(response['body'])['inactive_users']
        self.assertEqual(len(inactive_users), 2)  # Both users should be inactive
        
        # Check that send_message was called with the correct arguments for each user
        # We will use assert_any_call here to check for both users independently
        mock_send_message.assert_any_call('U123', 'JohnDoe', mock_get_config.return_value)
        mock_send_message.assert_any_call('U456', 'JaneSmith', mock_get_config.return_value)

        # Verify that send_message was called twice, one for each user
        self.assertEqual(mock_send_message.call_count, 2)

if __name__ == "__main__":
    unittest.main()