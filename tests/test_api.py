import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from sqlalchemy import select

from fatura_parser.api import SESSION_COOKIE_NAME, create_app
from fatura_parser.auth import create_user
from fatura_parser.database import (
    Database,
    DatabaseBase,
    UserSession,
    create_database,
)


class ApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.database_path = (
            Path(self.temporary_directory.name) / "test.db"
        )

    def test_health_endpoint_reports_that_the_api_is_available(self) -> None:
        application = create_app(database_path=self.database_path)

        with TestClient(application) as client:
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertTrue(self.database_path.exists())
        self.assertIsInstance(application.state.database, Database)

    def test_allows_the_local_vite_origin_with_credentials(self) -> None:
        application = create_app(database_path=self.database_path)

        with TestClient(application) as client:
            response = client.options(
                "/auth/login",
                headers={
                    "Origin": "http://127.0.0.1:5173",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://127.0.0.1:5173",
        )
        self.assertEqual(
            response.headers["access-control-allow-credentials"],
            "true",
        )

    def test_does_not_allow_an_unlisted_browser_origin(self) -> None:
        application = create_app(database_path=self.database_path)

        with TestClient(application) as client:
            response = client.options(
                "/auth/login",
                headers={
                    "Origin": "https://untrusted.example",
                    "Access-Control-Request-Method": "POST",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_rejects_wildcard_cors_with_credentials(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicit allowed origins"):
            create_app(
                database_path=self.database_path,
                allowed_origins=("*",),
            )


class AuthenticationApiTestCase(unittest.TestCase):
    """Verify the complete browser session flow through HTTP."""

    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.database_path = Path(self.temporary_directory.name) / "test.db"
        database = create_database(self.database_path)
        DatabaseBase.metadata.create_all(database.engine)
        with database.session_factory() as session:
            create_user(
                session,
                email="chris@example.com",
                password="uma frase senha longa",
            )
            session.commit()
        database.close()

    def test_login_me_and_logout_complete_the_session_flow(self) -> None:
        application = create_app(database_path=self.database_path)

        with TestClient(application) as client:
            login_response = client.post(
                "/auth/login",
                json={
                    "email": "CHRIS@example.com",
                    "password": "uma frase senha longa",
                },
            )
            me_response = client.get("/auth/me")
            logout_response = client.post("/auth/logout")
            after_logout_response = client.get("/auth/me")

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(
            login_response.json(),
            {"email": "chris@example.com"},
        )
        self.assertNotIn("password", login_response.text.casefold())
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json(), login_response.json())
        self.assertEqual(logout_response.status_code, 204)
        self.assertEqual(after_logout_response.status_code, 401)

    def test_login_cookie_uses_protective_browser_attributes(self) -> None:
        application = create_app(database_path=self.database_path)

        with TestClient(application) as client:
            response = client.post(
                "/auth/login",
                json={
                    "email": "chris@example.com",
                    "password": "uma frase senha longa",
                },
            )

        cookie_header = response.headers["set-cookie"]
        self.assertIn(f"{SESSION_COOKIE_NAME}=", cookie_header)
        self.assertIn("HttpOnly", cookie_header)
        self.assertIn("SameSite=strict", cookie_header)
        self.assertIn("Max-Age=43200", cookie_header)
        self.assertIn("Path=/", cookie_header)
        self.assertNotIn("Secure", cookie_header)

    def test_secure_cookie_can_be_enabled_for_https(self) -> None:
        application = create_app(
            database_path=self.database_path,
            secure_cookies=True,
        )

        with TestClient(application) as client:
            response = client.post(
                "/auth/login",
                json={
                    "email": "chris@example.com",
                    "password": "uma frase senha longa",
                },
            )

        self.assertIn("Secure", response.headers["set-cookie"])

    def test_invalid_credentials_return_the_same_generic_error(self) -> None:
        application = create_app(database_path=self.database_path)

        with TestClient(application) as client:
            wrong_password = client.post(
                "/auth/login",
                json={
                    "email": "chris@example.com",
                    "password": "outra frase senha longa",
                },
            )
            unknown_email = client.post(
                "/auth/login",
                json={
                    "email": "unknown@example.com",
                    "password": "uma frase senha longa",
                },
            )

        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(unknown_email.status_code, 401)
        self.assertEqual(wrong_password.json(), unknown_email.json())
        self.assertNotIn("set-cookie", wrong_password.headers)
        self.assertNotIn("set-cookie", unknown_email.headers)

    def test_logout_revokes_the_stored_token(self) -> None:
        application = create_app(database_path=self.database_path)

        with TestClient(application) as client:
            client.post(
                "/auth/login",
                json={
                    "email": "chris@example.com",
                    "password": "uma frase senha longa",
                },
            )
            client.post("/auth/logout")

        database = create_database(self.database_path)
        self.addCleanup(database.close)
        with database.session_factory() as session:
            stored_sessions = session.scalars(select(UserSession)).all()

        self.assertEqual(stored_sessions, [])

    def test_login_rejects_unknown_request_fields(self) -> None:
        application = create_app(database_path=self.database_path)

        with TestClient(application) as client:
            response = client.post(
                "/auth/login",
                json={
                    "email": "chris@example.com",
                    "password": "uma frase senha longa",
                    "is_admin": True,
                },
            )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
