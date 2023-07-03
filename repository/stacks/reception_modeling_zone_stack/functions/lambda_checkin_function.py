import os
import json
import urllib.parse
import boto3
        
def handler(event, context):
# Get the object from the event and show its content type
    s3 = boto3.client('s3')

    # Check if there are any new records in the event
    if 'Records' in event and len(event['Records']) > 0:
        for record in event['Records']:
            # Extract the bucket name and key of the newly uploaded object
            s3_bucket = record['s3']['bucket']['name']
            key = urllib.parse.unquote_plus(record['s3']['object']['key'], encoding='utf-8')
            
            print(s3_bucket)
            print(key)

            # Check if the key has a specific prefix and rename the object
            if key.startswith('input_data/'):
                stripped_key = key.replace("input_data/", "")
                print(stripped_key)
                new_key_renamed = 'raw_data/' + stripped_key
                print(new_key_renamed)
                
                s3.copy_object(
                 Bucket=s3_bucket,
                 CopySource={'Bucket': s3_bucket, 'Key': key},
                 Key=new_key_renamed
                )