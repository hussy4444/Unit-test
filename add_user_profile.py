import os
import json
import base64
import urllib.parse
import requests
import boto3
from datetime import datetime
from typing import Any, Dict, Literal, Optional, Union
import logging

from mypy_boto3_secretsmanager.client import SecretsManagerClient
from mypy_boto3_dynamodb.service_resource import DynamoDBServiceResource, Table

# Setup logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def dynamo_init():
    dynamodb: DynamoDBServiceResource = boto3.resource('dynamodb')
    table_name = os.getenv("SLACK_USER_RESPONSE")
    print("table_name", table_name)
    table = dynamodb.Table(table_name)
    return table



def get_secret(secret_name: str) -> Dict[str, str]:
    """Retrieve Slack bot token from AWS Secrets Manager."""
    secrets_client: SecretsManagerClient = boto3.client('secretsmanager')
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])


def get_user_response_from_db(user_id: str) -> Optional[Dict[str, Any]]:
    table = dynamo_init()
    """Fetch user response from DynamoDB."""
    try:
        response = table.get_item(Key={"user_id": user_id})
        return response.get("Item", {})
    except Exception as e:
        logger.error(f"Error fetching user response: {e}")
        return None


def save_user_response_to_db(user_id: str, response: str) -> None:
    table = dynamo_init()

    """Save user response to DynamoDB."""
    try:
        table.put_item(
            Item={
                "user_id": user_id,
                "response": response,
                "timestamp": int(datetime.now().timestamp()),
            }
        )
    except Exception as e:
        logger.error(f"Error saving user response: {e}")


def publish_home_view(
    user_id: str, slack_token: str, existing_response: Optional[str] = None
) -> Dict[str, Any]:
    """Publish a view to the Slack Home tab with or without a profile question."""
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": "👋 Welcome to the Frum Finance App! \n\n 📝 Profile Question: How did you first find frum.finance?"}
        },
        {"type": "divider"}
    ]

    # If a response exists, show the response and no input field
    if existing_response:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"\n Your response: {existing_response}"}
        })
    else:
        # Show the input question if no response is found
        blocks.append({
            "type": "input",
            "block_id": "question_block",
            "element": {
                "type": "plain_text_input",
                "action_id": "user_response",
                "placeholder": {"type": "plain_text", "text": "Please enter your response"}
            },
            "label": {"type": "plain_text", "text": "Answer:"}
        })
        blocks.append({
            "type": "actions",
            "block_id": "submit_button",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Submit"},
                    "action_id": "submit_profile"
                }
            ]
        })

    # Call the Slack API to publish the Home tab view
    view_payload = {
        "user_id": user_id,
        "view": {"type": "home", "blocks": blocks}
    }

    response = requests.post(
        'https://slack.com/api/views.publish',
        headers={'Authorization': f'Bearer {slack_token}', 'Content-Type': 'application/json'},
        json=view_payload
    )
    return response.json()


def send_message(user_id: str, text: str, slack_token: str) -> Dict[str, Any]:
    """Send a direct message to the user."""
    response = requests.post(
        'https://slack.com/api/chat.postMessage',
        headers={'Authorization': f'Bearer {slack_token}', 'Content-Type': 'application/json'},
        json={'channel': user_id, 'text': text}
    )
    return response.json()


def decode_payload(payload: str, is_base64_encoded: bool) -> Dict[str, Any]:
    """Decode the payload from the event body."""
    if is_base64_encoded:
        decoded_base64 = base64.b64decode(payload).decode("utf-8")
        decoded_url = urllib.parse.unquote(decoded_base64)
    else:
        decoded_url = urllib.parse.unquote(payload)

    if decoded_url.startswith("payload="):
        decoded_url = decoded_url[len("payload="):]

    if not decoded_url:
        raise ValueError("Decoded payload is empty.")

    return json.loads(decoded_url)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Union[int, str]]:
    """Main Lambda handler."""
    secret_name = os.getenv("SECRET_NAME")
    secrets = get_secret(secret_name)
    slack_token = secrets["SLACK_BOT_TOKEN"]
    logger.info(f"Received event: {event}")

    body = event.get('body', '')
    is_base64_encoded = event.get("isBase64Encoded", False)

    # try:
    #     body = decode_payload(body, is_base64_encoded)
    # except Exception as e:
    #     logger.error(f"Error decoding payload: {e}")
    #     return {"statusCode": 400, "body": "Invalid payload"}
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception as e:
            logger.error(f"Error parsing JSON from body: {e}")
            return {"statusCode": 400, "body": "Invalid payload"}

    event_type = body.get("type")
    slack_event = body.get("event", {})
    logger.info(f"slack_event event: {event_type}")

    # Handle Slack URL verification (needed during Slack setup)
    if event_type == 'url_verification':
        return {'statusCode': 200, 'body': body['challenge']}

    # Handle app_home_opened event
    if slack_event.get('type') == 'app_home_opened':
        user_id = slack_event.get('user')
        if not user_id:
            return {'statusCode': 400, 'body': 'Missing user_id'}

        # Check if the user has already submitted a response
        existing_response = get_user_response_from_db(user_id).get('response')

        # Publish the profile question or show the existing response
        publish_response = publish_home_view(user_id, slack_token, existing_response)
        if not publish_response.get('ok'):
            logger.error(f"Error publishing home view: {publish_response}")
            return {"statusCode": 500, "body": "Failed to publish view"}

        return {'statusCode': 200, 'body': 'Home view published'}

    # Handle block_actions (button click)
    if body.get('type') == 'block_actions':
        user_id = body['user']['id']
        action_id: Literal["submit_profile"] = body["actions"][0]["action_id"]

        if action_id == 'submit_profile':
            # Get the user's input response from the payload
            raw_response = body['view']['state']['values']['question_block']['user_response']['value']
            user_input = urllib.parse.unquote(raw_response).replace('+', ' ')
            # Save the response to DynamoDB
            save_user_response_to_db(user_id, user_input)
            # Send a confirmation message
            response_text = f"Thank you for submitting your response!\n 📝 Profile Question: How did you first find frum.finance? : {user_input}"
            send_message(user_id, response_text, slack_token)

        return {'statusCode': 200, 'body': 'Action processed'}

    return {'statusCode': 200, 'body': 'Success, event not handled'}