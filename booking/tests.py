from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Booking, Expert, User


class BookingAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("admin", "admin@example.com", "Strong-Test-Pass-123!")
        cls.owner = User.objects.create_user("expert", "expert@example.com", "Strong-Test-Pass-123!")
        cls.other = User.objects.create_user("other", "other@example.com", "Strong-Test-Pass-123!")
        cls.expert = Expert.objects.create(
            user=cls.owner, name="Dr Example", expertise="Medicine", email=cls.owner.email
        )

    def appointment(self, **overrides):
        return {
            "expertId": self.expert.pk, "name": "Visitor", "email": "visitor@example.com",
            "bookingDate": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "timeSlot": "10:00", **overrides,
        }

    def test_login_and_authenticated_me(self):
        response = self.client.post("/api/users/login", {"username": "expert", "password": "Strong-Test-Pass-123!"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["token"], response.data["access"])
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {response.data["access"]}')
        me = self.client.get("/api/users/me/")
        self.assertEqual(me.data["id"], self.owner.pk)
        self.assertNotIn("password", me.data)
        refresh = self.client.post("/api/token/refresh", {"refresh": response.data["refresh"]})
        self.assertEqual(refresh.status_code, 200)

    def test_invalid_login(self):
        response = self.client.post("/api/users/login", {"username": "expert", "password": "wrong"})
        self.assertEqual(response.status_code, 401)

    def test_register_hashes_password_and_cannot_escalate_role(self):
        response = self.client.post("/api/users/register", {
            "username": "newperson", "email": "new@example.com",
            "password": "Another-Strong-Pass-456!", "role": "ADMIN",
        })
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="newperson")
        self.assertEqual(user.role, "USER")
        self.assertTrue(user.check_password("Another-Strong-Pass-456!"))
        self.assertNotIn("password", response.data)

    def test_search_and_optional_slashes(self):
        for url in ["/api/experts", "/api/experts/"]:
            self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.get("/api/experts/search", {"name": "example", "expertise": "MED"})
        self.assertEqual(len(response.data), 1)
        self.assertNotIn("user", response.data[0])

    def test_admin_creates_expert_and_duplicate_profile_is_rejected(self):
        self.client.force_authenticate(self.admin)
        payload = {"userId": self.other.pk, "name": "New Expert", "expertise": "Law", "email": ""}
        response = self.client.post("/api/experts/", payload)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["email"], self.other.email)
        self.assertEqual(response.data["availableHours"][0], "09:00")
        self.assertEqual(self.client.post("/api/experts", payload).status_code, 400)

    def test_expert_permissions_and_partial_updates(self):
        url = f"/api/experts/{self.expert.pk}"
        self.assertEqual(self.client.patch(url, {"name": "Changed"}).status_code, 401)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.patch(url, {"name": "Changed"}).status_code, 403)
        self.client.force_authenticate(self.owner)
        response = self.client.patch(url, {"expertise": "Surgery"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Dr Example")
        self.assertEqual(response.data["expertise"], "Surgery")
        self.assertEqual(self.client.patch(url, {"userId": self.other.pk}).status_code, 400)
        self.assertEqual(self.client.patch(url, {"availableHours": ["25:00"]}, format="json").status_code, 400)

    def test_public_booking_lookup_availability_and_conflict(self):
        payload = self.appointment()
        response = self.client.post("/api/bookings", payload)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.client.post("/api/bookings/", payload).status_code, 409)
        lookup = self.client.get(f'/api/bookings/key/{response.data["key"]}')
        self.assertEqual(lookup.status_code, 200)
        availability = self.client.get(f"/api/experts/{self.expert.pk}/availability", {"date": payload["bookingDate"]})
        self.assertEqual(availability.status_code, 200)
        slots = {slot["time"]: slot["available"] for slot in availability.data["slots"]}
        self.assertFalse(slots["10:00"])
        self.assertTrue(slots["11:00"])

    def test_booking_validation(self):
        for changes in [
            {"timeSlot": "12:00"}, {"timeSlot": "bad"}, {"email": "invalid"},
            {"bookingDate": (timezone.localdate() - timedelta(days=1)).isoformat()},
            {"expertId": 99999},
        ]:
            response = self.client.post("/api/bookings", self.appointment(**changes))
            self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.client.get(f"/api/experts/{self.expert.pk}/availability").status_code, 400)

    def test_database_enforces_slot_uniqueness(self):
        attrs = {"expert": self.expert, "booking_date": timezone.localdate(), "time_slot": "10:00", "name": "A", "email": "a@example.com"}
        Booking.objects.create(**attrs)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Booking.objects.create(**attrs)

    def test_booking_access_and_cancellation(self):
        booking = self.client.post("/api/bookings", self.appointment()).data
        url = f"/api/bookings/expert/{self.expert.pk}"
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get("/api/bookings").data, [])
        self.assertEqual(self.client.delete(f'/api/bookings/{booking["id"]}').status_code, 403)
        self.client.force_authenticate(self.owner)
        self.assertEqual(len(self.client.get(url).data), 1)
        self.assertEqual(self.client.delete(f"/api/experts/{self.expert.pk}").status_code, 409)
        self.assertEqual(self.client.delete(f'/api/bookings/{booking["id"]}').status_code, 204)
        self.assertEqual(self.client.post("/api/bookings", self.appointment()).status_code, 201)

    def test_bulk_is_admin_only_and_atomic(self):
        payload = [{"username": "batch", "email": "batch@example.com", "password": "Batch-Password-456!"}] * 2
        self.assertEqual(self.client.post("/api/users/users/bulk", payload, format="json").status_code, 401)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post("/api/users/users/bulk", payload, format="json").status_code, 400)
        self.assertFalse(User.objects.filter(username="batch").exists())
        self.assertEqual(self.client.post("/api/users/users/bulk", payload[:1], format="json").status_code, 201)

    def test_user_list_is_admin_only_and_has_no_passwords(self):
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get("/api/users/").status_code, 403)
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/users/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("password", response.data[0])
