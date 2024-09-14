import json
import logging
from datetime import datetime
from typing import Any, Dict

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from pymongo import MongoClient

# Initialize logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize the DynamoDB resource
dynamodb = boto3.resource("dynamodb")

# Initialize the S3 client
s3_client = boto3.client("s3")

# DynamoDB table name and S3 bucket name
table_name = "expenseReportTabledevelopment"
table = dynamodb.Table(table_name)
s3_bucket_name = "chequebase-develop-file-upload-bucket"


def lambda_handler(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lambda function to handle SQS messages, extract expense report data, query DynamoDB, and save the result as a JSON file in S3.

    The function is triggered by SQS messages, where each message contains the company_id, start_date, and end_date.
    """
    try:
        for record in event["Records"]:
            # Extract body from SQS message and parse it as JSON
            message_body = json.loads(record["body"])

            # Extract parameters from the message
            company_id = message_body.get("company_id")
            start_date_str = message_body.get("start_date")
            end_date_str = message_body.get("end_date")

            if not company_id or not start_date_str or not end_date_str:
                logger.error(
                    "Missing required parameters: 'company_id', 'start_date', or 'end_date'."
                )
                continue

            # Parse date strings to datetime objects
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

            if start_date > end_date:
                logger.error("'start_date' cannot be later than 'end_date'.")
                continue

            # Query DynamoDB
            dynamo_items = query_dynamodb(company_id, start_date_str, end_date_str)

            if not dynamo_items:
                logger.info(
                    f"No records found for company_id {company_id} and date range {start_date_str} to {end_date_str}."
                )
                continue

            # Structure the response for the front-end
            structured_response = format_response(
                dynamo_items, company_id, start_date_str, end_date_str
            )

            # Generate the current date for the filename
            current_date = datetime.now().strftime("%Y-%m-%d")

            # Save the JSON to S3 in the expenseReports subfolder
            s3_key = f"{company_id}/expenseReports/expense_report_{current_date}.json"
            save_to_s3(structured_response, s3_key)

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Reports processed successfully."}),
        }

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"error": "An unexpected error occurred. Please try again later."}
            ),
        }


def query_dynamodb(company_id: str, start_date_str: str, end_date_str: str) -> list:
    """
    Query DynamoDB for expense reports within a date range for a specific company.

    :param company_id: The company ID to query for.
    :param start_date_str: The start date as a string (YYYY-MM-DD).
    :param end_date_str: The end date as a string (YYYY-MM-DD).
    :return: A list of items retrieved from DynamoDB.
    """
    try:
        response = table.query(
            KeyConditionExpression=Key("user_id").eq(company_id)
            & Key("date").between(start_date_str, end_date_str)
        )  # TODO Change the user_id key to company_id
        return response.get("Items", [])
    except ClientError as e:
        logger.error(f"Error querying DynamoDB: {e}")
        raise e


def format_response(
    items: list, company_id: str, start_date_str: str, end_date_str: str
) -> Dict[str, Any]:
    """
    Format the DynamoDB items into a structured response for the client.

    :param items: List of items retrieved from DynamoDB.
    :param company_id: The company ID for which the data was queried.
    :param start_date_str: The start date of the query range as a string.
    :param end_date_str: The end date of the query range as a string.
    :return: A structured dictionary response.
    """
    response: Dict[str, Any] = {
        "company_id": company_id,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "reports": [],
    }

    for item in items:
        report = {
            "profile": item.get("company_id"),
            "business_purpose_description": item.get("Business_purpose_description"),
            "expense_country": item.get("Expense_country"),
            "receipts_currency": item.get("Receipts_currency"),
            "total_amount": item.get("Total_amount"),
            "payment_date": item.get("Payment_date"),
            "payment_method": item.get("Payment_method"),
            "number_of_participants": item.get("Number_of_participants"),
            "category": item.get("Category"),
            "date": item.get("date"),
        }
        response["reports"].append(report)

    return response


def save_to_s3(json_data: Dict[str, Any], s3_key: str):
    """
    Save the structured JSON data to an S3 bucket.

    :param json_data: The structured JSON data to save.
    :param s3_key: The S3 object key (file path) where the JSON file will be saved.
    """
    try:
        # Convert the JSON data to a string
        json_body = json.dumps(json_data, indent=2)

        # Save the file to S3
        s3_client.put_object(
            Bucket=s3_bucket_name,
            Key=s3_key,
            Body=json_body,
            ContentType="application/json",
        )

        logger.info(f"Successfully saved report to S3: {s3_key}")

    except ClientError as e:
        logger.error(f"Failed to save report to S3: {e}")
        raise e


def get_mongo_client() -> MongoClient:
    """
    Creates and returns a MongoDB client using AWS IAM authentication.

    :return: A MongoDB client instance.
    """
    # Initialize AWS session and credentials
    session = boto3.Session()
    credentials = session.get_credentials()
    aws_access_key_id = credentials.access_key
    aws_secret_access_key = credentials.secret_key
    aws_session_token = credentials.token

    # MongoDB connection string using AWS IAM authentication
    MONGO_URI = (
        f"mongodb+srv://{aws_access_key_id}:{aws_secret_access_key}@cluster0.cx1ni.mongodb.net/?"
        f"authSource=%24external&authMechanism=MONGODB-AWS&retryWrites=true&w=majority&"
        f"authMechanismProperties=AWS_SESSION_TOKEN:{aws_session_token}&appName=Cluster"
    )

    # Initialize MongoDB client
    client: MongoClient = MongoClient(MONGO_URI)

    return client


def get_wallet_entries_mongo(
    client: MongoClient, user_id: str, start_date: datetime, end_date: datetime
) -> list:
    """
    Query MongoDB for wallet entries within a date range for a specific user.

    :param client: MongoDB client instance.
    :param user_id: The user ID to query for.
    :param start_date: The start date as a datetime object.
    :param end_date: The end date as a datetime object.
    :return: A list of wallet entries retrieved from MongoDB.
    """
    try:
        # Access the database and collection
        db = client["chequebase-staging"]
        wallet_collection = db["walletentries"]

        # Query MongoDB collections
        wallet_entries = list(
            wallet_collection.find(
                {
                    "organization": user_id,
                    "meta.createdAt": {"$gte": start_date, "$lte": end_date},
                    "scope": {"$in": ["wallet_transfer", "budget_transfer"]},
                }
            )
        )

        return wallet_entries
    except Exception as e:
        logger.error(f"Error querying MongoDB: {e}")
        return []
