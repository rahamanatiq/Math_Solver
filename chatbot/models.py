from django.db import models
from django.conf import settings

class ChatSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_sessions')
    title = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Chat {self.id} - {self.user.email}"

class ChatMessage(models.Model):
    SENDER_CHOICES = (
        ('USER', 'User'),
        ('AI', 'AI'),
    )

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=10, choices=SENDER_CHOICES)
    message = models.TextField(blank=True, default='')
    image = models.ImageField(upload_to='chat_images/', blank=True, null=True)
    audio = models.FileField(upload_to='chat_audio/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender}: {self.message[:50]}"

class Document(models.Model):
    filename = models.CharField(max_length=255, unique=True, help_text="Name of the file in the documents directory")
    ingested_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.filename

class DocumentChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='chunks')
    chunk_index = models.IntegerField()
    text = models.TextField()

    def __str__(self):
        return f"{self.document.filename} - Chunk {self.chunk_index}"
