import json

import boto3
from botocore.exceptions import ClientError

# Initialize S3 client
s3_client = boto3.client("s3")


def lambda_handler(event, context):

    company_id = event["company_id"]
    file_name_list = event["filenames"].split(",")

    if not company_id or not file_name_list:
        return {
            "statusCode": 400,
            "body": "Missing required query parameters: company_id or filenames",
        }

    # S3 bucket name (set this in Lambda environment variables)
    bucket_name = "chequebase-develop-file-upload-bucket"

    # Dictionary to store the pre-signed URLs
    presigned_urls = {}

    try:
        # Generate pre-signed URLs for each file
        for file_name in file_name_list:
            # Construct the S3 object key with the company_id as the "folder"
            object_key = f"{company_id}/{file_name.strip()}"

            # Generate the pre-signed URL for each file
            presigned_url = s3_client.generate_presigned_url(
                "put_object",
                Params={"Bucket": bucket_name, "Key": object_key},
                ExpiresIn=3600,  # URLs expire in 1 hour
            )

            # Append the presigned URL and its corresponding file name to the result list
            presigned_urls[file_name.strip()] = {"presigned_url": presigned_url}

        # Return the list of pre-signed URLs as the response
        return {
            "statusCode": 200,
            "body": {
                "company_id": company_id,
                "presigned_urls": json.dumps(presigned_urls),
            },
        }

    except ClientError as e:
        return {
            "statusCode": 500,
            "body": f"Error generating pre-signed URLs: {str(e)}",
        }
