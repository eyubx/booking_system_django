from datetime import datetime

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Booking, Expert, User
from .permissions import AdminOnly, ExpertAccess, is_admin
from .serializers import (
    AvailabilityQuerySerializer, BookingSerializer, ExpertSearchSerializer,
    ExpertSerializer, LoginSerializer, RegisterSerializer, UserSerializer,
)


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer


class UserViewSet(viewsets.GenericViewSet):
    queryset = User.objects.order_by("id")
    serializer_class = UserSerializer
    permission_classes = [AdminOnly]

    def list(self, request):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @extend_schema(request=RegisterSerializer, responses={201: UserSerializer})
    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def register(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def me(self, request):
        return Response(UserSerializer(request.user).data)

    @extend_schema(request=RegisterSerializer(many=True), responses={201: UserSerializer(many=True)})
    @action(detail=False, methods=["post"], url_path="users/bulk")
    def bulk(self, request):
        serializer = RegisterSerializer(data=request.data, many=True, allow_empty=False)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                users = serializer.save()
        except IntegrityError:
            return Response({"detail": "Duplicate username or email in batch."}, status=400)
        return Response(UserSerializer(users, many=True).data, status=201)


class ExpertViewSet(viewsets.ModelViewSet):
    queryset = Expert.objects.select_related("user").all()
    serializer_class = ExpertSerializer
    permission_classes = [ExpertAccess]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    @extend_schema(responses=ExpertSearchSerializer(many=True))
    @action(detail=False, methods=["get"])
    def search(self, request):
        queryset = self.get_queryset().filter(
            name__icontains=request.query_params.get("name", "").strip(),
            expertise__icontains=request.query_params.get("expertise", "").strip(),
        )
        return Response(ExpertSearchSerializer(queryset, many=True).data)

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response({"detail": "Expert has bookings and cannot be deleted."}, status=409)

    @extend_schema(parameters=[AvailabilityQuerySerializer])
    @action(detail=True, methods=["get"])
    def availability(self, request, pk=None):
        expert = self.get_object()
        query = AvailabilityQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        date = query.validated_data["date"]
        occupied = set(expert.bookings.filter(booking_date=date).values_list("time_slot", flat=True))
        slots = []
        for slot in expert.available_hours:
            moment = timezone.make_aware(datetime.combine(date, datetime.strptime(slot, "%H:%M").time()))
            slots.append({"time": slot, "available": slot not in occupied and moment > timezone.now()})
        return Response({"expertId": expert.pk, "date": date.isoformat(), "slots": slots})


class BookingViewSet(viewsets.GenericViewSet):
    queryset = Booking.objects.select_related("expert").all()
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in {"create", "by_key"}:
            return [AllowAny()]
        return super().get_permissions()

    def list(self, request):
        queryset = self.get_queryset()
        if not is_admin(request.user):
            queryset = queryset.filter(expert__user=request.user)
        return Response(self.get_serializer(queryset, many=True).data)

    @extend_schema(request=BookingSerializer, responses={201: BookingSerializer})
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            return Response({"detail": "This time slot is already booked."}, status=409)
        return Response(serializer.data, status=201)

    @action(detail=False, methods=["get"], url_path=r"expert/(?P<expert_id>\d+)")
    def by_expert(self, request, expert_id=None):
        expert = get_object_or_404(Expert, pk=expert_id)
        if not is_admin(request.user) and expert.user_id != request.user.id:
            raise PermissionDenied("You can only view your own expert bookings.")
        return Response(self.get_serializer(self.get_queryset().filter(expert=expert), many=True).data)

    @action(detail=False, methods=["get"], url_path=r"key/(?P<key>[^/.]+)", permission_classes=[AllowAny])
    def by_key(self, request, key=None):
        booking = get_object_or_404(self.get_queryset(), key=key)
        return Response(self.get_serializer(booking).data)

    def destroy(self, request, pk=None):
        booking = self.get_object()
        if not is_admin(request.user) and booking.expert.user_id != request.user.id:
            raise PermissionDenied("You can only cancel your own expert bookings.")
        booking.delete()
        return Response(status=204)
