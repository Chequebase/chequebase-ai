import json
import os
import time
import urllib.parse

import boto3


def lambda_handler(event, context):
    try:
        # Initialize clients for S3 and Textract
        s3 = boto3.client("s3")
        textract = boto3.client("textract")

        # Process each S3 event record
        for record in event["Records"]:
            # Extract the bucket name and object key from the S3 event
            bucket_name = record["s3"]["bucket"]["name"]
            s3_object_key = record["s3"]["object"]["key"]

            # Url decode the s3 object key
            s3_object_key = urllib.parse.unquote_plus(s3_object_key)
            print(
                f"Starting Textract job for file: {s3_object_key} in bucket: {bucket_name}"
            )

            # Start Textract job
            response = textract.start_document_text_detection(
                DocumentLocation={
                    "S3Object": {"Bucket": bucket_name, "Name": s3_object_key}
                }
            )

            job_id = response["JobId"]
            print(f"Started Textract job with ID: {job_id}")

            # Extract the user_id and file name from the S3 object key
            user_id = s3_object_key.split("/")[0]
            file_name = os.path.basename(s3_object_key)

            # Polling for Textract job completion and extracting text
            result_text = extract_text_from_textract(textract, job_id)

            # Save extracted text to S3 as a .txt file in the same bucket
            output_key = f"{user_id}/{os.path.splitext(file_name)[0]}.txt"
            s3.put_object(Bucket=bucket_name, Key=output_key, Body=result_text)

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Textract job completed successfully"}),
        }

    except Exception as e:
        print(f"Error processing Textract job: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def extract_text_from_textract(textract, job_id):

    # Polling to wait for the job to complete
    while True:
        response = textract.get_document_text_detection(JobId=job_id)
        status = response["JobStatus"]

        if status in ["SUCCEEDED", "FAILED"]:
            break

        time.sleep(5)

    if status == "SUCCEEDED":
        detected_text = []
        for item in response["Blocks"]:
            if item["BlockType"] == "LINE":
                detected_text.append(item["Text"])
        return "\n".join(detected_text)

    raise Exception("Textract job failed")
