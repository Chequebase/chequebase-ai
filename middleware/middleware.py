import logging
import os
from functools import wraps
from typing import Any, Dict, List

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError
from pymongo import MongoClient

# Initialize logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Set secret key from environment variable
SECRET_KEY = os.getenv("ACCESS_TOKEN_SECRET")

# Initialize MongoDB client
mongo_client: MongoClient = MongoClient(os.getenv("MONGODB_URI"))
db = mongo_client["chequebase-staging"]
users_collection = db["users"]
devices_collection = db["devices"]
sessions_collection = db["sessions"]


def verify_token(token: str) -> Dict[str, Any]:
    """
    Verifies JWT token and returns decoded token data.

    :param token: The JWT token to verify.
    :return: Decoded token data if valid.
    :raises: Unauthorized error if the token is invalid or expired.
    """
    try:
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return decoded_token
    except ExpiredSignatureError:
        logger.error("Token expired")
        raise Exception("Unauthorized: Token expired")
    except JWTError:
        logger.error("Invalid token")
        raise Exception("Unauthorized: Invalid token")


def current_user(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Middleware to attach user information to request if token is valid.

    :param event: The event data passed to the function (contains headers).
    :return: User data if the token is valid.
    :raises: Unauthorized error if no valid authorization header or user not found.
    """
    auth_header = event.get("headers", {}).get("Authorization")
    if not auth_header:
        raise Exception("Unauthorized: Authorization header missing")

    token = auth_header.split("Bearer ")[-1]
    decoded_token = verify_token(token)
    user = users_collection.find_one({"_id": decoded_token["sub"]})

    if not user:
        raise Exception("Unauthorized: User not found")

    return user


def rbac(actions: List[str] = []):
    """
    Middleware to handle Role-Based Access Control (RBAC).

    :param actions: List of actions required to access the resource.
    :return: Decorator function to enforce RBAC.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(event, context, *args, **kwargs):
            user = current_user(event)

            if user["status"] in ["DELETED", "DISABLED"]:
                raise Exception("Unauthorized: User account is not active")

            if user["organization"]["status"] == "BLOCKED":
                raise Exception("Unauthorized: User's organization is blocked")

            client_id = event.get("headers", {}).get("client-id")
            api_key = event.get("headers", {}).get("source-app")

            if api_key != "banksphere":
                if not client_id:
                    raise Exception("Unauthorized: No ClientId provided")

                current_device = devices_collection.find_one({"clientId": client_id})
                if not current_device:
                    raise Exception("Not Found: Device not found")

                current_sessions = list(
                    sessions_collection.find(
                        {
                            "user": user["_id"],
                            "device": {"$ne": current_device["_id"]},
                            "revokedAt": {"$exists": False},
                        }
                    )
                )

                if current_sessions:
                    users_collection.update_one(
                        {"_id": user["_id"]}, {"$set": {"rememberMe": False}}
                    )
                    raise Exception("Forbidden: Currently logged in to another device")

            is_owner = (
                user["roleRef"]["name"] == "owner"
                and user["roleRef"]["type"] == "default"
            )
            user_actions = [
                perm["actions"] for perm in user["roleRef"].get("permissions", [])
            ]

            if (
                is_owner
                or not actions
                or any(action in user_actions for action in actions)
            ):
                return func(event, context, *args, **kwargs)
            else:
                raise Exception("Forbidden: Access Denied")

        return wrapper

    return decorator
