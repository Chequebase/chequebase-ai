import os
import base64
import json
from upload.uploader import S3Uploader
from dotenv import load_dotenv

# Determine which environment file to load
environment = os.getenv('ENVIRONMENT', 'dev')  # Default to 'dev' if ENVIRONMENT is not set

if environment == 'prod':
    load_dotenv('.env.prod')
elif environment == 'staging':
    load_dotenv('.env.staging')
else:
    load_dotenv('.env.dev')

def lambda_handler(event, context):
    try:
        # Extract credentials and other information from environment variables
        bucket_name = os.getenv('BUCKET_NAME', 'ch-expense-input-bucket')
        aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        region_name = os.getenv('AWS_REGION', 'eu-central-1')

        # Extract user ID and any additional metadata from the request
        user_id = event['headers'].get('User-ID')
        processing_status = 'uploaded'

        # Create an instance of S3Uploader
        uploader = S3Uploader(
            bucket_name=bucket_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name
        )

        # Helper function to upload a single file with tags
        def upload_with_tags(file_content, content_type):
            response = uploader.upload_file(
                file_content, 
                content_type, 
                ExtraArgs={
                    'Tagging': f"user-id={user_id}&processing-status={processing_status}"
                }
            )
            return response

        # If the request is a single file
        if isinstance(event['body'], str):
            file_content = base64.b64decode(event['body'])
            content_type = event['headers']['Content-Type']
            response = upload_with_tags(file_content, content_type)

        # If the request contains multiple files 
        elif isinstance(event['body'], list):
            responses = []
            for file_data in event['body']:
                file_content = base64.b64decode(file_data)
                content_type = event['headers']['Content-Type']  
                response = upload_with_tags(file_content, content_type)
                responses.append(response)
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Files uploaded successfully', 'results': responses})
            }

        return response

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }