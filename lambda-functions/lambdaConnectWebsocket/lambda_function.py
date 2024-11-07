import json
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

# Initialize logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB and SQS clients
dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")
table_name = "WebSocketSessions"
table = dynamodb.Table(table_name)


def lambda_handler(event, context):
    """
    Handles new WebSocket connections by logging session information to DynamoDB.
    """
    logger.info("Handling WebSocket $connect event")
    logger.info(f"Received event: {json.dumps(event)}")
    print(f"The event is {str(event)}")

    connection_id = event["requestContext"]["connectionId"]
    timestamp = int(datetime.now(timezone.utc).timestamp())

    source_ip = event["requestContext"].get("identity", {}).get("sourceIp", "Unknown")

    # Construct the item to store in DynamoDB
    item = {
        "connectionId": connection_id,
        "timestamp": timestamp,
        "sourceIp": source_ip,
        "status": "connected",
    }

    try:
        # Store the connection information in DynamoDB
        table.put_item(Item=item)
        logger.info(f"Connection ID {connection_id} logged successfully")
    except ClientError as e:
        logger.error(f"Error logging connection ID {connection_id}: {e}")
        return {"statusCode": 500, "body": "Failed to connect"}
    except Exception as e:
        logger.error(f"Error storing data in DynamoDB: {e}")
        return {"statusCode": 500, "body": "Failed to store data in DynamoDB"}

    return {"statusCode": 200, "body": "Connected"}
