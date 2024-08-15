import json

import boto3
from dateutil.parser import parse as parse_date  # type: ignore


def lambda_handler(event, context):
    # Initialize the S3 client
    s3 = boto3.client("s3")

    # Extract the inputs from the event
    user_id = event["user_id"]
    start_date = parse_date(event["start_date"])
    end_date = parse_date(event["end_date"])
    bucket_name = "your-s3-bucket-name"

    # List objects in the user's folder in the S3 bucket
    user_prefix = f"{user_id}/"
    response = s3.list_objects_v2(Bucket=bucket_name, Prefix=user_prefix)

    if "Contents" not in response:
        return {
            "statusCode": 404,
            "body": json.dumps({"message": "No files found for the user."}),
        }

    # Filter files by date range
    filtered_files = []
    for obj in response["Contents"]:
        metadata = s3.head_object(Bucket=bucket_name, Key=obj["Key"])
        last_modified = metadata["LastModified"]

        # Check if the file is within the specified date range and is a .txt file
        if start_date <= last_modified <= end_date and obj["Key"].endswith(".txt"):
            filtered_files.append(obj["Key"])

    if not filtered_files:
        return {
            "statusCode": 404,
            "body": json.dumps({"message": "No files found within the date range."}),
        }

    # Read the contents of the filtered .txt files
    all_texts = ""
    for key in filtered_files:
        txt_object = s3.get_object(Bucket=bucket_name, Key=key)
        txt_content = txt_object["Body"].read().decode("utf-8")
        all_texts += txt_content + "\n\n"

    # Define the prompt for the LLM
    prompt = (
        "You are an AI that generates expense reports. "
        "Based on the text provided, create a summary of the user's expenses "
        "within the specified date range. Use the following standard expense report template:\n\n"
        "Expense Report:\n"
        "-----------------\n"
        "Date Range: {} - {}\n"
        "User ID: {}\n\n"
        "Expenses:\n\n"
        "{}"
    ).format(event["start_date"], event["end_date"], user_id, all_texts)

    # Here we mock an LLM call. Replace this with actual LLM integration.
    expense_summary = generate_expense_report_from_llm(prompt)

    # Return the generated expense summary
    return {"statusCode": 200, "body": json.dumps({"expense_report": expense_summary})}


def generate_expense_report_from_llm(prompt):
    # This is a placeholder function for LLM interaction.

    # For example, with OpenAI GPT-4, you might use the openai Python package:
    # import openai
    # response = openai.Completion.create(
    #     engine="text-davinci-003",
    #     prompt=prompt,
    #     max_tokens=500
    # )
    # return response['choices'][0]['text'].strip()

    # Mock response (for demonstration purposes)
    return (
        "Expense Report:\n"
        "-----------------\n"
        "Date Range: {}\n"
        "User ID: {}\n\n"
        "Expenses:\n"
        "1. Date: 2024-08-01, Description: Grocery shopping, Amount: $150.00\n"
        "2. Date: 2024-08-03, Description: Utility bill, Amount: $200.00\n"
        "3. Date: 2024-08-05, Description: Restaurant, Amount: $75.00\n"
        "Total Expenses: $425.00"
    )
