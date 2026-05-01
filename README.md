# AI Math Solver & Tutor 🧮🤖

A powerful, AI-driven backend for a Math Solver application. This project uses **Django** and **Google Gemini 2.5 Pro** to provide a seamless, multi-modal tutoring experience. Students can interact via text, images, or voice, and the AI responds with step-by-step solutions in English or Bulgarian — complete with accurate geometric diagrams and function plots.

## 🚀 Key Features

### 🔐 Authentication & User Management
-   **Secure Registration**: Email-based signup with valid email verification via OTP (SMTP) and strict rate limit cooldowns.
-   **Social Login**: Cryptographically verified Google Sign-In backend integration (OAuth2) with auto-provisioning.
-   **JWT Authentication**: Secure, stateless authentication using JSON Web Tokens.
-   **Password Reset**: Secure, session-based password recovery flow with OTP verification.
-   **Token Refresh**: Automatic access token refresh for uninterrupted sessions.
-   **Logout**: Secure JWT token blacklisting on logout.

### 🧠 AI Chatbot (Gemini Powered)
-   **Math Tutor Persona**: Specialized system instructions enforce a patient, step-by-step tutoring style with proper LaTeX formatting for all mathematical expressions.
-   **Dual-Mode Intelligence**:
    -   **Mode 1 — Math Tutor**: Solves problems with numbered logical steps (Step 1, Step 2, etc.) and naturally embeds the final answer within the last step.
    -   **Mode 2 — Question Generator**: Generates exam-style practice questions from uploaded documents using RAG (Retrieval-Augmented Generation).
-   **Smart Visualization Tools** (Automatic Function Calling):
    -   **Wolfram Alpha** (`draw_wolfram_alpha_shape`): Mandatory for all simple shapes (circles, triangles, squares) and pure function plots (sin(x), e^x, y=x², etc.). Extracts only the relevant visual pod from the API response.
    -   **Matplotlib** (`draw_matplotlib_diagram`): Reserved exclusively for complex geometric constructions requiring labeled vertices, midpoints, intersecting cevians, medians, shaded regions, and computed coordinate geometry. All diagrams are rendered in solid black lines for clarity.
-   **Wolfram|Alpha Validation**: Intercepts deterministic math queries and proxies them through the Wolfram LLM API using direct Function Calling.
-   **Multi-Modal Inputs**:
    -   **Text**: Type math problems directly.
    -   **Image**: Upload photos of handwritten or printed math problems.
    -   **Voice/Audio**: Record and upload voice queries (e.g., "Solve this linear equation"). Integrates temporary disk buffering to prevent quota leaks.
-   **Auto-Language Detection**: Automatically detects Bulgarian (Cyrillic) or English text and responds in the corresponding language. Wolfram Alpha responses are translated accordingly.
-   **Context Awareness**: Maintains chat history within sessions so the AI remembers previous context, leveraging DRF pagination (N+1 query optimized).
-   **Guest Chat**: Unauthenticated users can try the AI chatbot in a stateless, single-turn mode without creating an account.

### 📚 RAG-Based Question Generator
-   **Document Ingestion**: Upload PDF or DOCX files containing mathematical problems. Documents are chunked and stored in a ChromaDB vector database.
-   **Context-Aware Generation**: The system retrieves the most relevant document chunks (k=10) and generates new, unique practice questions that mimic the exact format, difficulty, and style of the source material.
-   **Language-Specific Formatting**: Automatically adapts multiple-choice labels — uses **(A, B, C, D)** for English prompts and **(А, Б, В, Г)** for Bulgarian prompts.
-   **Intent Detection**: Automatically switches between Tutor and Question Generator modes based on keyword detection in the user's message.

## 🛠️ Tech Stack

-   **Backend Framework**: Django 6.0, Django Rest Framework (DRF), & Gunicorn
-   **AI Model**: Google Generative AI (`google-generativeai`) — **Gemini 2.5 Pro**
-   **Visualization**: Wolfram Alpha Full Results API (v2) & Matplotlib (Agg backend)
-   **RAG Pipeline**: ChromaDB (vector store), PyPDF, python-docx (document parsers)
-   **Authentication**: `djangorestframework-simplejwt` & `google-auth`
-   **Task Queue**: Celery & Redis (asynchronous background email processing)
-   **Database**: SQLite (volume-mapped) / extensible to PostgreSQL
-   **Infrastructure**: Docker & Docker Compose
-   **Static Files**: WhiteNoise (compressed manifest storage in production)
-   **Environment Management**: `python-dotenv`

## 📁 Project Structure

```
Math_Solver/
├── auth_system/          # Django project settings, WSGI, URLs
│   ├── settings.py       # All configuration (DB, API keys, CORS, JWT, Celery)
│   └── urls.py           # Root URL routing
├── users/                # Authentication & user management app
│   ├── models.py         # Custom User model with OTP fields
│   ├── views.py          # Register, Login, Google OAuth, Password Reset
│   ├── serializers.py    # DRF serializers for auth endpoints
│   ├── tasks.py          # Celery tasks for async email delivery
│   ├── throttles.py      # Rate limiting for OTP endpoints
│   └── urls.py           # Auth URL patterns
├── chatbot/              # AI chatbot & visualization app
│   ├── models.py         # ChatSession & ChatMessage models
│   ├── views.py          # Core AI logic, tool routing, RAG integration
│   ├── serializers.py    # Message serialization with image URL extraction
│   ├── urls.py           # Chat URL patterns
│   └── rag/              # Retrieval-Augmented Generation module
│       ├── ingest_document.py  # PDF/DOCX chunking & ChromaDB storage
│       └── retriever.py        # Vector similarity search
├── documents/            # Uploaded source documents for RAG
├── media/                # Generated images (diagrams, Wolfram plots)
│   └── chat_images/      # Matplotlib-generated diagram storage
├── Dockerfile            # Python 3.12 container definition
├── docker-compose.yml    # Multi-service orchestration (web, redis, celery)
├── entrypoint.sh         # Auto-migration & static collection on startup
├── requirements.txt      # Python dependencies
└── .env                  # Environment variables (not committed)
```

## ⚙️ Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/rahamanatiq/Math_Solver.git
cd Math_Solver
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory and add the following:

```env
# Email Configuration (for OTPs)
EMAIL_USER=your_email@gmail.com
EMAIL_PASS=your_app_password  # Generate from Google Account > Security > App Passwords

# API Keys
GEMINI_API_KEY=your_gemini_api_key          # Get from Google AI Studio
WOLFRAM_ALPHA_APP_ID=your_wolfram_app_id    # Get from Wolfram Alpha Developer Portal
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# Django Security
SECRET_KEY=your_cryptographically_secure_django_secret
DEBUG=True

# Routing & Networking
BASE_URL=http://127.0.0.1:8000
FRONTEND_URL=http://localhost:3000
```

### 3. Start the Application (Docker — Recommended)
Ensure Docker Desktop is running, then execute:
```bash
docker-compose up --build
```

**That's it!** Docker will automatically:
- Build the Python 3.12 environment and install all dependencies from `requirements.txt`.
- Pull down Alpine Redis for the Celery message broker.
- Start the Celery Worker for background email delivery.
- Run `python manage.py migrate` and `collectstatic` via `entrypoint.sh`.
- Launch the Gunicorn production server with a 300-second timeout.

The API will be available at `http://127.0.0.1:8000/`.

### Local Development (Without Docker)
If you prefer running locally without containers:
```bash
python -m venv venv
venv\Scripts\activate   # Windows
source venv/bin/activate # Mac/Linux

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```
> **Note**: Without Docker, you will need to run Redis and Celery separately, or the app will fall back to synchronous email sending.

## 📡 API Documentation

### Auth Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/users/register/` | Register a new user |
| `POST` | `/api/users/verify-email/` | Verify email with OTP |
| `POST` | `/api/users/resend-otp/` | Resend OTP code |
| `POST` | `/api/users/login/` | Login (Email/Username + Password) |
| `POST` | `/api/users/google-login/` | Google Social Login (OAuth2) |
| `POST` | `/api/users/token/refresh/` | Refresh access token |
| `POST` | `/api/users/password-reset/` | Request password reset OTP |
| `POST` | `/api/users/password-reset/verify/` | Verify password reset OTP |
| `POST` | `/api/users/password-reset/confirm/` | Set new password |
| `GET`  | `/api/users/profile/` | Get user profile |
| `POST` | `/api/users/logout/` | Logout (blacklist token) |
| `GET`  | `/api/users/terms-privacy/` | Get terms & privacy policy |

### Chatbot Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/chat/sessions/` | Create a new chat session |
| `GET`  | `/api/chat/sessions/` | List all chat sessions (paginated) |
| `GET`  | `/api/chat/sessions/{id}/` | Get chat history for a session |
| `PUT`  | `/api/chat/sessions/{id}/` | Rename a chat session |
| `DELETE` | `/api/chat/sessions/{id}/` | Delete a chat session |
| `POST` | `/api/chat/sessions/{id}/send/` | Send message (Text/Image/Audio) |
| `POST` | `/api/chat/guest/` | Guest chat (no auth required) |

### Example: Send a Message
```json
POST /api/chat/sessions/1/send/
Content-Type: application/json
Authorization: Bearer <your_jwt_token>

{
    "message": "Solve x^2 + 5x + 6 = 0 step by step"
}
```

### Example: Generate Practice Questions
```json
POST /api/chat/sessions/1/send/
Content-Type: application/json
Authorization: Bearer <your_jwt_token>

{
    "message": "Generate 5 practice questions about quadratic equations"
}
```

For detailed request/response examples, refer to the `Postman_API_Testing_Guide.pdf` included in the repository.

## 🤝 Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## 📄 License
[MIT](https://choosealicense.com/licenses/mit/)