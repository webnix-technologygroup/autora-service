from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings


@override_settings(DEBUG=True, ALLOWED_HOSTS=["localhost", "testserver"])
class AdminCsrfRegressionTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_superuser(
            username="csrf-admin",
            email="admin@example.test",
            password="Strong-test-password-2026",
        )

    def test_local_null_origin_login_succeeds_with_valid_token(self):
        client = Client(enforce_csrf_checks=True)
        client.get("/admin/login/", HTTP_HOST="localhost:8000")
        token = client.cookies["csrftoken"].value
        response = client.post(
            "/admin/login/?next=/admin/",
            {
                "username": "csrf-admin",
                "password": "Strong-test-password-2026",
                "csrfmiddlewaretoken": token,
            },
            HTTP_HOST="localhost:8000",
            HTTP_ORIGIN="null",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/admin/")

    def test_local_null_origin_without_token_is_rejected(self):
        response = Client(enforce_csrf_checks=True).post(
            "/admin/login/",
            {"username": "csrf-admin", "password": "Strong-test-password-2026"},
            HTTP_HOST="localhost:8000",
            HTTP_ORIGIN="null",
        )
        self.assertEqual(response.status_code, 403)
