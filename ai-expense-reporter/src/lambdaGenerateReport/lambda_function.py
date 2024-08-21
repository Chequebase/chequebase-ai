import json
import logging
from datetime import datetime

import boto3
from boto3.dynamodb.conditions import Key

# Initialize logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize the DynamoDB resource
dynamodb = boto3.resource("dynamodb")

# DynamoDB table name
table_name = "expenseReportTabledevelopment"
table = dynamodb.Table(table_name)


def lambda_handler(event, context):
    """
    Lambda function to handle API requests to retrieve expense reports based on user_id and a date range.

    :param event: The event data passed to the function (contains user_id, start_date, and end_date).
    :param context: The context in which the function is running.
    :return: JSON response containing the expense reports or an error message.
    """
    try:
        # Extract and validate input parameters
        user_id = event.get("user_id")
        start_date_str = event.get("start_date")
        end_date_str = event.get("end_date")

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
        response = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id)
            & Key("date").between(start_date_str, end_date_str)
        )

        print("The response is:")
        print(f"{response}")

        items = response.get("Items", [])

        if not items:
            return {
                "statusCode": 404,
                "body": json.dumps(
                    {
                        "message": "No records found for the given user_id and date range."
                    }
                ),
            }

        # Structure the response for the front-end
        structured_response = {
            "user_id": user_id,
            "start_date": start_date_str,
            "end_date": end_date_str,
            "reports": [],
        }

        for item in items:
            report = {
                "profile": item.get("user_id"),
                "business_purpose_description": item.get(
                    "Business_purpose_description"
                ),
                "expense_country": item.get("Expense_country"),
                "receipts_currency": item.get("Receipts_currency"),
                "total_amount": item.get("Total_amount"),
                "payment_date": item.get("Payment_date"),
                "payment_method": item.get("Payment_method"),
                "number_of_participants": item.get("Number_of_participants"),
                "category": item.get("Category"),
                "date": item.get("date"),
            }
            structured_response["reports"].append(report)

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
