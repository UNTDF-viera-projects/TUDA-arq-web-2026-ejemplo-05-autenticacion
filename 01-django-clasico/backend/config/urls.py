from django.urls import path
from activities import views
urlpatterns = [
    path("", views.index, name="index"),
    path("activities/", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("me/", views.me, name="me"),
    path("activities/<uuid:activity_id>/enroll/", views.enroll, name="enroll"),
    path("activities/<uuid:activity_id>/unenroll/", views.unenroll, name="unenroll"),
]
