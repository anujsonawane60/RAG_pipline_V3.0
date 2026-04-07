# Changelog

**Git commit:** `refactor: modularize codebase, fix security issues, update dependencies`

---

## 2026-04-07 17:33 IST

### Security Fixes
- Moved hardcoded admin credentials (`HOST_USERNAME`, `HOST_PASSWORD`) to `.env` — server refuses to start without them
- Added `JWT_SECRET_KEY` validation on startup — no more silent `None` secret
- Fixed XSS vulnerabilities in all HTML files — added `escapeHtml()` sanitization for all user-supplied values
- Removed sensitive token logging from auth flow
- CORS origins now configurable via `ALLOWED_ORIGINS` env var

### Architecture — Modularized `main.py` (1462 lines → ~70 lines)
- `app/config.py` — centralized env vars and validation
- `app/auth.py` — JWT, password hashing, auth dependencies
- `app/models/schemas.py` — Pydantic models (User, Token, QueryRequest)
- `app/services/service_manager.py` — Pinecone/Cohere client with caching
- `app/services/text_processor.py` — PDF/DOCX extraction and chunking
- `app/services/chatbot_manager.py` — chatbot CRUD and chat history
- `app/services/user_manager.py` — user CRUD and authentication
- `app/routes/auth_routes.py` — `/register`, `/token`, `/users/me`
- `app/routes/chatbot_routes.py` — all chatbot endpoints

### Performance
- Added `ServiceManager` caching — instances reused across requests instead of re-initializing per call
- Replaced blocking `requests.post()` with async `httpx.AsyncClient` for TogetherAI calls
- Cohere system prompt now included in message (v4 SDK has no `preamble` param)

### Dependency Updates
- Updated Cohere model: `command` → `command-a-03-2025` (latest)
- Fixed Pydantic v2 deprecation: `schema_extra` → `json_schema_extra`
- Fixed `datetime.utcnow()` deprecation → `datetime.now(timezone.utc)`
- Removed unused deps: `requests`, `together`, `langchain`
- Added `httpx==0.27.0`
- Pinned all previously unpinned versions (`tenacity`, `python-jose`, `passlib`)

### Other Fixes
- Added server-side file upload size limit (10MB, returns HTTP 413)
- Removed `.:/app` bind mount from `docker-compose.yml` (was conflicting with named volumes)
- Created `.env.example` with all required/optional variables
- Updated `README.MD` — removed exposed admin credentials, added `.env.example` reference
- Added full traceback logging for `/ask` endpoint errors
