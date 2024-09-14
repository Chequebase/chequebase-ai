import json
import logging
from datetime import datetime
from typing import Any, Dict

import boto3

# Initialize logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize the SQS client
sqs = boto3.client("sqs")

# SQS queue URL
QUEUE_URL = "https://sqs.<region>.amazonaws.com/<account-id>/<queue-name>"


def lambda_handler(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lambda function to handle user authentication, authorization, and pass the event to SQS.
    """

    try:

        # Extract query parameters
        query_params = event.get("queryStringParameters", {})
        user_id = query_params.get("user_id")
        start_date_str = query_params.get("start_date")
        end_date_str = query_params.get("end_date")

        if not user_id or not start_date_str or not end_date_str:
            raise ValueError(
                "Missing required parameters: 'user_id', 'start_date', or 'end_date'."
            )

        # Parse dates
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

        if start_date > end_date:
            raise ValueError("'start_date' cannot be later than 'end_date'.")

        # Structure the event data to send to SQS
        sqs_message = {
            "user_id": user_id,
            "start_date": start_date_str,
            "end_date": end_date_str,
        }

        # Send the message to the SQS queue
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(sqs_message))

        return {
            "statusCode": 200,
            "body": json.dumps(
                {"message": "Request successfully queued for processing."}
            ),
        }

    except ValueError as ve:
        logger.error(f"Input validation error: {ve}")
        return {"statusCode": 400, "body": json.dumps({"error": str(ve)})}

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "An unexpected error occurred."}),
        }
