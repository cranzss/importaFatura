import unittest

from fastapi.testclient import TestClient

from fatura_parser.api import create_app


class ApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_health_endpoint_reports_that_the_api_is_available(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
