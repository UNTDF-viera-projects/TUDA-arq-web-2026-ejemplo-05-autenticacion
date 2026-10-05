from django.urls import path
from activities import api_views as v
urlpatterns = [
    path("api/v1/activities", v.activities),
    path("api/v1/activities/<str:activity_id>", v.activity_detail),
    path("api/v1/auth/register", v.register),
    path("api/v1/me", v.me),
    path("api/v1/me/enrollments", v.enrollments),
    path("api/v1/me/enrollments/<str:activity_id>", v.enrollment_detail),
    path("api/v1/enrollments/<str:enrollment_id>", v.enrollment_by_id),
    path("api/v1/auth/login", v.login_api),
    path("api/v1/auth/logout", v.logout_api),
    path("api/v1/auth/csrf", v.csrf_api),
]
