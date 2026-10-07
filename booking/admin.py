from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Booking, Expert, User


@admin.register(User)
class BookingUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Booking", {"fields": ("role",)}),)
    list_display = ("username", "email", "role", "is_staff")


@admin.register(Expert)
class ExpertAdmin(admin.ModelAdmin):
    list_display = ("name", "expertise", "email", "user")
    search_fields = ("name", "expertise", "email")


@admin.register(Booking)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("name", "expert", "booking_date", "time_slot")
    list_filter = ("booking_date", "expert")
    readonly_fields = ("key", "created_at")
