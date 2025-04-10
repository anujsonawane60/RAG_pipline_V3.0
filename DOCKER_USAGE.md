# Using the RAG Chatbot Docker Image

This guide explains how to use the published Docker image for the RAG Chatbot platform with your own API keys.

## Prerequisites

- Docker installed on your system
- API keys for OpenAI, Cohere, TogetherAI, and Pinecone
- A secure JWT secret key

## Quick Start

1. Create a `.env` file with your API keys:

```
OPENAI_API_KEY=your_openai_key 
COHERE_API_KEY=your_cohere_key 
TOGETHERAI_API_KEY=your_togetherai_key 
PINECONE_API_KEY=your_pinecone_key
JWT_SECRET_KEY=your_jwt_secret_key
```

2. Run the Docker container with your environment variables:

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

Replace `yourusername/rag-chatbot:latest` with the actual image name from Docker Hub.

3. Access the application at http://localhost:8000

## Using docker-compose

Alternatively, you can use docker-compose:

1. Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  rag-chatbot:
    image: yourusername/rag-chatbot:latest
    ports:
      - "8000:8000"
    volumes:
      - rag_uploaded_files:/app/uploaded_files
      - rag_chat_history:/app/chat_history
      - rag_data:/app/data
    env_file:
      - .env
    restart: always

volumes:
  rag_uploaded_files:
  rag_chat_history:
  rag_data:
```

2. Create your `.env` file with API keys as shown above.

3. Run the application:

```bash
docker-compose up -d
```

## Volume Persistence

The application uses Docker volumes to persist data:

- `rag_uploaded_files`: Stores all uploaded documents
- `rag_chat_history`: Stores chat conversation history
- `rag_data`: Stores application data including user information

## Updating the Image

To update to a newer version of the image:

```bash
# Using docker
docker pull yourusername/rag-chatbot:latest
docker rm -f rag-chatbot
# Then run the container again with the same command as above

# Using docker-compose
docker-compose pull
docker-compose up -d
```

## Security Considerations

- Store your `.env` file securely and never commit it to version control
- For production deployments, consider using Docker secrets or a secure environment variable management solution
- The default admin credentials are username: `host_admin`, password: `admin123`. Change these for production use.

## Troubleshooting

If you encounter issues:

1. Check the container logs:
```bash
docker logs rag-chatbot
# or with docker-compose
docker-compose logs
```

2. Verify your API keys are correct in the `.env` file

3. Make sure all required ports are available 