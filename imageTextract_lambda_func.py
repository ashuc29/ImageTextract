import json
import boto3

def lambda_handler(event, context):
    s3_client = boto3.client('s3')
    textract_client = boto3.client('textract')
    sns_client = boto3.client('sns')
    dynamodb_client = boto3.client('dynamodb')

    sns_topic_arn = 'arn:aws:sns:eu-west-1:559050216210:ashuTextract'
    dynamodb_table_name = 'Ashwini_table'

    try:
        print(f"Received event: {json.dumps(event)}")
        
        if 'Records' not in event or not event['Records']:
            raise ValueError("Invalid event format: Missing 'Records' field for S3 event.")
        
        bucket_name = event['Records'][0]['s3']['bucket']['name']
        object_key = event['Records'][0]['s3']['object']['key']
        print(f"Processing file from bucket: {bucket_name}, key: {object_key}")

        # Get the object's metadata
        head_response = s3_client.head_object(Bucket=bucket_name, Key=object_key)
        content_type = head_response.get('ContentType', 'unknown')
        file_size = head_response.get('ContentLength', 'unknown')
        print(f"Content Type: {content_type}, File Size: {file_size} bytes")

        # Validate the file type
        supported_types = ['image/jpeg', 'image/png', 'application/pdf']
        if content_type not in supported_types:
            raise ValueError(f"Unsupported document format: {content_type} for file: {object_key}")

        # Call Textract to analyze the document
        try:
            print(f"Calling Textract for file {object_key} from bucket {bucket_name}...")
            response = textract_client.detect_document_text(
                Document={
                    'S3Object': {
                        'Bucket': bucket_name,
                        'Name': object_key
                    }
                }
            )
            print(f"Textract response: {json.dumps(response)}")
        except textract_client.exceptions.UnsupportedDocumentException as e:
            print(f"Textract exception: {str(e)}")
            raise ValueError(f"Unsupported document format for file: {object_key}") from e
        except textract_client.exceptions.InvalidParameterException as e:
            print(f"Invalid Parameter exception from Textract: {str(e)}")
            raise ValueError(f"Invalid file for Textract: {object_key}") from e
        except Exception as e:
            print(f"Error calling Textract: {str(e)}")
            raise RuntimeError(f"Textract error for file: {object_key}") from e

        # Extract the text from the Textract response
        extracted_text = "\n".join(
            block['Text'] for block in response.get('Blocks', []) if block['BlockType'] == 'LINE'
        )
        print(f"Extracted Text: {extracted_text}")

        if not extracted_text.strip():
            raise ValueError(f"No text was extracted from file: {object_key}. It might be empty or not contain readable text.")

        sns_message = {
            'bucket': bucket_name,
            'object_key': object_key,
            'extracted_text': extracted_text
        }
        sns_response = sns_client.publish(
            TopicArn=sns_topic_arn,
            Message=json.dumps(sns_message),
            Subject="Textract Document Text Extraction Results"
        )
        print(f"SNS Response: {sns_response}")

        dynamodb_response = dynamodb_client.put_item(
            TableName=dynamodb_table_name,
            Item={
                'param1': {'S': object_key},
                'extracted_text': {'S': extracted_text}
            }
        )
        print(f"DynamoDB Response: {dynamodb_response}")

        return {
            'statusCode': 200,
            'body': json.dumps({'extracted_text': extracted_text})
        }

    except ValueError as ve:
        print(f"Validation Error: {str(ve)}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': str(ve)})
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
