import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from fatura_parser.api import create_app
from fatura_parser.database import Database


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


if __name__ == "__main__":
    unittest.main()
