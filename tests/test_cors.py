import unittest
from fastapi.testclient import TestClient
from app.main import app

class CorsTests(unittest.TestCase):
    def test_android_preflight(self) -> None:
        res = TestClient(app).options('/api/v1/stores', headers={
            'Origin': 'https://localhost', 'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'authorization,content-type'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('access-control-allow-origin'), 'https://localhost')

    def test_other_origin_not_allowed(self) -> None:
        res = TestClient(app).options('/api/v1/stores', headers={
            'Origin': 'https://untrusted.example', 'Access-Control-Request-Method': 'POST'})
        self.assertEqual(res.status_code, 400)
        self.assertNotIn('access-control-allow-origin', res.headers)
