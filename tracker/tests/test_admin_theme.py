from django.test import TestCase
from django.contrib.auth import get_user_model


class AdminThemeTests(TestCase):
    def test_admin_login_loads_the_main_app_stylesheet_and_theme(self):
        response = self.client.get("/admin/login/", HTTP_HOST="localhost")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/static/tracker/style.css")
        self.assertContains(response, "/static/tracker/admin.css")
        self.assertContains(response, "steam-tracker-admin")

    def test_admin_dashboard_loads_the_app_theme(self):
        user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password",
        )
        self.client.force_login(user)

        response = self.client.get("/admin/", HTTP_HOST="localhost")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/static/tracker/style.css")
        self.assertContains(response, "/static/tracker/admin.css")
        self.assertContains(response, "Steam Tracker Admin")
