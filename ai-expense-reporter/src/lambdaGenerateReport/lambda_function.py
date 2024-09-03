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

# DynamoDB table name
table_name = "expenseReportTabledevelopment"
table = dynamodb.Table(table_name)


def lambda_handler(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lambda function to handle API requests to retrieve expense reports based on user_id and a date range.

    :param event: The event data passed to the function (contains query parameters such as user_id, start_date, and end_date).
    :param context: The context in which the function is running.
    :return: JSON response containing the expense reports or an error message.
    """
    try:
        # Extract and validate input parameters from the query string
        query_params = event.get("queryStringParameters", {})
        user_id = query_params.get("user_id")
        start_date_str = query_params.get("start_date")
        end_date_str = query_params.get("end_date")

        if not user_id or not start_date_str or not end_date_str:
            raise ValueError(
                "Missing required parameters: 'user_id', 'start_date', or 'end_date'."
            )

        # Parse date strings to datetime objects
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

        if start_date > end_date:
            raise ValueError("'start_date' cannot be later than 'end_date'.")

        # Query DynamoDB
        dynamo_items = query_dynamodb(user_id, start_date_str, end_date_str)

        if not dynamo_items:
            return {
                "statusCode": 404,
                "body": json.dumps(
                    {
                        "message": "No records found for the given user_id and date range."
                    }
                ),
            }

        # Structure the response for the front-end
        structured_response = format_response(
            dynamo_items, user_id, start_date_str, end_date_str
        )

        # Return the structured JSON response
        return {"statusCode": 200, "body": json.dumps(structured_response)}

    except ValueError as ve:
        logger.error(f"Input validation error: {ve}")
        return {"statusCode": 400, "body": json.dumps({"error": str(ve)})}

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"error": "An unexpected error occurred. Please try again later."}
            ),
        }


def query_dynamodb(user_id: str, start_date_str: str, end_date_str: str) -> list:
    """
    Query DynamoDB for expense reports within a date range for a specific user.

    :param user_id: The user ID to query for.
    :param start_date_str: The start date as a string (YYYY-MM-DD).
    :param end_date_str: The end date as a string (YYYY-MM-DD).
    :return: A list of items retrieved from DynamoDB.
    """
    try:
        response = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id)
            & Key("date").between(start_date_str, end_date_str)
        )
        return response.get("Items", [])
    except ClientError as e:
        logger.error(f"Error querying DynamoDB: {e}")
        raise e


def format_response(
    items: list, user_id: str, start_date_str: str, end_date_str: str
) -> Dict[str, Any]:
    """
    Format the DynamoDB items into a structured response for the client.

    :param items: List of items retrieved from DynamoDB.
    :param user_id: The user ID for which the data was queried.
    :param start_date_str: The start date of the query range as a string.
    :param end_date_str: The end date of the query range as a string.
    :return: A structured dictionary response.
    """
    response: Dict[str, Any] = {
        "user_id": user_id,
        "start_date": start_date_str,
        "end_date": end_date_str,
        "reports": [],
    }

    for item in items:
        report = {
            "profile": item.get("user_id"),
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
    client = MongoClient(MONGO_URI)

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
