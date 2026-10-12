from django.urls import path

from .api import ChatAPIView, ChatHistoryAPIView, ChatSessionAPIView

urlpatterns = [
    path(
        "chat/history/<str:session_id>/",
        ChatSessionAPIView.as_view(),
        name="chat-session-detail",
    ),
    path("chat/history/", ChatHistoryAPIView.as_view(), name="chat-history"),
    path("chat/", ChatAPIView.as_view(), name="chat"),
]
