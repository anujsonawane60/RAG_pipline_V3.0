# Multi-LLM RAG Chatbot

Production-ready Retrieval-Augmented Generation (RAG) platform for building and deploying chatbots backed by vector search. Supports document ingestion (PDF/DOCX/TXT), multiple LLM providers (OpenAI, Cohere, TogetherAI), Pinecone for vectors, JWT auth, role-based access, and a simple admin dashboard.

Quick links
- Docker usage: DOCKER_USAGE.md
- Example environment: .env.example

Highlights
- Create, manage, and delete chatbots
- Upload documents (PDF, DOCX, TXT) to provide retrieval context
- Choose from multiple LLM providers (OpenAI, Cohere, TogetherAI)
- Pinecone vector store integration
- JWT authentication with admin / user roles
- Public chatbots for anonymous access
- Web UI (static/) and REST API (FastAPI)

Table of contents
- Features
- Architecture & code layout
- Quickstart (local)
- Quickstart (Docker)
- Configuration / environment variables
- API overview
- Admin & usage notes
- Contributing
- License

## Features
- Create, manage, and delete chatbots
- Upload and validate files (PDF, DOCX, TXT)
- Chat with chatbots using retrieval-augmented prompts
- Persistent chat history per chatbot
- Role-based access (admin / regular user)
- Public chatbots for anonymous usage

## Architecture & repo layout
Top-level important entries:

```
app/                FastAPI application code (routes, services, models)
  ├── routes/        HTTP endpoints (auth_routes.py, chatbot_routes.py)
  ├── services/      Business logic (chatbot_manager.py, user_manager.py)
  └── models/        Pydantic schemas
static/             Frontend HTML (index.html, chatbot.html, admin.html, auth.html)
main.py             FastAPI app entrypoint
requirements.txt    Python dependencies
Dockerfile          Docker image build
docker-compose.yml  Compose for local Docker setup
DOCKER_USAGE.md     Detailed notes on using the pre-built image
.env.example        Template environment variables
README.MD           This file
```

How it fits together
- main.py mounts the FastAPI app under app/ and serves static/ HTML pages for the frontend.
- app/routes contains the HTTP endpoints. chatbot_routes.py handles chatbot creation, file upload, ask, and history; auth_routes.py handles registration/login and user info.
- app/services contains managers for chatbot lifecycle, user management, and text processing (ingestion & chunking).
- Pinecone is used as the vector store; LLM providers are pluggable via configuration.

## Quickstart — Local (minimal)
1. Clone the repository:
```bash
git clone https://github.com/anujsonawane60/RAG_pipline_V3.0.git
cd RAG_pipline_V3.0
```
2. Create and activate a virtual environment:
```bash
python3 -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
```
3. Install dependencies:
```bash
pip install -r requirements.txt
```
4. Copy `.env.example` to `.env` and fill in keys (see Configuration below):
```bash
cp .env.example .env
# edit .env to add API keys and secrets
```
5. Run the app:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
6. Open http://127.0.0.1:8000/ to view the frontend (index.html) and the API docs at http://127.0.0.1:8000/docs

## Quickstart — Docker
Build & run with docker-compose (recommended):

```bash
docker-compose up -d --build
```

Or run the pre-built image (replace image name):

```bash
docker run -d \
  --name rag-chatbot \
  -p 8000:8000 \
  --env-file .env \
  -v rag_uploaded_files:/app/uploaded_files \
  -v rag_chat_history:/app/chat_history \
  -v rag_data:/app/data \
  yourusername/rag-chatbot:latest
```

See DOCKER_USAGE.md for details and published image examples.

## Configuration / environment variables
Copy `.env.example` to `.env` and populate the keys. Important variables used by the app (examples):

```
OPENAI_API_KEY=
COHERE_API_KEY=
TOGETHERAI_API_KEY=
PINECONE_API_KEY=
JWT_SECRET_KEY=
HOST_USERNAME=
HOST_PASSWORD=
```

- JWT_SECRET_KEY: used to sign access tokens — use a strong random value in production.
- HOST_USERNAME / HOST_PASSWORD: convenience admin credentials (configured in the environment).
- Pinecone/OpenAI/Cohere credentials: required if you intend to use those providers.

## API overview
Authentication
- POST /register — create a new user
- POST /token — get an access token (JWT)
- GET /users/me — get current user info

Chatbot & usage
- GET /chatbots — list chatbots for the current user (admin sees all)
- GET /public-chatbots — list public chatbots (no auth required)
- POST /chatbot/create — create a new chatbot
- DELETE /chatbot/{chatbot_id} — delete a chatbot
- POST /chatbot/{chatbot_id}/upload — upload files to a chatbot
- POST /chatbot/{chatbot_id}/ask — send a question to a chatbot
- GET /chatbot/{chatbot_id}/history — fetch chat history
- POST /chatbot/{chatbot_id}/update-visibility — admin-only visibility toggle

Admin routes
- GET /admin — admin dashboard (web UI)

## Usage notes
- File uploads are validated for type/size before ingestion. Text is chunked and embedded then written to Pinecone.
- Chat history is saved under the chat_history directory (or inside container volume when using Docker).
- Public chatbots let anonymous users ask questions but do not allow modification.

## Troubleshooting & common tasks
- If the frontend doesn't appear, ensure uvicorn is running and static files are being served by FastAPI.
- If Pinecone errors occur, verify API key and index configuration in app/config.py.
- To reset demo data when using Docker volumes, remove the named volumes and restart docker-compose.

## Contributing
Contributions are welcome. Open an issue or submit a PR with a clear description of the change and tests/documentation when applicable.

## License
Include your license here (e.g., MIT) or add a LICENSE file at the repository root.

---
If you want, I can also:
- Add badges (build / license) to the top of the README
- Expand the Configuration section with a full `.env.example` snippet pulled from the repo
- Create a short quick demo script and update DOCKER_USAGE.md
