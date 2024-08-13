import json
import boto3
import uuid
from botocore.exceptions import ClientError

class S3Uploader:
    def __init__(self, bucket_name, aws_access_key_id=None, aws_secret_access_key=None, region_name=None):
        self.bucket_name = bucket_name
        self.s3 = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name
        )
    
    def upload_file(self, file_content, content_type):
        try:
            # Generate a unique filename
            file_name = str(uuid.uuid4()) + ".jpg"  # Assuming the file is a JPEG. Adjust as needed.

            # Upload the file to the S3 bucket
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=file_name,
                Body=file_content,
                ContentType=content_type
            )
            
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'File uploaded successfully', 'file_name': file_name})
            }
        
        except ClientError as e:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': str(e)})
            }
        except Exception as e:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': str(e)})
            }