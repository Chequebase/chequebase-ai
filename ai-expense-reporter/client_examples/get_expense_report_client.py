import datetime

import boto3
import requests
from aws_requests_auth.aws_auth import AWSRequestsAuth

# AWS region and service information
region = "eu-central-1"
service = "execute-api"

# API Gateway endpoint
endpoint = "https://84vtt8xp3f.execute-api.eu-central-1.amazonaws.com/development/chequebase-ai-getExpenseReport"

# JWT payload for user authentication
company_id = "user123"
expiration = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
    minutes=5
)
start_date = "2024-01-01"
end_date = "2024-12-31"

# Convert datetime objects to UNIX timestamps (seconds since epoch)
iat_timestamp = datetime.datetime.now(datetime.UTC).timestamp()
exp_timestamp = expiration.timestamp()

# JWT payload for internal authentication
payload = {
    "sub": company_id,
    "exp": expiration,
    "iat": iat_timestamp,  # Issued at time
    "permissions": ["fetch_expense_reports"],
}


# Get AWS credentials from the environment or AWS CLI configuration
session = boto3.Session()
credentials = session.get_credentials()

# Create AWSRequestsAuth to handle SigV4 signing
auth = AWSRequestsAuth(
    aws_access_key=credentials.access_key,
    aws_secret_access_key=credentials.secret_key,
    aws_token=credentials.token,
    aws_host="84vtt8xp3f.execute-api.eu-central-1.amazonaws.com",
    aws_region=region,
    aws_service="execute-api",
)

# Headers including the JWT for application-level authentication
headers = {
    "Authorization": "updatetojwt",  # TODO Update to jwt
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Query parameters for the API Gateway request
params = {
    "company_id": company_id,
    "start_date": start_date,
    "end_date": end_date,
}


# Make the GET request to API Gateway
response = requests.put(endpoint, auth=auth, headers=headers, params=params)

# Output the response for debugging
print(f"Response Code: {response.status_code}")
print(f"Response Body: {response.text}")
