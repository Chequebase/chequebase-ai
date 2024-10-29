import csv
import json
import logging
import os
import re
from datetime import datetime
from typing import Any

import boto3
import pymongo
from botocore.exceptions import ClientError
from bson.objectid import ObjectId
from openai import OpenAI
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

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
openai_client = OpenAI(api_key=secret["openai"])
MONGO_USER = os.getenv("MONGO_USER")
MONGO_USER_PASSWORD = os.getenv("MONGO_USER_PASSWORD")


def lambda_handler(event, context):
    # Parse file_path from the Lambda event if passed directly as an argument
    file_path = event.get("file_path")
    organization = event.get("organization")
    if not file_path:
        logger.error("File path not provided in event query parameters.")
        raise ValueError("File path not provided in event query parameters.")
    if not organization:
        logger.error("Organization not provided in event query parameters")
        raise ValueError("Organization not provided in event query parameters")

    # Connect to MongoDB
    uri = (
        f"mongodb+srv://{MONGO_USER}:{MONGO_USER_PASSWORD}@cluster0.cx1ni.mongodb.net/"
        f"?retryWrites=true&w=majority&appName=Cluster0"
    )
    client = MongoClient(uri, server_api=ServerApi("1"))
    db = client["chequebase-staging"]
    users_collection = db["users"]

    try:
        # Read the CSV file
        with open(file_path, mode="r") as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                # Prepare the prompt and get the LLM response
                prompt = generate_llm_prompt(row)
                try:
                    data_model = generate_data_model_from_gpt(prompt)

                    # Add constant fields to the data model
                    data_model["status"] = "active"  # Fixed value
                    data_model["createdAt"] = datetime.now().isoformat()
                    data_model["updatedAt"] = datetime.now().isoformat()
                    data_model["organization"] = ObjectId(organization)

                except Exception as e:
                    logger.warning(f"Skipping row due to LLM error: {e}")
                    continue

                # Validate and transform the data model
                if validate_data_model(data_model):
                    # Update MongoDB with validated data
                    update_database(users_collection, data_model)
                else:
                    logger.warning(
                        f"Skipping row due to validation failure: {data_model}"
                    )

    except Exception as e:
        logger.error(f"Error processing CSV file: {e}")
        raise
    finally:
        # Clean up MongoDB connections
        client.close()


def generate_llm_prompt(user_data: dict) -> str:
    # Constructs a prompt based on CSV row data
    prompt = (
        f"Transform the following user data to JSON format with 'firstName', 'lastName', and 'email' as "
        "mandatory fields. Include any additional fields as well: "
        f"{json.dumps(user_data)}"
    )
    return prompt


def generate_data_model_from_gpt(prompt: str) -> dict:
    """
    Call OpenAI’s GPT-4 model to map data from CSV to Data model.

    :param prompt: The generated prompt for the LLM.
    :return: Generated data model as dictionary.
    :raises Exception: If there's an error calling the OpenAI API.
    """
    max_retries = 2  # Number of retries
    for attempt in range(max_retries + 1):  # +1 for the initial attempt
        try:
            response: Any = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an AI that specializes in transforming user data from csv into a "
                            "structured format for MongoDB."
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
    required_fields = ["firstName", "lastName", "email"]

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
    if not data_model["firstName"].isalpha() or not data_model["lastName"].isalpha():
        logger.error(f"Name fields contain non-alphabetic characters: {data_model}")
        return False

    return True


def update_database(users_collection, data_model: dict):
    """
    Updates MongoDB with the provided data model.

    :param users_collection: MongoDB collection to update.
    :param data_model: The validated data model to upsert.
    """
    try:
        # Check if a user with the same firstName, lastName, and email exists
        existing_user = users_collection.find_one(
            {
                "firstName": data_model["firstName"],
                "lastName": data_model["lastName"],
                "email": data_model["email"],
            }
        )

        if existing_user:
            logger.info(
                f"User with email {data_model['email']} already exists. Skipping insertion."
            )
            return  # Skip insertion if user already exists

        # Proceed to insert the new user since no matching user was found
        users_collection.insert_one(data_model)
        logger.info(f"Inserted new user with email {data_model['email']}")

    except pymongo.errors.PyMongoError as e:
        logger.error(f"MongoDB update error for {data_model['email']}: {e}")
        raise
