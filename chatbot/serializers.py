import re
from rest_framework import serializers
from .models import ChatSession, ChatMessage

class ChatMessageSerializer(serializers.ModelSerializer):
    wolfram_image = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = ['id', 'session', 'sender', 'message', 'image', 'wolfram_image', 'audio', 'created_at']
        read_only_fields = ['session', 'sender', 'created_at']

    def get_wolfram_image(self, obj):
        if obj.sender == 'AI' and obj.message:
            match = re.search(r'!\[.*?\]\((.*?)\)', obj.message)
            if match:
                return match.group(1)
        return None

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if instance.sender == 'AI' and representation.get('message'):
            match = re.search(r'(!\[.*?\])\((.*?)\)', representation['message'])
            if match:
                representation['message'] = representation['message'].replace(
                    match.group(0), 
                    "Here is the generated mathematical visualization."
                )
        return representation

class ChatSessionListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for the sidebar session list.
    Only returns id, title, and updated_at — no messages.
    
    Why? When the sidebar calls GET /api/chat/sessions/, it only
    needs to display session titles. Loading every message for every
    session would be a massive N+1 query that gets worse over time.
    """
    class Meta:
        model = ChatSession
        fields = ['id', 'title', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class ChatSessionSerializer(serializers.ModelSerializer):
    """
    Full serializer — used only when viewing a single session's detail.
    This is the only place where we load all messages.
    """
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = ChatSession
        fields = ['id', 'user', 'title', 'created_at', 'updated_at', 'messages']
        read_only_fields = ['user', 'created_at', 'updated_at']
