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


def detect_language_from_text(text: str) -> str:
    """
    Auto-detect language from the user's message text.
    If the text contains Cyrillic characters, assume Bulgarian.
    Otherwise, default to English.
    """
    if text and re.search(r'[\u0400-\u04FF]', text):
        return 'Bulgarian'
    return 'English'


def query_wolfram_alpha(query: str) -> str:
    """Use this tool ONLY for pure arithmetic like '12150 / 6' or 'sqrt(2025)'. Never pass word problems or sentences."""
    # Only allow pure math expressions: digits, operators, parentheses, dots, commas, spaces, and math keywords
    if not re.match(r'^[\d\s\+\-\*/\^\(\)\.\,\=xyzabc]+$', query.strip()) and not re.match(r'^(sqrt|log|sin|cos|tan|abs|solve|simplify|factor|expand)\s*\(', query.strip(), re.IGNORECASE):
        return "ERROR: Only pure math expressions are allowed (e.g. '12150 / 6', 'sqrt(2025)'). You must solve the word problem yourself step by step and only call this tool for specific calculations."

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

    # Use the Full Results API (v2) with JSON output to get structured pods.
    # This lets us extract ONLY the plot/drawing image instead of a full-page screenshot.
    url = "http://api.wolframalpha.com/v2/query"
    # Pod titles that contain actual visualizations/drawings
    VISUAL_POD_KEYWORDS = [
        'plot', 'graph', 'illustration', 'visual', 'image',
        'contour', '3d', 'diagram', 'chart', 'result',
        'definition',   # geometric shapes often show their drawing here
    ]

    try:
        response = requests.get(url, params={
            "appid": app_id,
            "input": query,
            "output": "json",
            "format": "image",     # request image subpods
            "width": "500",
            "mag": "2",            # higher resolution
        }, timeout=15)

        if response.status_code != 200:
            return f"Wolfram Alpha error (HTTP {response.status_code}): {response.text}"

        data = response.json()
        query_result = data.get("queryresult", {})

        if not query_result.get("success"):
            return f"Wolfram Alpha could not understand the query: {query}"

        pods = query_result.get("pods", [])
        if not pods:
            return f"Wolfram Alpha returned no results for: {query}"

        # 1. Try to find a pod whose title matches a visual keyword
        best_img_url = None
        fallback_img_url = None
        for pod in pods:
            title_lower = pod.get("title", "").lower()
            subpods = pod.get("subpods", [])
            for subpod in subpods:
                img_src = subpod.get("img", {}).get("src")
                if not img_src:
                    continue
                # Record first available image as fallback
                if fallback_img_url is None and title_lower != "input interpretation":
                    fallback_img_url = img_src
                # Check if this pod is a visualization pod
                if any(kw in title_lower for kw in VISUAL_POD_KEYWORDS):
                    best_img_url = img_src
                    break  # take the first matching subpod image
            if best_img_url:
                break

        chosen_url = best_img_url or fallback_img_url
        if not chosen_url:
            return f"Wolfram Alpha did not return a visual image for: {query}"

        # 2. Download the chosen pod image
        img_response = requests.get(chosen_url, timeout=10)
        if img_response.status_code != 200:
            return f"Failed to download the plot image from Wolfram Alpha."

        filename = f"shape_{uuid.uuid4().hex}.png"
        media_chat_dir = os.path.join(settings.MEDIA_ROOT, 'chat_images')
        os.makedirs(media_chat_dir, exist_ok=True)
        filepath = os.path.join(media_chat_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(img_response.content)

        base_url = getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        return f"![Mathematical Visualization]({base_url}{media_url}chat_images/{filename})"

    except requests.exceptions.Timeout:
        return "Error: Wolfram Alpha visual query timed out."
    except Exception as e:
        return f"Error: {str(e)}"
def generate_practice_questions(topic: str, request_language: str = 'Bulgarian', num_questions: int = 5) -> str:
    """Use this tool whenever the user demonstrates an intent to practice, be tested, receive sample problems, or generate exam-style questions. 
    Triggers on both semantic intent (e.g., 'quiz me', 'give me some task') and explicit keywords (e.g., 'generate questions', 'practice', 'mock test', 'exam-style', 'тест', 'въпроси', 'задачи').
    topic: The specific math topic or area to focus on.
    request_language: User's language (default 'Bulgarian').
    num_questions: Count of questions."""
    from chatbot.rag.retriever import get_document_context
    import google.generativeai as genai
    import random
    
    # Fetch 10 chunks for better coverage
    context = get_document_context(topic, k=10)
    
    if request_language.lower() in ['english', 'en', 'eng']:
        try:
            translator_model = genai.GenerativeModel('models/gemini-2.5-flash')
            translation_prompt = f"Translate the following Bulgarian document text to clear English. Keep math and multiple-choice labels format:\n\n{context}"
            tr_resp = translator_model.generate_content(translation_prompt)
            if tr_resp.text:
                context = tr_resp.text
        except Exception:
            pass
    
    seed = random.randint(1000, 999999)
    return (
        f"KNOWLEDGE BASE CONTEXT (STRICT BOUNDARY):\n{context}\n\n"
        f"TASK: Generate EXACTLY {num_questions} practice questions about '{topic}'.\n\n"
        f"STRICT INSTRUCTIONS:\n"
        f"1. You are FORBIDDEN from using your own general mathematical knowledge to create these questions. You MUST only use the logic, difficulty level, and problem-solving patterns found in the KNOWLEDGE BASE CONTEXT above.\n"
        f"2. Mimic the exact structural format (labels, spacing, LaTeX) of the context.\n"
        f"3. Generate unique variants; do not repeat the same question twice.\n"
        f"4. Output must be in {request_language}.\n"
        f"5. NO 'Steps' or 'Final Answer' boxes. Just the questions.\n"
        f"[Seed: {seed}]"
    )

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
        "You MUST auto-detect if the user's prompt is in English or Bulgarian. If it is English, respond entirely in English. If it is Bulgarian, respond entirely in Bulgarian."
    )
    return (
        "You are an expert AI assistant with two specialized modes. You MUST determine which mode to use based on the user's request.\n\n"
        f"{lang_instruction}\n\n"
        "### MODE 1: MATH TUTOR (Problem Solving)\n"
        "Use this mode when the user asks you to solve a math problem, explain a concept, or answer any of the practice questions you just generated.\n"
        "1. FORMATTING: Every response MUST be structured as a sequence of numbered logical steps: 'Step 1: ...', 'Step 2: ...', etc. You MUST derive the logical steps yourself. Start your response immediately with Step 1.\n"
        "2. STEP STRUCTURE: Step 1: [Observation/Setup], Step 2: [Calculation], Step 3: [Result], etc. The last step should naturally state the result as part of the explanation. DO NOT add a separate 'Final Answer:' or '\\boxed{}' block at the end. The answer must appear within the last logical step only.\n"
        "3. SMART TOOLS: Use `draw_wolfram_alpha_shape` for visualizations. Include Markdown links for images. NEVER mention tool names to the user.\n"
        "4. VISION: Use your own built-in vision to analyze user-provided images directly.\n\n"
        "### MODE 2: QUESTION GENERATOR (Exam Practice)\n"
        "Use this mode when the user's message contains knowledge base context and asks to generate practice questions, tests, or exam-style problems.\n"
        "1. CONTEXT: The knowledge base context will be provided in the user message. Use ONLY the patterns, topics, and difficulty levels from that context to create the questions. If the user does not specify a number, you MUST generate at least 7 questions by default.\n"
        "2. NO EXTRA TEXT: You MUST start your response immediately with the first question. Do NOT output any introductory text, previous mathematical solutions, 'Steps', 'Final Answers', or meta-talk like 'Here are your questions'.\n"
        "3. STEALTH: NEVER reveal that you are reading from a document or using context. Act as if you are generating these questions from your own expertise.\n"
        "4. STRUCTURE: You MUST exactly mimic the formatting found in the provided context. If it uses multiple-choice with (A, B, V, G), match that. If English is requested, translate to English and use (A, B, C, D).\n"
        "5. DIFFICULTY: Match the exact mathematical difficulty level found in the context.\n"
        "6. VARIETY: Create NEW questions that are 'clones' or 'variants' of the types found in the context. You MUST generate at least 5 distinct questions.\n"
        "7. FLOW: If the user asks for answers to these questions after you generate them, switch immediately to MODE 1 to provide the detailed solutions.\n\n"
        "### GLOBAL RULES:\n"
        "- You ARE context-aware: you remember the full conversation and can reference earlier questions, answers, or generated problems when the user asks about them (e.g. 'solve question 3', 'what if x=5 instead?', 'explain your previous step').\n"
        "- CRITICAL — NO RECAPPING: When the user sends a NEW, independent problem, respond ONLY with the solution to THAT problem. NEVER repeat, summarize, or include solutions from earlier messages. Your response must contain ZERO text about prior problems unless the user EXPLICITLY references them.\n"
        "- Use LaTeX for all mathematical expressions.\n"
        "- Respond in the detected or specified language.\n"
        "- Never mention external tools (Wolfram Alpha, RAG, etc.)."
    )


from rest_framework.pagination import PageNumberPagination


SIMPLE_INTENT_KEYWORDS = [
    'generate', 'create', 'make', 'quiz', 'test', 'practice', 'give me questions',
    'задачи', 'въпроси', 'тест', 'генерирай', 'exam', 'mid term', 'midterm',
    'questions for', 'sample problems', 'mock', 'задачи за'
]


def detect_question_intent(message: str) -> bool:
    """
    Returns True if the user wants to generate practice questions.
    Used to bypass Gemini tool calling and call RAG directly.
    """
    if not message:
        return False
    lowered = message.lower()
    for kw in SIMPLE_INTENT_KEYWORDS:
        if kw in lowered:
            return True
    return False

def wrap_message_for_steps(message: str) -> str:
    """
    For any substantial math problem (non-trivial query), inject a strict
    chain-of-thought directive directly into the user message turn.
    This is more reliable than system instructions alone because
    Gemini gives higher priority to live user-turn content.
    """
    if not message or len(message.strip()) < 30:
        return message  # Too short to be a complex problem — leave as-is

    lowered = message.lower()
    for kw in SIMPLE_INTENT_KEYWORDS:
        if kw in lowered:
            return message  # It's a question-generation request — don't inject steps

    prefix = (
        "[INSTRUCTION — follow exactly]\n"
        "Solve ONLY the problem below. Do NOT repeat, recap, or reference solutions from earlier messages unless I explicitly ask about them.\n\n"
        "You MUST:\n"
        "1. Start your response immediately with 'Step 1:'.\n"
        "2. Work through the logic with numbered steps: 'Step 1:', 'Step 2:', etc.\n"
        "3. Show ALL intermediate calculations inline within the steps.\n"
        "4. Do NOT jump to the answer. Do NOT add a 'Final Answer:' block at the end.\n"
        "5. The answer must appear naturally inside the last step.\n"
        "6. Your ENTIRE response must be about the problem below — nothing else.\n\n"
        "[PROBLEM]\n"
    )
    return prefix + message


def safe_extract_response_text(response) -> str:
    """
    Safely extract text from a Gemini response.
    response.text throws if the response has no text parts (e.g. after
    automatic function calling returns an empty final turn).
    This helper inspects the raw candidates/parts to avoid crashing.
    """
    try:
        return response.text
    except ValueError:
        # Fallback: manually walk through candidates and parts
        if response.candidates:
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    text_parts = [p.text for p in candidate.content.parts if hasattr(p, 'text') and p.text]
                    if text_parts:
                        return "\n".join(text_parts)
        return "I'm sorry, I couldn't generate a response for that. Please try rephrasing your question."


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
            model = genai.GenerativeModel('gemini-2.5-flash', system_instruction=system_instruction, tools=[draw_wolfram_alpha_shape])

            # 2b. Detect question-generation intent and handle RAG directly
            is_question_gen = detect_question_intent(user_message_text)
            if is_question_gen:
                rag_context = generate_practice_questions(
                    topic=user_message_text,
                    request_language=user_language or detect_language_from_text(user_message_text),
                    num_questions=7
                )
                # Inject RAG context directly into the message instead of relying on tool calling
                user_message_text_for_ai = rag_context + "\n\nOriginal user request: " + user_message_text
            else:
                user_message_text_for_ai = None  # Will use wrap_message_for_steps below

            # 3. Build History for Context
            history = []
            # Fetch the latest 20 messages, excluding the current one we just saved
            previous_messages = ChatMessage.objects.filter(session=session).exclude(id=user_message_obj.id).order_by('-created_at')[:20]
            
            # Gemini expects chronological history: [user, model, user, model]
            for msg in reversed(previous_messages):
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
                if is_question_gen:
                    inputs.append(user_message_text_for_ai)
                else:
                    inputs.append(wrap_message_for_steps(user_message_text))
            
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
                    ai_response_text = safe_extract_response_text(response)
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
                tools=[draw_wolfram_alpha_shape]
            )

            # Detect question-generation intent and handle RAG directly
            is_question_gen = detect_question_intent(user_message_text)
            if is_question_gen:
                rag_context = generate_practice_questions(
                    topic=user_message_text,
                    request_language=language or detect_language_from_text(user_message_text),
                    num_questions=7
                )
                user_message_text_for_ai = rag_context + "\n\nOriginal user request: " + user_message_text
            else:
                user_message_text_for_ai = None

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
                if is_question_gen:
                    inputs.append(user_message_text_for_ai)
                else:
                    inputs.append(wrap_message_for_steps(user_message_text))
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
                ai_response_text = safe_extract_response_text(response)
                
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
