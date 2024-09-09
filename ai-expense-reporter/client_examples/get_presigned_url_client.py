import json
import mimetypes

import boto3
import requests
from aws_requests_auth.aws_auth import AWSRequestsAuth

# Replace these values with actual data
file_paths = (
    r"/Users/divinefavourodion/Downloads/chequebase-ai/assets/receipt_texts_final/receipt_sample_1.txt,"
    r"/Users/divinefavourodion/Downloads/chequebase-ai/assets/receipt_texts_final/receipt_sample_166.txt"
)


api_url = "https://84vtt8xp3f.execute-api.eu-central-1.amazonaws.com/development/chequebase-ai-uploadToS3"
company_id = "user123"


# Step 1: Get AWS credentials from the environment or session
session = boto3.Session()
credentials = session.get_credentials()

# Step 2: Create AWSRequestsAuth to handle SigV4 signing
auth = AWSRequestsAuth(
    aws_access_key=credentials.access_key,
    aws_secret_access_key=credentials.secret_key,
    aws_token=credentials.token,  # In case you're using temporary credentials (optional)
    aws_host="84vtt8xp3f.execute-api.eu-central-1.amazonaws.com",  # The host of your API Gateway
    aws_region="eu-central-1",  # The AWS region
    aws_service="execute-api",  # The AWS service you're interacting with
)

file_contents = []

# Step 3: Read the file content
for file_path in file_paths.split(","):

    with open(file_path, "rb") as file:
        file_contents.append(file.read())


# Step 4: Make the request to get the pre-signed URL (with AWS Signature v4 authentication)
response = requests.post(
    api_url, json={"company_id": company_id, "filenames": str(file_paths)}, auth=auth
)

# Step 5: Check the response status and handle accordingly
if response.status_code == 200:
    response_data = response.json()
    body = response_data["body"]
    # Parse the presigned_urls from the response body
    if "presigned_urls" in body:

        presigned_urls = json.loads(body["presigned_urls"])

        # Iterate through the presigned URLs and print them
        for file_name, url_info in presigned_urls.items():
            presigned_url = url_info["presigned_url"]
            print(f"File: {file_name}\nPresigned URL: {presigned_url}\n")

        # Step 6: Upload each file using the corresponding pre-signed URL
        for i, file_path in enumerate(file_paths.split(",")):

            # Upload the file to S3 using the presigned URL
            presigned_url = presigned_urls[file_path]["presigned_url"]
            content_type, _ = mimetypes.guess_type(file_path)  # Detect content type
            headers = {"Content-Type": content_type or "application/octet-stream"}

            upload_response = requests.put(
                presigned_url, data=file_contents[i], headers=headers
            )
            if upload_response.status_code == 200:
                print(f"File uploaded successfully: {file_name}")
            else:
                print(f"Failed to upload {file_name}: {upload_response.text}")
    else:
        print("No presigned URLs found in the response.")
else:
    print(f"Error getting pre-signed URL: {response.status_code} - {response.text}")
