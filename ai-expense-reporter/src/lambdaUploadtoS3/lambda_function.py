import base64
import json

import boto3


def lambda_handler(event, context):
    try:
        # Initialize the S3 client
        s3 = boto3.client("s3")
        bucket_name = "chequebase-develop-file-upload-bucket"

        # Parse the JSON body from the event
        body = json.loads(event["body"])

        # Extract user_id and files from the parsed body
        user_id = body.get("user_id")
        files = body.get("files")

        if not user_id:
            raise ValueError("The 'user_id' key is missing in the request body.")

        if not files:
            raise ValueError("The 'files' key is missing in the request body.")

        # Check if the user folder exists in the S3 bucket
        folder_exists = check_folder_exists(s3, bucket_name, user_id)
        if not folder_exists:
            # Create a folder by creating an empty object with the folder name
            create_folder(s3, bucket_name, user_id)

        responses = []  # To collect responses for each file upload

        # Process each file in the list
        for file in files:
            file_content = base64.b64decode(file["file"])
            file_name = file["file_name"]
            content_type = file.get("content_type", "application/octet-stream")

            # Construct the S3 key with the user_id as a folder
            s3_key = f"{user_id}/{file_name}"

            # Upload the file to S3
            s3.put_object(
                Bucket=bucket_name,
                Key=s3_key,
                Body=file_content,
                ContentType=content_type,
            )

            responses.append(
                {
                    "file_name": file_name,
                    "status": "File uploaded successfully",
                    "s3_key": s3_key,
                }
            )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {"message": "Files uploaded successfully", "uploads": responses}
            ),
        }

    except Exception as e:
        print(f"Error uploading files: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def check_folder_exists(s3, bucket_name, folder_name):
    """
    Check if a folder exists in the S3 bucket.

    :param s3: S3 client object
    :param bucket_name: Name of the S3 bucket
    :param folder_name: Name of the folder to check
    :return: True if the folder exists, False otherwise
    """
    response = s3.list_objects_v2(
        Bucket=bucket_name, Prefix=f"{folder_name}/", Delimiter="/"
    )
    return "Contents" in response


def create_folder(s3, bucket_name, folder_name):
    """
    Create a folder in the S3 bucket.

    :param s3: S3 client object
    :param bucket_name: Name of the S3 bucket
    :param folder_name: Name of the folder to create
    """
    s3.put_object(Bucket=bucket_name, Key=f"{folder_name}/")
