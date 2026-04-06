from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import ChatSession, ChatMessage
from .serializers import ChatSessionSerializer, ChatSessionListSerializer, ChatMessageSerializer
from django.conf import settings
import google.generativeai as genai
from PIL import Image
import requests
import tempfile
import os
import json
import uuid
import re
from django.utils.translation import gettext as _
from django.contrib.auth import get_user_model

User = get_user_model()

def query_wolfram_alpha(query: str) -> str:
    """Use this tool to compute exact mathematical answers, solve equations, or retrieve mathematical facts. Input should be a clearly formulated mathematical query."""
    app_id = getattr(settings, 'WOLFRAM_ALPHA_APP_ID', None)
    if not app_id:
        return "Error: WOLFRAM_ALPHA_APP_ID is not configured."
    url = "http://api.wolframalpha.com/v1/result"
    try:
        response = requests.get(url, params={"appid": app_id, "i": query}, timeout=10)
        if response.status_code == 200:
            return response.text
        else:
            return f"Wolfram Alpha error: {response.text}"
    except requests.exceptions.Timeout:
        return "Error: Wolfram Alpha query timed out."
    except Exception as e:
        return f"Error: {str(e)}"

def draw_wolfram_alpha_shape(query: str) -> str:
    """Use this tool to draw or visualize mathematical shapes, graphing functions, and plotting geometric figures."""
    app_id = getattr(settings, 'WOLFRAM_ALPHA_APP_ID', None)
    if not app_id:
        return "Error: WOLFRAM_ALPHA_APP_ID is not configured."
    url = "http://api.wolframalpha.com/v1/simple"
    try:
        response = requests.get(url, params={"appid": app_id, "i": query, "background": "transparent", "format": "png", "width": "500"}, timeout=15)
        if response.status_code == 200:
            filename = f"shape_{uuid.uuid4().hex}.png"
            media_chat_dir = os.path.join(settings.MEDIA_ROOT, 'chat_images')
            os.makedirs(media_chat_dir, exist_ok=True)
            filepath = os.path.join(media_chat_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            base_url = getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
            media_url = getattr(settings, 'MEDIA_URL', '/media/')
            return f"![Mathematical Visualization]({base_url}{media_url}chat_images/{filename})"
        elif response.status_code == 501: # Wolfram error
            return f"Wolfram Alpha could not generate a visual geometric shape for this query: {query}"
        else:
            return f"Wolfram Alpha error: {response.text}"
    except requests.exceptions.Timeout:
        return "Error: Wolfram Alpha visual query timed out."
    except Exception as e:
        return f"Error: {str(e)}"

# Configure Gemini
genai.configure(api_key=settings.GEMINI_API_KEY)


def build_system_instruction(language=None):
    """
    Builds the Gemini system instruction with the correct language.
    Shared by both SendMessageView and GuestChatView.
    """
    lang_instruction = (
        f"You MUST respond entirely in {language}." 
        if language else 
        "You MUST auto-detect if the user's prompt is in English or Bulgarian. If it is English, respond entirely in English. If it is Bulgarian, respond entirely in Bulgarian. If the user speaks any other language, detect the language and respond in the same language."
    )
    return (
        "You are an expert Math Tutor. Your objective is to help students understand mathematical concepts through detailed, step-by-step derivations.\n\n"
        f"{lang_instruction}\n\n"
        "CORE OPERATIONAL RULES:\n"
        "1. SMART TOOL USAGE: Use the `query_wolfram_alpha` tool ONLY for numeric calculations and text-based math equations. Use the `draw_wolfram_alpha_shape` tool ONLY to draw or visualize mathematical shapes, graphing functions, or plotting geometric entities (e.g. circle, sine wave). IMPORTANT: When `draw_wolfram_alpha_shape` returns an image Markdown link (e.g., `![...](...)`), YOU MUST INCLUDE THAT EXACT LINK directly in your final response! Do not omit it. NEVER mention tool usage explicitly to the user.\n"
        "2. VISUAL OBSERVATION: If the user provides an image and asks you to 'count' triangles or squares or any geometrical shapes edges or identify what is in the image, DO NOT use Wolfram Alpha. Use your own built-in vision capabilities to analyze and answer directly.\n"
        "3. FORMATTING: Every response MUST be structured as a sequence of logical steps.\n"
        "4. STEP STRUCTURE: \n"
        "   - Step: [Observation/Setup]\n"
        "   - Step: [Calculation/Logical Link]\n"
        "   - ...\n"
        "   - Final Answer: [boxed result]\n"
        "5. Even for simple questions like '2+2', you must provide a step-by-step breakdown (e.g., 'Step: Identify the numbers... Step: Sum the values...').\n"
        "6. Always encapsulate your ultimate mathematical conclusion as a Final Answer at the end of the response.\n"
        "7. Use LaTeX for all mathematical expressions and symbols.\n"
        "8. Never mention tools like Wolfram Alpha to the user. Present the solution as your own knowledge."
    )


from rest_framework.pagination import PageNumberPagination


class ChatSessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sessions = ChatSession.objects.filter(user=request.user).order_by('-updated_at')

        # Manual pagination because APIView doesn't auto-paginate
        # like generic views do. We handle it ourselves.
        paginator = PageNumberPagination()
        paginator.page_size = 20
        paginated_sessions = paginator.paginate_queryset(sessions, request)
        serializer = ChatSessionListSerializer(paginated_sessions, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        session = ChatSession.objects.create(user=request.user)
        return Response(ChatSessionSerializer(session).data, status=status.HTTP_201_CREATED)

class ChatSessionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        try:
            session = ChatSession.objects.get(id=session_id, user=request.user)
            serializer = ChatSessionSerializer(session)
            return Response(serializer.data)
        except ChatSession.DoesNotExist:
            return Response({'error': _('Session not found')}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, session_id):
        try:
            session = ChatSession.objects.get(id=session_id, user=request.user)
            session.delete()
            return Response({'message': 'Session deleted'}, status=status.HTTP_204_NO_CONTENT)
        except ChatSession.DoesNotExist:
            return Response({'error': _('Session not found')}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, session_id):
        """
        Rename a chat session.
        The only field a user should update is 'title' — we don't
        allow changing the user, messages, or timestamps via this endpoint.
        """
        try:
            session = ChatSession.objects.get(id=session_id, user=request.user)
        except ChatSession.DoesNotExist:
            return Response({'error': _('Session not found')}, status=status.HTTP_404_NOT_FOUND)

        new_title = request.data.get('title')
        if not new_title or not new_title.strip():
            return Response(
                {'error': _('Title is required and cannot be empty.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        session.title = new_title.strip()
        session.save()
        return Response(ChatSessionSerializer(session).data, status=status.HTTP_200_OK)

class SendMessageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        try:
            session = ChatSession.objects.get(id=session_id, user=request.user)
        except ChatSession.DoesNotExist:
            return Response({'error': _('Session not found')}, status=status.HTTP_404_NOT_FOUND)

        user_message_text = request.data.get('message', '')
        image_file = request.FILES.get('image')
        audio_file = request.FILES.get('audio')

        if not user_message_text and not image_file and not audio_file:
            return Response({'error': _('Message, image, or audio is required')}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Save User Message
        user_message_obj = ChatMessage.objects.create(
            session=session,
            sender='USER',
            message=user_message_text,
            image=image_file,
            audio=audio_file
        )

        try:
            # 2. Prepare Gemini Model — use language from request payload (None allows auto-detect)
            user_language = request.data.get('language')
            system_instruction = build_system_instruction(user_language)
            model = genai.GenerativeModel('gemini-2.5-flash', system_instruction=system_instruction, tools=[query_wolfram_alpha, draw_wolfram_alpha_shape])

            # 3. Build History for Context
            history = []
            previous_messages = ChatMessage.objects.filter(session=session).order_by('created_at')[:20] # Limit context window
            for msg in previous_messages:
                role = 'user' if msg.sender == 'USER' else 'model'
                parts = []
                
                if msg.message:
                     parts.append(msg.message)
                     
                # Append image if present to allow Gemini to remember visual context
                if msg.image:
                     try:
                         parts.append(Image.open(msg.image.path))
                     except Exception:
                         pass
                         
                if parts:
                     history.append({'role': role, 'parts': parts})

            chat = model.start_chat(history=history, enable_automatic_function_calling=True)

            # 4. Generate Response
            response = None
            inputs = []
            
            if user_message_text:
                inputs.append(user_message_text)
            
            if image_file:
                # Handle Image input
                if user_message_obj.image:
                   img = Image.open(user_message_obj.image.path)
                   inputs.append(img)
            
            remote_file = None  # Track for cleanup

            if audio_file:
                # Handle Audio input
                if user_message_obj.audio:
                    mime_type = audio_file.content_type if audio_file.content_type != 'application/octet-stream' else None
                    if not mime_type:
                        ext = os.path.splitext(audio_file.name)[1].lower() if audio_file.name else '.mp3'
                        mime_type = 'audio/mp4' if ext == '.m4a' else 'audio/mpeg'
                    
                    remote_file = genai.upload_file(user_message_obj.audio.path, mime_type=mime_type)
                    inputs.append(remote_file)

            if inputs:
                try:
                    response = chat.send_message(inputs)
                    ai_response_text = response.text
                finally:
                    # Clean up: delete the audio file from Gemini's servers.
                    # Gemini File API has a 20GB quota — without this cleanup,
                    # every audio message permanently consumes storage until
                    # the quota fills up and the app breaks.
                    if remote_file:
                        try:
                            genai.delete_file(remote_file.name)
                        except Exception:
                            pass  # Don't crash the response if cleanup fails
            else:
                 return Response({'error': 'No valid input for AI'}, status=status.HTTP_400_BAD_REQUEST)


            # 5. Save AI Response
            ai_message_obj = ChatMessage.objects.create(
                session=session,
                sender='AI',
                message=ai_response_text
            )
            
            # Update session title if it's the first message
            if not session.title:
                session.title = user_message_text[:30] if user_message_text else "Image Chat"
                session.save()

            # Return the User message (with image URL if any) and AI message
            return Response({
                'user_message': ChatMessageSerializer(user_message_obj).data,
                'ai_response': ChatMessageSerializer(ai_message_obj).data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class GuestChatView(APIView):
    """
    Allows unauthenticated users to try the AI chatbot.
    Messages are NOT saved — stateless, single-turn interaction.
    """
    permission_classes = []

    def post(self, request):
        user_message_text = request.data.get('message', '')
        image_file = request.FILES.get('image')
        audio_file = request.FILES.get('audio')
        language = request.data.get('language')
        history_data = request.data.get('history', '[]')

        if not user_message_text and not image_file and not audio_file:
            return Response(
                {'error': _('Message, image, or audio is required.')},
                status=status.HTTP_400_BAD_REQUEST
            )

        remote_file = None
        temp_audio_path = None

        try:
            system_instruction = build_system_instruction(language)
            model = genai.GenerativeModel(
                'gemini-1.5-flash',
                system_instruction=system_instruction,
                tools=[query_wolfram_alpha, draw_wolfram_alpha_shape]
            )

            # Build stateless history from frontend JSON array
            history = []
            try:
                parsed_history = json.loads(history_data)
                for item in parsed_history:
                    # Expecting structure like: {"role": "user", "parts": ["text"]}
                    if isinstance(item, dict) and 'role' in item and 'parts' in item:
                        history.append(item)
            except json.JSONDecodeError:
                pass # If the frontend sends junk history, ignore it and start fresh

            chat = model.start_chat(history=history, enable_automatic_function_calling=True)

            inputs = []
            if user_message_text:
                inputs.append(user_message_text)
            if image_file:
                img = Image.open(image_file)
                inputs.append(img)
            
            if audio_file:
                # Save the audio chunk to a temporary file locally so we can upload it to Gemini
                ext = os.path.splitext(audio_file.name)[1].lower() if audio_file.name else '.mp3'
                mime_type = audio_file.content_type if audio_file.content_type != 'application/octet-stream' else None
                if not mime_type:
                    mime_type = 'audio/mp4' if ext == '.m4a' else 'audio/mpeg'
                    
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_audio:
                    for chunk in audio_file.chunks():
                        temp_audio.write(chunk)
                    temp_audio_path = temp_audio.name
                
                remote_file = genai.upload_file(temp_audio_path, mime_type=mime_type)
                inputs.append(remote_file)

            if inputs:
                response = chat.send_message(inputs)
                ai_response_text = response.text
                
                wolfram_img_url = None
                match = re.search(r'(!\[.*?\])\((.*?)\)', ai_response_text)
                if match:
                    wolfram_img_url = match.group(2)
                    ai_response_text = ai_response_text.replace(
                        match.group(0), 
                        "Here is the generated mathematical visualization."
                    )

                return Response({
                    'message': user_message_text,
                    'ai_response': ai_response_text,
                    'wolfram_image': wolfram_img_url,
                    'is_guest': True
                }, status=status.HTTP_200_OK)
            else:
                return Response(
                    {'error': 'No valid input for AI.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        finally:
            # Clean up the cloud file to prevent quota leaks
            if remote_file:
                try:
                    genai.delete_file(remote_file.name)
                except Exception:
                    pass
            # Clean up the temporary local file to prevent disk bloat
            if temp_audio_path and os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                except Exception:
                    pass
