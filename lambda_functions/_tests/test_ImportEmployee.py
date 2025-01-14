import json
from unittest.mock import MagicMock, patch

import pytest

from lambda_functions.lambdaImportEmployee import lambda_function


def test_parse_with_heuristics_valid_rows():
    rows = [
        {"firstName": "Alice", "lastName": "Smith", "email": "alice@example.com"},
        {"name": "Bob Jones", "Email": "bob@example.com"},
    ]
    structured, failed = lambda_function.parse_with_heuristics(rows)

    assert len(structured) == 2
    assert len(failed) == 0
    assert structured[0]["name"] == "Alice Smith"
    assert structured[0]["email"] == "alice@example.com"
    assert structured[1]["name"] == "Bob Jones"
    assert structured[1]["email"] == "bob@example.com"


def test_parse_with_heuristics_missing_email():
    rows = [
        {"firstName": "Charlie", "lastName": "Brown"},
        {"firstName": "Dora", "email": "dora@example.com"},
    ]
    structured, failed = lambda_function.parse_with_heuristics(rows)

    assert len(structured) == 1
    assert len(failed) == 1
    assert structured[0]["name"] == "Dora"
    assert structured[0]["email"] == "dora@example.com"
    assert failed[0]["firstName"] == "Charlie"


def test_parse_with_ai_fallback_success(mock_openai_client):
    """
    If the GPT call returns a valid JSON, ensure rows are parsed
    and none remain in 'still_failed_rows'.
    """
    # Mock GPT response
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "name": "Test User",
                            "email": "test@example.com",
                            "role": "employee",
                            "phoneNumber": "123456789",
                        }
                    )
                )
            )
        ]
    )

    failed_rows = [{"raw_field1": "value1"}]
    ai_parsed, still_failed = lambda_function.parse_with_ai_fallback(failed_rows)

    assert len(ai_parsed) == 1
    assert ai_parsed[0]["name"] == "Test User"
    assert ai_parsed[0]["email"] == "test@example.com"
    assert len(still_failed) == 0


def test_parse_with_ai_fallback_failure(mock_openai_client):
    """
    If the GPT call fails, ensure that the row ends up in still_failed_rows.
    """
    # Mock GPT to raise an exception
    mock_openai_client.chat.completions.create.side_effect = Exception("GPT error")

    failed_rows = [{"raw_field1": "value1"}]
    ai_parsed, still_failed = lambda_function.parse_with_ai_fallback(failed_rows)

    assert len(ai_parsed) == 0
    assert len(still_failed) == 1


def test_generate_data_model_from_gpt_valid(mock_openai_client):
    """
    Test generate_data_model_from_gpt with a valid GPT response.
    """
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "name": "Jane Doe",
                            "email": "jane@example.com",
                            "role": "employee",
                            "phoneNumber": "987654321",
                        }
                    )
                )
            )
        ]
    )

    prompt = "Some prompt"
    result = lambda_function.generate_data_model_from_gpt(prompt)
    assert result["name"] == "Jane Doe"
    assert result["email"] == "jane@example.com"


def test_generate_data_model_from_gpt_invalid_json(mock_openai_client):
    """
    If GPT returns non-JSON or invalid JSON, ensure we raise a ValueError.
    """
    mock_openai_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Not JSON"))]
    )

    with pytest.raises(ValueError) as exc_info:
        lambda_function.generate_data_model_from_gpt("Some prompt")
    assert "Invalid data format returned from GPT" in str(exc_info.value)


# -------------------------------------------------------------------------------------
#                           TEST validate_data_model
# -------------------------------------------------------------------------------------


def test_validate_data_model_success():
    data_model = {
        "name": "Alice Smith",
        "email": "alice@example.com",
        "phoneNumber": "123456",
    }
    assert lambda_function.validate_data_model(data_model) is True


def test_validate_data_model_missing_fields():
    data_model = {
        "name": "Bob"
        # Missing "email"
    }
    assert lambda_function.validate_data_model(data_model) is False


def test_validate_data_model_bad_email():
    data_model = {"name": "Charlie Brown", "email": "charlie@invalid@.com"}
    assert lambda_function.validate_data_model(data_model) is False


def test_validate_data_model_non_alphabetic_name():
    data_model = {"name": "Dave123", "email": "dave@example.com"}
    assert lambda_function.validate_data_model(data_model) is False


# -------------------------------------------------------------------------------------
#                           TEST lambda_handler
# -------------------------------------------------------------------------------------


@patch.object(lambda_function, "send_data_to_websocket")
def test_lambda_handler_happy_path(mock_send_ws, mock_dynamodb_item, sqs_event):
    """
    End-to-end test of lambda_handler with a valid CSV row.
    Ensures that parse_with_heuristics processes the row,
    and the results are sent to WebSocket successfully.
    """
    response = lambda_function.lambda_handler(sqs_event, {})
    assert response["statusCode"] == 200
    mock_send_ws.assert_called_once()
    # Check that we are sending a message with 'data_models' in the payload
    send_args = mock_send_ws.call_args[0]
    connection_id, data_models = send_args
    assert "invites" in data_models
    assert "failedUsers" in data_models


@patch.object(lambda_function, "send_data_to_websocket")
def test_lambda_handler_missing_csv(mock_send_ws, mock_dynamodb_item):
    """
    If 'data' is missing from the message_body, ensure we raise a ValueError
    and do not call send_data_to_websocket.
    """
    event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "connectionId": "test_connection_123",
                        # "data" is omitted intentionally
                    }
                )
            }
        ]
    }

    with pytest.raises(ValueError) as exc_info:
        lambda_function.lambda_handler(event, {})
    assert "CSV content must be provided" in str(exc_info.value)
    mock_send_ws.assert_not_called()


@patch.object(lambda_function, "parse_with_heuristics")
@patch.object(lambda_function, "parse_with_ai_fallback")
@patch.object(lambda_function, "send_data_to_websocket")
def test_lambda_handler_fallback_logic(
    mock_send_ws, mock_ai_fallback, mock_heuristics, mock_dynamodb_item, sqs_event
):
    """
    If parse_with_heuristics returns some failed rows, we call parse_with_ai_fallback.
    """
    # Mock heuristics to fail 1 row
    mock_heuristics.return_value = (
        [{"name": "Alice Smith", "email": "alice@example.com"}],  # structured
        [{"firstName": "Bob", "lastName": "Jones"}],  # failed
    )

    # Mock AI fallback to succeed with 1 row
    mock_ai_fallback.return_value = (
        [{"name": "Bob Jones", "email": "bob@example.com"}],
        [],
    )

    lambda_function.lambda_handler(sqs_event, {})

    mock_heuristics.assert_called_once()
    mock_ai_fallback.assert_called_once()
    mock_send_ws.assert_called_once()
