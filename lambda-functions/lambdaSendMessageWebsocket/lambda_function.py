import json

import boto3

# Initialize SQS client
sqs_client = boto3.client("sqs")

# Define SQS queue URL
SQS_QUEUE_URL = "https://sqs.eu-central-1.amazonaws.com/381491983037/chequebase-ai-data-mapper-queue"


def lambda_handler(event, context):
    try:
        # Parse the connectionId and CSV data from the event
        connection_id = event["requestContext"]["connectionId"]
        csv_data = event["body"]  # Assuming the CSV data is in the body of the event

        # Send CSV data to SQS with connectionId
        message = {
            "connectionId": connection_id,
            "data": csv_data,  # Sending CSV data directly
        }
        sqs_client.send_message(QueueUrl=SQS_QUEUE_URL, MessageBody=json.dumps(message))

        # Return a 200 status code
        return {"statusCode": 200, "body": json.dumps("Message sent successfully")}
    except Exception as e:
        # Handle unexpected requests
        return {"statusCode": 500, "body": json.dumps(f"Error: {str(e)}")}
