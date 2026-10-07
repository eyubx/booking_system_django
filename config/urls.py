from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenRefreshView

from booking.views import BookingViewSet, ExpertViewSet, LoginView, UserViewSet

router = SimpleRouter(trailing_slash=False)
router.trailing_slash = "/?"
router.register("users", UserViewSet)
router.register("experts", ExpertViewSet)
router.register("bookings", BookingViewSet)

urlpatterns = [
    path("admin/", admin.site.urls),
    re_path(r"^api/users/login/?$", LoginView.as_view(), name="login"),
    re_path(r"^api/token/refresh/?$", TokenRefreshView.as_view(), name="token-refresh"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/", include(router.urls)),
]
