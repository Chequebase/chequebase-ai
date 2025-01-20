import csv
import json
import logging
import os
import re
from typing import Any, Dict, List, Tuple

import boto3
from botocore.exceptions import ClientError
from openai import OpenAI

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Constants / environment variables
WEBSOCKET_API_ENDPOINT = os.environ.get("WEBSOCKET_API_ENDPOINT")
TABLE_NAME = os.environ.get("TABLE_NAME", "webSocketSessions")
DEFAULT_ROLE = "employee"
EMAIL_REGEX = r"^[\w\.-]+@[\w\.-]+\.\w+$"

# AWS clients
s3_client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def get_secret():

    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        return {"openai": api_key}
    secret_name = "openai"
    region_name = "eu-central-1"
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)
    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise e
    return json.loads(get_secret_value_response["SecretString"])


# OpenAI Client (api_key from Secrets Manager)
secret = get_secret()
openai_client = OpenAI(api_key=secret["openai"])


def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")

    # This example assumes SQS triggers the Lambda
    for record in event["Records"]:
        message_body = json.loads(record["body"])
        connection_id = message_body.get("connectionId")

        # Check DynamoDB for connection status
        try:
            response = table.get_item(Key={"connectionId": connection_id})
            item = response.get("Item")

            if not item or item.get("status") != "connected":
                logger.warning(
                    f"Connection ID {connection_id} is not valid or not connected."
                )
                continue

            csv_content = message_body.get("data")
            if not csv_content:
                logger.error("CSV content not provided in API request.")
                raise ValueError("CSV content must be provided.")

            # Parse CSV
            logger.info("Parsing CSV content...")
            parsed_rows = list(csv.DictReader(csv_content.splitlines()))
            logger.info(f"Number of rows read: {len(parsed_rows)}")

            # Attempt direct mapping
            structured_rows, failed_rows = parse_with_heuristics(parsed_rows)

            # If any rows failed, fall back to GPT
            if failed_rows:
                logger.info(f"Falling back to GPT for {len(failed_rows)} rows.")
                ai_parsed, still_failed = parse_with_ai_fallback(failed_rows)
                structured_rows.extend(ai_parsed)
                # If there are rows that AI also fails, log them
                if still_failed:
                    logger.warning(
                        f"Rows failed even after AI fallback: {len(still_failed)}"
                    )

            # Validation & Finalizing
            validated_rows = []
            invalid_rows = []
            for row in structured_rows:
                if validate_data_model(row):
                    # Insert default role if missing
                    if "role" not in row or not row["role"]:
                        row["role"] = DEFAULT_ROLE
                    validated_rows.append(row)
                else:
                    invalid_rows.append(row)

            # Prepare the final response
            generated_data_models = {
                "invites": validated_rows,
                "failedUsers": invalid_rows,
            }

            # Send response via WebSocket
            send_data_to_websocket(connection_id, generated_data_models)

        except ClientError as e:
            logger.error(
                f"Error retrieving connection ID {connection_id} from DynamoDB: {e}"
            )

    return {"statusCode": 200, "body": "Processed SQS messages"}


def parse_with_heuristics(
    parsed_rows: List[Dict[str, str]]
) -> Tuple[List[Dict], List[Dict]]:
    """
    Attempt to parse CSV rows with direct heuristics:
    - Combine first/last name
    - Identify email columns
    - Identify phone columns if present
    Returns (structured_rows, failed_rows).
    """
    structured_rows = []
    failed_rows = []

    # Common synonyms for name & email columns
    name_synonyms = {
        "firstname",
        "first_name",
        "f_name",
        "lastname",
        "last_name",
        "surname",
    }
    email_synonyms = {"email", "mail", "email_address"}

    for row in parsed_rows:
        # Convert all keys to lowercase for easy matching
        row_lower = {k.lower().strip(): v.strip() for k, v in row.items() if v}

        # Try to find name parts
        first_name = None
        last_name = None
        for k, v in row_lower.items():
            if "first" in k:
                first_name = v
            elif "last" in k:
                last_name = v
            elif k in name_synonyms:
                if "f" in k:
                    first_name = v
                if "l" in k or "s" in k:
                    last_name = v

        # If there's a single 'name' field
        if not first_name and not last_name:
            if "name" in row_lower:
                first_name = row_lower["name"]
                last_name = ""  # not mandatory to have a last name

        combined_name = None
        if first_name or last_name:
            combined_name = f"{first_name or ''} {last_name or ''}".strip()

        # Try to find an email
        email = None
        for k, v in row_lower.items():
            if k in email_synonyms or "email" in k:
                email = v
                break

        # Try to find phone number
        phone = None
        for k, v in row_lower.items():
            if "phone" in k or "mobile" in k:
                phone = v
                break

        # Build structured object
        data_obj = {}
        if combined_name:
            data_obj["name"] = combined_name
        if email:
            data_obj["email"] = email
        if phone:
            data_obj["phoneNumber"] = phone

        # Basic check
        if "name" not in data_obj or "email" not in data_obj:
            failed_rows.append(row)
        else:
            structured_rows.append(data_obj)

    return structured_rows, failed_rows


def parse_with_ai_fallback(
    failed_rows: List[Dict[str, str]]
) -> Tuple[List[Dict], List[Dict]]:
    """
    Use GPT to transform rows into the required JSON.
    Returns (ai_parsed_rows, still_failed_rows).
    """
    ai_parsed_rows = []
    still_failed_rows = []
    for row in failed_rows:
        prompt = generate_llm_prompt(row)
        try:
            result = generate_data_model_from_gpt(prompt)
            ai_parsed_rows.append(result)
        except Exception as e:
            logger.warning(f"Skipping row due to LLM error: {e}")
            still_failed_rows.append(row)
    return ai_parsed_rows, still_failed_rows


def generate_llm_prompt(user_data: dict) -> str:
    # Similar to your initial approach
    prompt = (
        "Transform the following user data to JSON format with 'name' and 'email' as "
        "mandatory fields. Combine 'firstname' and 'lastname' into 'name' if necessary. "
        "Include any additional fields as well. The returned JSON MUST follow this structure: "
        "{'name': 'string', 'role': 'string', 'email': 'user@example.com', 'phoneNumber': 'string'}. "
        f"Transform the provided user data accordingly: {json.dumps(user_data)}"
    )
    return prompt


def generate_data_model_from_gpt(prompt: str) -> dict:
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response: Any = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an AI that transforms user data from CSV into a "
                            "structured JSON format for an employee import system."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=512,
                temperature=0.7,
                top_p=0.9,
            )
            data_model = json.loads(response.choices[0].message.content)
            return data_model
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"LLM response parsing error: {e}")
            raise ValueError("Invalid data format returned from GPT-3.")
        except Exception as e:
            logger.error(f"Failed to call GPT: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying GPT call... Attempt {attempt+2}/{max_retries}")
            else:
                raise
    return {}


def validate_data_model(data_model: dict) -> bool:
    """
    Validates the data model ensuring mandatory fields and correct formatting.
    """
    required_fields = ["name", "email"]
    if not all(field in data_model for field in required_fields):
        logger.error(f"Data model missing required fields: {data_model}")
        return False

    if not re.match(EMAIL_REGEX, data_model["email"]):
        logger.error(f"Invalid email format: {data_model.get('email')}")
        return False

    # Check that name isn't empty
    if not data_model["name"].strip():
        logger.error(f"Name is empty: {data_model}")
        return False

    if not all(part.isalpha() for part in data_model["name"].split()):
        logger.error(f"Name contains non-alphabetic characters: {data_model}")
        return False

    return True


def send_data_to_websocket(connection_id, data_models):
    message = json.dumps({"data_models": data_models})
    websocket_url = (
        "https://w2zpvrbvxa.execute-api.eu-central-1.amazonaws.com/development"
    )
    apigw_management_client = boto3.client(
        "apigatewaymanagementapi", endpoint_url=websocket_url
    )

    try:
        apigw_management_client.post_to_connection(
            ConnectionId=connection_id, Data=message.encode("utf-8")
        )
        logger.info("Message sent  to client successfully.")
    except ClientError as e:
        logger.error(f"Failed to send message to WebSocket: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while sending message: {e}")
