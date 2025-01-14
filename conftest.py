import json
from unittest.mock import MagicMock, patch

import pytest

from lambda_functions.lambdaImportEmployee import lambda_function


@pytest.fixture
def mock_openai_client():
    """Fixture to mock the OpenAI client."""
    with patch.object(lambda_function, "openai_client") as mock_client:
        yield mock_client


@pytest.fixture
def mock_dynamodb():
    """Fixture to mock the DynamoDB resource and table."""
    with patch.object(lambda_function, "table") as mock_table:
        mock_table.get_item.return_value = {
            "Item": {"connectionId": "test_connection_123", "status": "connected"}
        }
        yield mock_table


@pytest.fixture
def mock_apigw_management():
    """Fixture to mock the API Gateway Management API client."""
    with patch("lambda_function.boto3.client") as mock_boto_client:
        mock_api_client = MagicMock()
        mock_boto_client.return_value = mock_api_client
        yield mock_api_client


@pytest.fixture
def sqs_event():
    """A basic SQS event with a CSV payload and a single record."""
    return {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "connectionId": "test_connection_123",
                        "data": "firstName,lastName,email\nAlice,Smith,alice@example.com\nBob,,bob@example\n",
                    }
                )
            }
        ]
    }


@pytest.fixture
def mock_dynamodb_item(mock_dynamodb):
    """
    Pre-configure the mock DynamoDB table's get_item response
    to return a 'connected' connection status.
    """
    mock_dynamodb.get_item.return_value = {
        "Item": {"connectionId": "test_connection_123", "status": "connected"}
    }
