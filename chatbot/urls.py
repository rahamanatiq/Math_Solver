from django.urls import path
from .views import ChatSessionListView, ChatSessionDetailView, SendMessageView, GuestChatView

urlpatterns = [
    path('sessions/', ChatSessionListView.as_view(), name='chat-sessions'),
    path('sessions/<int:session_id>/', ChatSessionDetailView.as_view(), name='chat-detail'),
    path('sessions/<int:session_id>/send/', SendMessageView.as_view(), name='chat-send'),
    path('guest/', GuestChatView.as_view(), name='guest-chat'),
]
