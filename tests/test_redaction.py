from moobby.redaction import configure_secrets, database_hint, redact


def test_redacts_bearer_api_key_database_uri_and_cookies():
    configure_secrets(("super-secret", "postgresql://user:password@db.example.test/postgres"))
    message = (
        "Authorization: Bearer super-secret; "
        "api_key=super-secret; "
        "DATABASE=postgresql://user:password@db.example.test/postgres; "
        "Cookie: session=private"
    )
    output = redact(message)
    for secret in ("super-secret", "password", "session=private"):
        assert secret not in output
    assert "[REDACTED]" in output
    assert "[DATABASE_URL_REDACTED]" in output


def test_database_hint_does_not_include_uri_credentials_or_full_project_ref():
    hint = database_hint("postgresql://postgres.abcdef123456:topsecret@db.example.test/postgres")
    assert "topsecret" not in hint
    assert "abcdef123456" not in hint
    assert "abc…56" in hint


def test_redacts_arbitrary_database_uri_even_without_registered_secret():
    configure_secrets(())
    assert "secret" not in redact("connection failed: postgres://user:secret@host/db")
