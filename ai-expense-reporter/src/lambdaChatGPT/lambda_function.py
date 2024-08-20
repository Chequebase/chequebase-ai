import json
import logging
import re

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from openai import OpenAI

# Initialize logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


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
client = OpenAI(api_key=secret["openai"])


def lambda_handler(event, context):
    """
    Lambda handler function to process a single document from S3 and generate
    an expense report using an LLM model.

    :param event: The event data passed to the function (contains information about the uploaded S3 object).
    :param context: The context in which the function is running.
    :return: JSON response containing the extracted fields or an error message.
    """

    # Initialize the S3 client
    s3 = boto3.client("s3")

    try:
        for record in event["Records"]:
            # Extract the bucket name and object key from the S3 event
            bucket_name = record["s3"]["bucket"]["name"]
            file_key = record["s3"]["object"]["key"]

            # Read the content of the uploaded text file
            txt_object = s3.get_object(Bucket=bucket_name, Key=file_key)
            txt_content = txt_object["Body"].read().decode("utf-8")

            # Generate the prompt for the LLM
            prompt = generate_llm_prompt(file_key, txt_content)

            # Call GPT-4o
            expense_summary = generate_expense_report_from_gpt3_5(prompt)

            # Check if the response is empty
            if not expense_summary:
                raise ValueError("The model's response was empty.")

            # Use a regular expression to extract the JSON part if there are extraneous characters
            json_match = re.search(r"\{.*\}", expense_summary, re.DOTALL)

            if json_match:
                json_string = json_match.group(0)
            else:
                raise ValueError("No valid JSON object found in the model's response.")

            try:
                structured_report = json.loads(json_string)
                logger.info("Successfully parsed JSON")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse model response as JSON: {e}")
                raise ValueError("The model's response could not be parsed as JSON.")

            # Return the generated expense summary as JSON
            return {
                "statusCode": 200,
                "body": json.dumps({"expense_report": structured_report}),
            }

    except ValueError as ve:
        logger.error(f"Input validation error: {ve}")
        return {"statusCode": 400, "body": json.dumps({"error": str(ve)})}

    except (ClientError, BotoCoreError) as e:
        logger.error(f"AWS error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"error": "An internal error occurred. Please try again later."}
            ),
        }

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"error": "An unexpected error occurred. Please try again later."}
            ),
        }


def generate_llm_prompt(file_key, txt_content):
    """
    Generate the prompt for the LLM to request specific fields.

    :param file_key: The key (name) of the file in S3.
    :param txt_content: The content of the text file.
    :return: Formatted prompt string.
    """
    example_json = {
        "Profile": "...",
        "Business_purpose_description": "...",
        "Expense_country": "...",
        "Receipts_currency": "...",
        "Total_amount": "...",
        "Payment_date": "...",
        "Payment_method": "...",
        "Number_of_participants": "...",
        "Category": "Travel",
    }

    # Convert the example JSON to a formatted string
    example_json_str = json.dumps(example_json, indent=2)

    prompt = (
        "Human: You are an AI specialized in generating detailed and accurate expense reports. "
        "Please extract the following fields from the provided text and return a single JSON object:\n"
        "1. Profile\n"
        "2. Business purpose/description\n"
        "3. Expense country\n"
        "4. Receipts currency\n"
        "5. Total amount\n"
        "6. Payment date\n"
        "7. Payment method\n"
        "8. Number of participants\n"
        "9. Category\n\n"
        "The response should be in JSON format as follows (note that this is just an template for you to use):\n"
        f"{example_json_str}\n\n"
        "Please ensure the response is well-structured and contains all the fields requested. "
        "If any field is missing, return it with a null value.\n\n"
        f"File Name: {file_key}\n"
        f"{txt_content}\n"
        "Lastly, please ensure that the returned output is always JSON.\n"
        "Assistant:"
    )

    return prompt


def generate_expense_report_from_gpt3_5(prompt):
    """
    Call OpenAI’s GPT-4o model to generate the expense report summary with specific fields.

    :param prompt: The generated prompt for the LLM.
    :return: Generated expense report summary.
    :raises Exception: If there's an error calling the OpenAI API.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "You are an AI that specializes in generating detailed and accurate expense reports.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
            temperature=0.7,
            top_p=0.9,
        )

        # Correctly extract the message content
        expense_summary = response.choices[0].message.content

        return expense_summary

    except Exception as e:
        logger.error(f"Failed to generate expense report from GPT-4: {e}")
        raise
