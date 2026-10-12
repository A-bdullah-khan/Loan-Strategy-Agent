"""Tests for the JWT auth endpoints (`/api/auth/register/`, `/api/auth/login/`,
`/api/auth/token/refresh/`)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()

REGISTER_URL = "/api/auth/register/"
LOGIN_URL = "/api/auth/login/"
REFRESH_URL = "/api/auth/token/refresh/"

STRONG_PASSWORD = "correct-horse-battery-9"


class RegisterApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.payload = {
            "full_name": "Ayesha Khan",
            "email": "Ayesha@Example.com",
            "password": STRONG_PASSWORD,
        }

    def test_register_creates_user_and_returns_tokens(self):
        response = self.client.post(REGISTER_URL, self.payload, format="json")

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="ayesha@example.com")
        self.assertEqual(user.username, "ayesha@example.com")
        self.assertTrue(user.check_password(STRONG_PASSWORD))
        self.assertEqual(
            response.data["user"],
            {"id": user.id, "email": "ayesha@example.com", "full_name": "Ayesha Khan"},
        )
        self.assertEqual(AccessToken(response.data["access"])["user_id"], str(user.id))
        self.assertIn("refresh", response.data)
        self.assertNotIn("password", response.data["user"])

    def test_register_rejects_duplicate_email_case_insensitively(self):
        self.client.post(REGISTER_URL, self.payload, format="json")

        response = self.client.post(
            REGISTER_URL, {**self.payload, "email": "AYESHA@example.com"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)
        self.assertEqual(User.objects.count(), 1)

    def test_register_rejects_weak_password(self):
        response = self.client.post(
            REGISTER_URL, {**self.payload, "password": "12345"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)
        self.assertFalse(User.objects.exists())

    def test_register_requires_every_field(self):
        response = self.client.post(
            REGISTER_URL, {"email": "a@example.com"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("full_name", response.data)
        self.assertIn("password", response.data)


class LoginApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="ayesha@example.com",
            email="ayesha@example.com",
            password=STRONG_PASSWORD,
        )

    def test_login_returns_tokens_for_valid_credentials(self):
        response = self.client.post(
            LOGIN_URL,
            {"email": "Ayesha@Example.com", "password": STRONG_PASSWORD},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            AccessToken(response.data["access"])["user_id"], str(self.user.id)
        )
        self.assertEqual(response.data["user"]["email"], "ayesha@example.com")

    def test_login_rejects_wrong_password(self):
        response = self.client.post(
            LOGIN_URL,
            {"email": "ayesha@example.com", "password": "wrong-password"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("access", response.data)

    def test_login_rejects_unknown_email_with_same_error(self):
        wrong_password = self.client.post(
            LOGIN_URL,
            {"email": "ayesha@example.com", "password": "nope-nope"},
            format="json",
        )
        unknown_email = self.client.post(
            LOGIN_URL,
            {"email": "nobody@example.com", "password": "nope-nope"},
            format="json",
        )

        self.assertEqual(unknown_email.status_code, 401)
        self.assertEqual(unknown_email.data, wrong_password.data)

    def test_login_rejects_inactive_user(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.client.post(
            LOGIN_URL,
            {"email": "ayesha@example.com", "password": STRONG_PASSWORD},
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_login_works_for_account_whose_username_is_not_its_email(self):
        User.objects.create_user(
            username="admin", email="admin@example.com", password=STRONG_PASSWORD
        )

        response = self.client.post(
            LOGIN_URL,
            {"email": "admin@example.com", "password": STRONG_PASSWORD},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

    def test_login_ignores_a_stale_authorization_header(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")

        response = self.client.post(
            LOGIN_URL,
            {"email": "ayesha@example.com", "password": STRONG_PASSWORD},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

    def test_refresh_token_issues_a_new_access_token(self):
        login = self.client.post(
            LOGIN_URL,
            {"email": "ayesha@example.com", "password": STRONG_PASSWORD},
            format="json",
        )

        response = self.client.post(
            REFRESH_URL, {"refresh": login.data["refresh"]}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            AccessToken(response.data["access"])["user_id"], str(self.user.id)
        )
