import secrets

from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


def default_hours():
    return ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00", "17:00"]


def booking_key():
    return secrets.token_urlsafe(24)


class BookingUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields["role"] = User.Role.ADMIN
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN"
        EXPERT = "EXPERT"
        USER = "USER"

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=6, choices=Role.choices, default=Role.USER)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = BookingUserManager()
    REQUIRED_FIELDS = ["email"]


class Expert(models.Model):
    user = models.OneToOneField(User, on_delete=models.PROTECT, related_name="expert_profile")
    name = models.CharField(max_length=255)
    expertise = models.CharField(max_length=255)
    description = models.TextField(max_length=2000, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    available_hours = models.JSONField(default=default_hours)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} ({self.expertise})"


class Booking(models.Model):
    key = models.CharField(max_length=64, unique=True, default=booking_key, editable=False)
    expert = models.ForeignKey(Expert, on_delete=models.PROTECT, related_name="bookings")
    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    note = models.TextField(max_length=500, blank=True)
    booking_date = models.DateField()
    time_slot = models.CharField(max_length=5)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["booking_date", "time_slot", "id"]
        constraints = [models.UniqueConstraint(
            fields=["expert", "booking_date", "time_slot"], name="unique_expert_date_slot"
        )]

    def __str__(self):
        return f"{self.name}: {self.booking_date} {self.time_slot}"
