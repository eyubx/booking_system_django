from rest_framework.permissions import BasePermission, SAFE_METHODS


def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.role == "ADMIN")


class AdminOnly(BasePermission):
    def has_permission(self, request, view):
        return is_admin(request.user)


class ExpertAccess(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        if view.action == "create":
            return is_admin(request.user)
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return request.method in SAFE_METHODS or is_admin(request.user) or obj.user_id == request.user.id
