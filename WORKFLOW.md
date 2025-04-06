# RAG Pipeline Docker Workflow Documentation

## Overview
This document explains the complete workflow of the RAG (Retrieval-Augmented Generation) Pipeline application running in Docker, including how files are handled, ports are managed, and data persistence works.

## Docker Setup

### Container Configuration
- Base Image: Python 3.10-slim
- Exposed Port: 8000
- Working Directory: /app
- Entry Point: Uvicorn server running main.py

### Port Mapping
- Container Port: 8000 (internal)
- Host Port: 8000 (external)
- When you access localhost:8000, requests are forwarded to the container's port 8000

## Application Structure

### Key Directories
1. `/app` - Main application directory inside container
2. `uploaded_files` - Directory for storing uploaded documents
3. `chat_history` - Directory for storing chat histories
4. `static` - Directory for static files

### Data Persistence
1. File Storage:
   - Uploaded files are stored in the `uploaded_files` directory
   - In Docker, these files are stored inside the container
   - To persist data between container restarts, you should use Docker volumes

2. Database:
   - The application uses Pinecone (cloud-based vector database)
   - Database configuration:
     - Cloud: AWS
     - Region: us-east-1
     - Dimension: 1024

## Application Workflow

### 1. Container Startup
1. Docker container starts with the command: `uvicorn main:app --host 0.0.0.0 --port 8000`
2. FastAPI application initializes
3. CORS middleware is configured to allow all origins
4. Static file serving is set up

### 2. File Upload Process
1. Files are uploaded via `/chatbot/{chatbot_name}/upload` endpoint
2. Files are temporarily stored in the container's filesystem
3. Text is extracted from documents (PDF/DOCX)
4. Content is chunked and embedded
5. Embeddings are stored in Pinecone

### 3. Query Processing
1. Queries received at `/chatbot/{chatbot_name}/ask`
2. System retrieves relevant context from Pinecone
3. Selected LLM (OpenAI/Cohere/TogetherAI) generates response
4. Chat history is saved

### 4. Data Storage
1. Chat Histories:
   - Stored in JSON format
   - Located in `chat_history` directory
   - Includes timestamps and conversation flow

2. Uploaded Files:
   - Stored in `uploaded_files/{chatbot_name}`
   - Organized by chatbot instance
   - Original files preserved for reference

## Port Configuration
- The port configuration is defined in multiple places:
  1. Dockerfile: `EXPOSE 8000`
  2. main.py: Uvicorn configuration `--port 8000`
  3. Docker run command: `-p 8000:8000` (maps host port to container port)

## Best Practices for Production

### Data Persistence
To persist data between container restarts:
```bash
docker run -v /host/path/to/data:/app/uploaded_files -p 8000:8000 your-image-name
```

### Environment Variables
- Store sensitive information in `.env` file
- Mount as Docker secrets in production
- Required variables:
  - OPENAI_API_KEY
  - COHERE_API_KEY
  - TOGETHERAI_API_KEY
  - PINECONE_API_KEY

### Security Considerations
1. Use Docker volumes for persistent storage
2. Implement proper authentication
3. Secure API keys and sensitive data
4. Regular backup of chat histories and uploaded files

## Troubleshooting

### Common Issues
1. Port conflicts:
   - Ensure port 8000 is not in use by other services
   - Change port mapping if needed: `-p <new-port>:8000`

2. File persistence:
   - Check volume mounting
   - Verify file permissions

3. Database connection:
   - Verify Pinecone API key
   - Check network connectivity
   - Confirm index existence

### Logs
- Access container logs: `docker logs <container-id>`
- Application logs are output to stdout/stderr
- Check for error messages in the container logs

## Development vs Production
- Development:
  - Use Docker Compose for easier management
  - Mount volumes for live code updates
  - Enable debug mode

- Production:
  - Use proper container orchestration (e.g., Kubernetes)
  - Implement health checks
  - Set up monitoring and logging
  - Use production-grade database configurations 