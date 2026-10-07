from datetime import datetime

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Booking, Expert, User


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]


class UserSerializer(serializers.ModelSerializer):
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "role", "createdAt", "updatedAt"]
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = ["username", "email", "password"]
        extra_kwargs = {"email": {"required": True, "allow_blank": False}}

    def validate(self, attrs):
        try:
            validate_password(attrs["password"], User(username=attrs["username"], email=attrs["email"]))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data["token"] = data["access"]
        data["user"] = UserSerializer(self.user).data
        return data


class ExpertSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(read_only=True)
    userId = serializers.PrimaryKeyRelatedField(
        source="user", queryset=User.objects.all(), write_only=True,
        validators=[UniqueValidator(queryset=Expert.objects.all(), message="User already has an expert profile.")],
    )
    availableHours = serializers.ListField(
        source="available_hours", child=serializers.RegexField(r"^(?:[01]\d|2[0-3]):[0-5]\d$"), required=False
    )
    email = serializers.EmailField(required=False, allow_blank=True)

    class Meta:
        model = Expert
        fields = ["id", "name", "expertise", "description", "email", "phone", "user", "userId", "availableHours"]

    def validate_availableHours(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Available hours must be unique.")
        return sorted(value)

    def validate(self, attrs):
        request = self.context["request"]
        if self.instance and "user" in attrs:
            from .permissions import is_admin
            if not is_admin(request.user) and attrs["user"].pk != self.instance.user_id:
                raise serializers.ValidationError({"userId": "Only an admin can reassign an expert."})
        user = attrs.get("user") or (self.instance.user if self.instance else None)
        if not attrs.get("email") and ("email" in attrs or not self.instance):
            attrs["email"] = user.email
        return attrs


class ExpertSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expert
        fields = ["id", "name", "expertise", "description", "email", "phone"]


class ExpertSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Expert
        fields = ["id", "name", "expertise"]


class BookingSerializer(serializers.ModelSerializer):
    expert = ExpertSummarySerializer(read_only=True)
    expertId = serializers.PrimaryKeyRelatedField(source="expert", queryset=Expert.objects.all(), write_only=True)
    bookingDate = serializers.DateField(source="booking_date")
    timeSlot = serializers.RegexField(r"^(?:[01]\d|2[0-3]):[0-5]\d$", source="time_slot")

    class Meta:
        model = Booking
        fields = ["id", "key", "expert", "expertId", "name", "email", "phone", "note", "bookingDate", "timeSlot"]
        read_only_fields = ["id", "key"]
        validators = []  # The database constraint and view handle concurrent slot conflicts.

    def validate(self, attrs):
        if attrs["time_slot"] not in attrs["expert"].available_hours:
            raise serializers.ValidationError({"timeSlot": "This expert does not offer that time slot."})
        moment = datetime.combine(attrs["booking_date"], datetime.strptime(attrs["time_slot"], "%H:%M").time())
        if timezone.make_aware(moment) <= timezone.now():
            raise serializers.ValidationError({"bookingDate": "Choose a future appointment."})
        return attrs


class AvailabilityQuerySerializer(serializers.Serializer):
    date = serializers.DateField()
