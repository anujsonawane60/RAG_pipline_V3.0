#!/bin/bash

# RAG Chatbot Docker Runner
# This script helps run the RAG Chatbot Docker container with proper environment setup

# Configuration - change this to match your Docker Hub image
DOCKER_IMAGE="yourusername/rag-chatbot:latest"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Creating sample .env file. Please edit it with your actual API keys."
    cat > .env << EOL
OPENAI_API_KEY=your_openai_key 
COHERE_API_KEY=your_cohere_key 
TOGETHERAI_API_KEY=your_togetherai_key 
PINECONE_API_KEY=your_pinecone_key
JWT_SECRET_KEY=your_jwt_secret_key
EOL
    echo ".env file created. Please edit it with your actual API keys, then run this script again."
    exit 1
fi

# Stop any existing container
echo "Stopping any existing RAG Chatbot container..."
docker rm -f rag-chatbot 2>/dev/null

# Pull the latest image
echo "Pulling the latest RAG Chatbot image..."
docker pull $DOCKER_IMAGE

# Run the container
echo "Starting RAG Chatbot container..."
docker run -d \
  --name rag-chatbot \
  -p 8000:8000 \
  --env-file .env \
  -v rag_uploaded_files:/app/uploaded_files \
  -v rag_chat_history:/app/chat_history \
  -v rag_data:/app/data \
  $DOCKER_IMAGE

# Check if container started successfully
if [ $? -eq 0 ]; then
    echo "RAG Chatbot started successfully!"
    echo "Access the application at http://localhost:8000"
    echo "Admin login: username 'host_admin', password 'admin123'"
    echo "To view logs: docker logs rag-chatbot"
    echo "To stop: docker stop rag-chatbot"
else
    echo "Failed to start RAG Chatbot container. Check for errors above."
fi 