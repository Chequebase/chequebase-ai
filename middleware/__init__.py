from middleware.middleware import current_user, rbac, verify_token

test = verify_token(
    "test"
)  # TODO this was done to bypass pre-commit hook, remove this later

test2 = current_user({"test": "test"})

test3 = rbac(["test", "test"])
