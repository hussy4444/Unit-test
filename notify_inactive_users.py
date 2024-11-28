import os
import json
import time
import requests
from datetime import datetime, timedelta
import boto3
from mypy_boto3_secretsmanager.client import SecretsManagerClient
from constants import (
    USERS_LIST_ENDPOINT,
    CONVERSATIONS_LIST_ENDPOINT,
    CONVERSATIONS_HISTORY_ENDPOINT,
    POST_MESSAGE_ENDPOINT,
    DEFAULT_DAYS_INACTIVE,
    DEFAULT_MESSAGE_TEMPLATE,
    BASE_API_URL
)

# Function to retrieve all configurations from Secrets Manager
def get_config():
    client : SecretsManagerClient = boto3.client('secretsmanager')
    try:
        response = client.get_secret_value(SecretId=os.environ.get('SECRET_NAME'))
        config = json.loads(response['SecretString'])
        # Format URLs using BASE_API_URL for consistency
        config['USERS_LIST_URL'] = f"{BASE_API_URL}{USERS_LIST_ENDPOINT}"
        config['CONVERSATIONS_LIST_URL'] = f"{BASE_API_URL}{CONVERSATIONS_LIST_ENDPOINT}"
        config['CONVERSATIONS_HISTORY_URL'] = f"{BASE_API_URL}{CONVERSATIONS_HISTORY_ENDPOINT}"
        config['POST_MESSAGE_URL'] = f"{BASE_API_URL}{POST_MESSAGE_ENDPOINT}"
        config['DEFAULT_DAYS_INACTIVE'] = DEFAULT_DAYS_INACTIVE
        config['DEFAULT_MESSAGE_TEMPLATE'] = DEFAULT_MESSAGE_TEMPLATE
        return config
    except Exception as e:
        print(f"Error retrieving secret: {e}")
        return None

# Function to retrieve all users
def get_all_users(config):
    response = requests.get(
        config['USERS_LIST_URL'],
        headers={'Authorization': f"Bearer {config['SLACK_BOT_TOKEN']}"}
    )
    users = response.json().get('members', [])
    return [user for user in users if not user.get('is_bot') and not user.get('deleted')]

# Function to retrieve all channels
def get_all_channels(config):
    response = requests.get(
        config['CONVERSATIONS_LIST_URL'],
        headers={'Authorization': f"Bearer {config['SLACK_BOT_TOKEN']}"}
    )
    return response.json().get('channels', [])

# Function to check if a user is active in any channel in the last DEFAULT_DAYS_INACTIVE days
def check_user_activity(user_id, channel_ids, config):
    time_limit_last_active = int((datetime.now() - timedelta(days=int(config['DEFAULT_DAYS_INACTIVE']))).timestamp())
    for channel_id in channel_ids:
        response = requests.get(
            config['CONVERSATIONS_HISTORY_URL'],
            headers={'Authorization': f"Bearer {config['SLACK_BOT_TOKEN']}"},
            params={'channel': channel_id, 'oldest': time_limit_last_active}
        )
        messages = response.json().get('messages', [])
        for message in messages:
            if message.get('user') == user_id:
                return True
    return False

# Function to send a message to a user
def send_message(user_id, user_name, config):
    response = requests.post(
        config['POST_MESSAGE_URL'],
        headers={'Authorization': f"Bearer {config['SLACK_BOT_TOKEN']}", 'Content-Type': 'application/json; charset=utf-8'},
        json={
            'channel': user_id,
            'text': config['DEFAULT_MESSAGE_TEMPLATE'].format(user_name=user_name)
        }
    )
    return response.json()

# Main Lambda function handler
def lambda_handler(event, context):
    config = get_config()
    if not config:
        return {'statusCode': 500, 'body': 'Failed to retrieve configuration from Secrets Manager'}

    users = get_all_users(config)
    channels = get_all_channels(config)
    channel_ids = [channel['id'] for channel in channels]

    inactive_users = []
    for user in users:
        user_id = user['id']
        user_name = user['name']
        if not check_user_activity(user_id, channel_ids, config):
            inactive_users.append({'user_id': user_id, 'name': user_name})
            send_message(user_id, user_name, config)
            time.sleep(1)  # Rate limiting

    return {
        'statusCode': 200,
        'body': json.dumps({'inactive_users': inactive_users})
    }