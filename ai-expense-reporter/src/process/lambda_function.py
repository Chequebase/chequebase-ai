import os
import boto3
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def lambda_handler(event, context):
    try:
        # Extract necessary environment variables
        bucket_name = os.getenv('BUCKET_NAME', 'ch-expense-input-bucket')
        processed_status = 'processed'

        s3 = boto3.client('s3')
        textract = boto3.client('textract')
        
        # Iterate over S3 event records
        for record in event['Records']:
            s3_object_key = record['s3']['object']['key']

            # Get object tags to filter based on 'processing-status'
            tagging_response = s3.get_object_tagging(
                Bucket=bucket_name,
                Key=s3_object_key
            )
            tags = {tag['Key']: tag['Value'] for tag in tagging_response['TagSet']}

            if tags.get('processing-status') == 'uploaded':
                # Start Textract job
                response = textract.detect_document_text(
                    Document={
                        'S3Object': {
                            'Bucket': bucket_name,
                            'Name': s3_object_key
                        }
                    }
                )

                # Extract detected text
                detected_text = []
                for item in response['Blocks']:
                    if item['BlockType'] == 'LINE':
                        detected_text.append(item['Text'])
                
                # Save extracted text to S3 as a .txt file in the same bucket with an updated tag
                output_key = f"{os.path.splitext(s3_object_key)[0]}.txt"
                s3.put_object(
                    Bucket=bucket_name,
                    Key=output_key,
                    Body='\n'.join(detected_text)
                )

                # Update the tags on the original file to indicate it has been processed
                s3.put_object_tagging(
                    Bucket=bucket_name,
                    Key=s3_object_key,
                    Tagging={
                        'TagSet': [
                            {'Key': 'user-id', 'Value': tags['user-id']},
                            {'Key': 'processing-status', 'Value': processed_status}
                        ]
                    }
                )

        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Textract processing completed successfully'})
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }