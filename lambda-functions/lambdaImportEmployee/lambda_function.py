import csv
import json
import logging
import os
import re
from typing import Any

import boto3
from botocore.exceptions import ClientError
from openai import OpenAI

# Initialize logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get the webwsocket api endpoint from env variables
WEBSOCKET_API_ENDPOINT = os.environ.get(
    "WEBSOCKET_API_ENDPOINT",
    "https://w2zpvrbvxa.execute-api.eu-central-1.amazonaws.com/development/@connections",
)

# Initialize S3 client
s3_client = boto3.client("s3")

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
table_name = "webSocketSessions"
table = dynamodb.Table(table_name)

# Default data model keys
default_role = "employee"


def get_secret():
    secret_name = "openai"
    region_name = "eu-central-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)

    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise e

    secret = get_secret_value_response["SecretString"]
    return json.loads(secret)


# Initialize the OpenAI client object
secret = get_secret()
openai_client = OpenAI(api_key=secret["openai"])


def lambda_handler(event, context):
    # Expecting SQS trigger
    logger.info("Triggered by SQS event")
    logger.info(f"Received event: {json.dumps(event)}")

    # Process each record in the SQS event
    for record in event["Records"]:
        message_body = json.loads(record["body"])
        connection_id = message_body.get("connectionId")

        # Retrieve connection status from DynamoDB
        try:
            response = table.get_item(Key={"connectionId": connection_id})
            item = response.get("Item")

            if item and item.get("status") == "connected":
                # Process the user model as before
                csv_content = message_body["data"]

                if not csv_content:
                    logger.error("CSV content not provided in API request.")
                    raise ValueError("CSV content must be provided.")

                # Read the CSV content directly from the API request
                csv_reader = csv.DictReader(csv_content.splitlines())

                generated_data_models = {}  # List to collect generated data models
                generated_data_models["invites"] = []
                failed_users = []  # List to collect failed user data

                for row in csv_reader:
                    # Prepare the prompt and get the LLM response
                    prompt = generate_llm_prompt(row)
                    logger.info("Successfully generated prompt")
                    try:
                        data_model = generate_data_model_from_gpt(prompt)
                        logger.info((f"The data model is {data_model}"))

                        # Validate the data model
                        if validate_data_model(data_model):
                            data_model["role"] = default_role

                            generated_data_models["invites"].append(data_model)
                        else:
                            logger.warning(
                                f"Validation failed for data model: {data_model}"
                            )
                            failed_users.append(row)

                    except Exception as e:
                        logger.warning(f"Skipping row due to LLM error: {e}")
                        failed_users.append(row)
                        continue

                # Send processed data back to WebSocket client
                send_data_to_websocket(connection_id, generated_data_models)

            else:
                logger.warning(
                    f"Connection ID {connection_id} is not connected or does not exist."
                )
        except ClientError as e:
            logger.error(
                f"Error retrieving connection ID {connection_id} from DynamoDB: {e}"
            )

    return {"statusCode": 200, "body": "Processed SQS messages"}


def send_data_to_websocket(connection_id, data_models):
    logger.info(f"Sending data back to WebSocket for connection ID {connection_id}")

    # Convert data models to JSON format
    message = json.dumps({"data_models": data_models})

    # Create the WebSocket connection URL dynamically
    websocket_url = (
        "https://w2zpvrbvxa.execute-api.eu-central-1.amazonaws.com/development"
    )
    logger.info(f"The websocket url is {websocket_url}")
    print(f"The websocket url is {websocket_url}")

    # Initialize API Gateway Management API client
    apigw_management_client = None
    if not apigw_management_client:
        apigw_management_client = boto3.client(
            "apigatewaymanagementapi", endpoint_url=websocket_url
        )

    try:
        apigw_management_client.post_to_connection(
            ConnectionId=connection_id, Data=message.encode("utf-8")
        )
        logger.info("Message sent successfully.")
    except ClientError as e:
        logger.error(f"Failed to send message to WebSocket: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while sending message: {e}")


def generate_llm_prompt(user_data: dict) -> str:
    # Constructs a prompt based on CSV row data
    prompt = (
        f"Transform the following user data to JSON format with 'name' and 'email' as "
        "mandatory fields. Combine 'firstname' and 'lastname' into 'name' if necessary. Include any additional fields as well. "
        "The returned json should follow this structure: "
        "{'name': 'string', 'role': 'string', 'email': 'user@example.com', 'phoneNumber': 'string'}. "
        f"Transform the provided user data accordingly: {json.dumps(user_data)}"
    )
    return prompt


def generate_data_model_from_gpt(prompt: str) -> dict:
    """
    Call OpenAI’s GPT-4 model to map data from CSV to Data model.

    :param prompt: The generated prompt for the LLM.
    :return: Generated data model as dictionary.
    :raises Exception: If there's an error calling the OpenAI API.
    """
    max_retries = 3  # Number of retries
    for attempt in range(max_retries):  # +1 for the initial attempt
        try:
            response: Any = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an AI that specializes in transforming user data from csv into a "
                            "structured format for MongoDB. You are simply an API, so no yapping"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4096,
                temperature=0.7,
                top_p=0.9,
            )

            # Correctly extract and parse the message content as JSON
            data_model = json.loads(response.choices[0].message.content)
            return data_model
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"LLM response parsing error: {e}")
            raise ValueError("Invalid data format returned from GPT-3.")
        except Exception as e:
            logger.error(f"Failed to call GPT-3 model: {e}")
            if attempt < max_retries:  # Only retry if we haven't exhausted attempts
                logger.info(f"Retrying... Attempt {attempt + 2}/{max_retries + 1}")
            else:
                raise  # Re-raise the exception if all attempts fail
    return {}


def validate_data_model(data_model: dict) -> bool:
    """
    Validates the data model ensuring mandatory fields and correct formatting.

    :param data_model: The data model dictionary to validate.
    :return: True if valid, False otherwise.
    """
    required_fields = ["name", "email"]

    # Check for required fields
    if not all(field in data_model for field in required_fields):
        logger.error(f"Data model missing required fields: {data_model}")
        return False

    # Email format validation using regex
    email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if not re.match(email_pattern, data_model.get("email", "")):
        logger.error(f"Invalid email format: {data_model.get('email')}")
        return False

    # Ensure firstName and lastName fields contain alphabetic characters
    for name in data_model["name"].split(" "):

        if not name.isalpha():
            logger.error(f"Name fields contain non-alphabetic characters: {data_model}")
            return False

    return True
