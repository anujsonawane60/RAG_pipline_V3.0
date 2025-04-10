# Multi-LLM RAG Chatbot

This project implements a Retrieval-Augmented Generation (RAG) chatbot platform that allows users to create chatbots, upload documents, and chat with them using multiple Language Models (LLMs).

## Features

*   Create, manage, and delete chatbots.
*   Upload PDF, DOCX, and TXT files to provide context.
*   Chat with chatbots and receive responses.
*   Choose between OpenAI, Cohere, and TogetherAI language models.
*   Chat history is saved.
*   The type and size of the uploaded files are validated.
*   User authentication system with registration and login.
*   Role-based access control with admin and regular user roles.
*   Admin users can view and manage all chatbots.
*   Regular users can only access their own chatbots.
*   Secure JWT token-based authentication.
*   **Public chatbots** that can be accessed by anyone without login.
*   Admin dashboard to manage all chatbots and toggle their public visibility.
*   Public chatbot showcase on the homepage for easy access.

## Tech Stack

*   FastAPI
*   Pinecone
*   Cohere
*   OpenAI
*   TogetherAI
*   Python 3.10+
*   Uvicorn
*   PyPDF2
*   docx
*   Bootstrap 5
*   JavaScript

## Installation

### Local Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/anujsonawane60/RAG_Pipeline_V3.git
    ```
2.  Navigate to the project directory:
    ```bash
    cd your-repo-name
    ```
3.  Create a virtual environment (recommended):
    ```bash
    python3 -m venv myenv
    ```
4.  Activate the virtual environment:
    ```bash
    myenv\Scripts\activate
    ```
5.  Install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```
6. Create a `.env` file and add your API Keys.

```
OPENAI_API_KEY=your_openai_key 
COHERE_API_KEY=your_cohere_key 
TOGETHERAI_API_KEY=your_togetherai_key 
PINECONE_API_KEY=your_pinecone_key
JWT_SECRET_KEY=your_secret_key_for_jwt
```

7. Run the app:

```bash
uvicorn main:app --reload
```

### Docker Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/anujsonawane60/RAG_Pipeline_V3.git
   ```

2. Navigate to the project directory:
   ```bash
   cd your-repo-name
   ```

3. Create a `.env` file with your API keys as shown above.

4. Build and run the Docker container:
   ```bash
   docker-compose up -d
   ```

5. The application will be available at http://localhost:8000

## Usage
1. Go to http://127.0.0.1:8000/
2. Register a new account or log in with existing credentials.
3. Admin access is available using hardcoded credentials (username: host_admin, password: admin123).
4. Click on `Dashboard` in the menu.
5. Create a chatbot by clicking on the `Create New` button.
6. Select a chatbot.
7. Upload a file by clicking on `Choose File` and then `Upload File`.
8. Select a model and send messages to the chatbot.

### Admin Features
1. Log in as admin (username: host_admin, password: admin123).
2. Access the Admin Dashboard by clicking the "Admin Dashboard" link in the navigation.
3. View all chatbots in the system and their creators.
4. Toggle chatbots between public and private visibility.
5. Delete any chatbot in the system.

### Public Chatbots
1. Public chatbots are displayed on the homepage and can be used by anyone without login.
2. To create a public chatbot, log in as an admin and check the "Make this chatbot public" option when creating a new chatbot.
3. Existing chatbots can be made public by toggling the switch in the admin dashboard.
4. Public chatbots allow anonymous users to chat with them, but not modify them.

## API Endpoints

### Authentication Endpoints
- **POST /register**: Register a new user account
- **POST /token**: Log in and get an access token
- **GET /users/me**: Get current authenticated user information

### Chatbot Endpoints
- **GET /chatbots**: List all chatbots (admin sees all, users see only their own)
- **GET /public-chatbots**: List all public chatbots (no authentication required)
- **POST /chatbot/create**: Create a new chatbot
- **DELETE /chatbot/{chatbot_id}**: Delete a chatbot
- **POST /chatbot/{chatbot_id}/upload**: Upload a file to a chatbot
- **POST /chatbot/{chatbot_id}/ask**: Chat with a chatbot
- **GET /chatbot/{chatbot_id}/history**: Get chat history for a chatbot
- **POST /chatbot/{chatbot_id}/update-visibility**: Update chatbot visibility (admin only)

### Admin Routes
- **GET /admin**: Access the admin dashboard (admin users only)

## Contributing

## License



