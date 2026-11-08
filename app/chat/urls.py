from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/chat/stream", views.api_chat_stream, name="api_chat_stream"),
]