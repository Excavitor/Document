from django.urls import path

from . import views

urlpatterns = [
    path("", views.check_page, name="lc_check"),
    path("api/check", views.api_check, name="lc_api_check"),
    path("sample", views.sample, name="lc_sample"),
]
