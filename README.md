# AI Math Solver & Tutor 🧮🤖

A powerful, AI-driven backend for a Math Solver application. This project uses **Django** and **Google Gemini 2.0 Flash** to provide a seamless, multi-modal tutoring experience. Students can interact via text, images, or voice, and the AI responds with step-by-step solutions in English or Bulgarian.

## 🚀 Key Features

### 🔐 Authentication & User Management
-   **Secure Registration**: Email-based signup with valid email verification via OTP (SMTP) and strict rate limit cooldowns.
-   **Social Login**: Cryptographically verified Google Sign-In backend integration (OAuth2) with auto-provisioning.
-   **JWT Authentication**: Secure, stateless authentication using JSON Web Tokens.
-   **Password Reset**: Secure, session-based password recovery flow with OTP verification.

### 🧠 AI Chatbot (Gemini Powered)
-   **Math Tutor Persona**: Specialized system instructions to act as a helpful, patient tutor showing step-by-step work.
-   **Wolfram|Alpha Validation**: intercepts deterministic math queries and proxies them through the Wolfram LLM API using direct Function Calling.
-   **Multi-Modal Inputs**:
    -   **Text**: Type math problems directly.
    -   **Image**: Upload photos of handwritten or printed math problems.
    -   **Voice/Audio**: Record and upload voice queries (e.g., "Solve this linear equation"). Integrates temporary disk buffering to prevent quota leaks.
-   **Auto-Language Detection**: Automatically translates Wolfram responses and defaults strictly to **Bulgarian** or **English** based on the user's dynamic payload.
-   **Context Awareness**: Maintains chat history within sessions so the AI remembers previous context, leveraging DRF pagination (N+1 query optimized).

## 🛠️ Tech Stack

-   **Backend Framework**: Django, Django Rest Framework (DRF), & Gunicorn
-   **AI Integration**: Google Generative AI (`google-generativeai`) - **Gemini 2.0 Flash**
-   **Authentication**: `djangorestframework-simplejwt` & `google-auth`
-   **Task Queue**: Celery & Redis (Asynchronous background processing)
-   **Database**: SQLite (Volume-mapped) / Extensible to PostgreSQL
-   **Infrastructure**: Docker & Docker Compose
-   **Environment Management**: `python-dotenv`

## ⚙️ Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/rahamanatiq/Math_Solver.git
cd Math_Solver
```

(Skip steps 2 and 3 if you are using Docker Desktop)

### Local Development (Without Docker)
If you prefer running locally without containers, the app gracefully falls back to synchronous email sending:
```bash
python -m venv venv
venv\Scripts\activate   # Windows
source venv/bin/activate # Mac/Linux

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory and add the following:

```env
# Email Configuration (for OTPs)
EMAIL_USER=your_email@gmail.com
EMAIL_PASS=your_app_password  # Generate from Google Account > Security > App Passwords

# API Keys
GEMINI_API_KEY=your_gemini_api_key  # Get from Google AI Studio
WOLFRAM_ALPHA_APP_ID=your_wolfram_app_id
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# Django Security
SECRET_KEY=your_cryptographically_secure_django_secret
DEBUG=True

# Routing & Networking
BASE_URL=http://127.0.0.1:8000
FRONTEND_URL=http://localhost:3000
```

### 3. Start the Application (Docker)
Ensure Docker Desktop is running, then execute:
```bash
docker-compose up --build
```

**That's it!** Docker will automatically:
- Build the Python 3.12 environment and install `requirements.txt`.
- Pull down Alpine Redis.
- Start the Celery Worker for background emails.
- Run `python manage.py migrate` and `collectstatic` via `entrypoint.sh`.
- Launch the Gunicorn production server.

The API will instantly be available at `http://127.0.0.1:8000/`.

## 📡 API Documentation

### Auth Endpoints
-   `POST /api/users/register/` - Register new user
-   `POST /api/users/verify-email/` - Verify OTP
-   `POST /api/users/login/` - Login (Email/Username + Password)
-   `POST /api/users/google-login/` - Google Social Login
-   `POST /api/users/password-reset/` - Request Password Reset

### Chatbot Endpoints
-   `POST /api/chat/sessions/` - Create a new chat session
-   `GET /api/chat/sessions/{id}/` - Get chat history
-   `POST /api/chat/sessions/{id}/send/` - Send message (Text/Image/Audio)

For detailed request/response examples, please refer to the `Postman_Guide.md` file included in the repository (if available) or explore the code.

## 🤝 Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## 📄 License
[MIT](https://choosealicense.com/licenses/mit/)