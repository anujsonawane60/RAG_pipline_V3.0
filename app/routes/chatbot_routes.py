import os

import httpx
import openai
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, status
from fastapi.responses import JSONResponse

from app.config import Config
from app.auth import get_current_active_user, get_current_user_optional
from app.models.schemas import User, QueryRequest
from app.services.service_manager import get_service_manager
from app.services.text_processor import TextProcessor

router = APIRouter()


def _get_chatbot_manager():
    from app.routes.chatbot_routes import _chatbot_manager

    return _chatbot_manager


_chatbot_manager = None


def set_chatbot_manager(manager):
    global _chatbot_manager
    _chatbot_manager = manager


def _check_chatbot_access(chatbot_id: str, current_user: User, chatbot_manager):
    if chatbot_id not in chatbot_manager.chatbots:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chatbot {chatbot_id} not found",
        )
    if not (current_user.is_host or current_user.username == Config.HOST_USERNAME):
        chatbot_info = chatbot_manager.chatbots.get(chatbot_id)
        if not chatbot_info or chatbot_info.get("user_id") != current_user.username:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this chatbot",
            )


@router.get("/chatbots")
async def list_chatbots(current_user: User = Depends(get_current_active_user)):
    cm = _get_chatbot_manager()
    if current_user.is_host or current_user.username == Config.HOST_USERNAME:
        chatbots = cm.get_all_chatbots()
    else:
        chatbots = cm.get_user_chatbots(current_user.username)
    return {"chatbots": chatbots}


@router.post("/chatbot/create")
async def create_chatbot(
    request: Request, current_user: User = Depends(get_current_active_user)
):
    data = await request.json()
    chatbot_name = data.get("name")
    is_public = data.get("is_public", False)

    if not chatbot_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chatbot name is required",
        )

    user_id = (
        None
        if (current_user.is_host or current_user.username == Config.HOST_USERNAME)
        else current_user.username
    )

    cm = _get_chatbot_manager()
    try:
        result = cm.create_chatbot(chatbot_name, user_id, is_public)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    return {
        "status": "success",
        "message": f"Chatbot '{chatbot_name}' created successfully",
        "chatbot_id": result["chatbot_id"],
        "name": chatbot_name,
        "is_public": is_public,
    }


@router.delete("/chatbot/{chatbot_id}")
async def delete_chatbot(
    chatbot_id: str, current_user: User = Depends(get_current_active_user)
):
    cm = _get_chatbot_manager()
    _check_chatbot_access(chatbot_id, current_user, cm)

    try:
        return cm.delete_chatbot(chatbot_id)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post("/chatbot/{chatbot_id}/upload")
async def upload_file(
    chatbot_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
):
    cm = _get_chatbot_manager()
    _check_chatbot_access(chatbot_id, current_user, cm)

    filename = file.filename
    file_extension = os.path.splitext(filename)[1].lower()

    if file_extension not in [".pdf", ".docx", ".txt"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF, DOCX, and TXT files are allowed",
        )

    # Enforce server-side file size limit
    contents = await file.read()
    if len(contents) > Config.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds {Config.MAX_UPLOAD_SIZE_MB}MB limit",
        )

    documents_dir = f"data/{chatbot_id}/documents"
    os.makedirs(documents_dir, exist_ok=True)

    file_path = os.path.join(documents_dir, filename)
    with open(file_path, "wb") as f:
        f.write(contents)

    # Extract text
    text = ""
    if file_extension == ".pdf":
        text = TextProcessor.extract_text_from_pdf(contents)
    elif file_extension == ".docx":
        text = TextProcessor.extract_text_from_docx(contents)
    elif file_extension == ".txt":
        text = contents.decode("utf-8")

    chunks = TextProcessor.chunk_text(text)

    index_name = cm.chatbots[chatbot_id]["index_name"]

    try:
        service_manager = get_service_manager(index_name)

        embeddings_response = service_manager.co.embed(
            texts=chunks,
            model="embed-english-v3.0",
            input_type="search_document",
        )
        vectors = embeddings_response.embeddings

        upsert_data = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            upsert_data.append(
                {
                    "id": f"{filename}-{i}",
                    "values": vector,
                    "metadata": {
                        "text": chunk,
                        "source": filename,
                        "chunk_id": i,
                    },
                }
            )

        service_manager.index.upsert(vectors=upsert_data)
        cm.add_file_to_chatbot(chatbot_id, filename)

        return {
            "status": "success",
            "message": f"File {filename} uploaded and processed successfully",
            "chunks": len(chunks),
        }
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing file: {str(e)}",
        )


@router.post("/chatbot/{chatbot_id}/ask")
async def chat_with_bot(
    chatbot_id: str,
    request: QueryRequest,
    current_user: User = Depends(get_current_user_optional),
):
    cm = _get_chatbot_manager()

    if chatbot_id not in cm.chatbots:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chatbot {chatbot_id} not found",
        )

    chatbot_info = cm.chatbots[chatbot_id]
    is_public_chatbot = chatbot_info.get("is_public", False)

    if not is_public_chatbot:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required for this chatbot",
            )
        if not (current_user.is_host or current_user.username == Config.HOST_USERNAME):
            if chatbot_info.get("user_id") != current_user.username:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to access this chatbot",
                )

    try:
        index_name = cm.chatbots[chatbot_id]["index_name"]
        service_manager = get_service_manager(index_name)

        query_embedding = service_manager.co.embed(
            texts=[request.query],
            model="embed-english-v3.0",
            input_type="search_query",
        ).embeddings[0]

        search_results = service_manager.index.query(
            vector=query_embedding, top_k=3, include_metadata=True
        )

        contexts = [match.metadata["text"] for match in search_results.matches]

        chat_history = cm.get_chat_history(chatbot_id)
        recent_history = chat_history[-3:] if len(chat_history) > 3 else chat_history

        system_prompt = (
            "You are a helpful AI assistant. Using the provided context and chat history, "
            "answer the user's question. If you cannot find the answer in the context, "
            'say "I cannot find the answer in the provided context." '
            "Base your answer on both the context and the conversation history provided."
        )

        history_context = ""
        if recent_history:
            history_context = "\nPrevious conversation:\n"
            for entry in recent_history:
                history_context += (
                    f"User: {entry['query']}\nAssistant: {entry['answer']}\n"
                )

        user_prompt = (
            f"Context: {' '.join(contexts)}\n{history_context}\n\n"
            f"Current Question: {request.query}\n\n"
            "Please provide a clear and concise answer based on both the context "
            "and conversation history above."
        )
        if request.model.lower() == "openai":
            if not Config.OPENAI_API_KEY:
                raise HTTPException(400, "OpenAI API key not configured")

            client = openai.OpenAI(api_key=Config.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=500,
                presence_penalty=0.1,
                frequency_penalty=0.1,
            )
            answer = response.choices[0].message.content

        elif request.model.lower() == "cohere":
            if not Config.COHERE_API_KEY:
                raise HTTPException(400, "Cohere API key not configured")

            combined_message = f"{system_prompt}\n\n{user_prompt}"
            response = service_manager.co.chat(
                message=combined_message,
                model="command-a-03-2025",
                temperature=0.7,
                chat_history=[],
                prompt_truncation="AUTO",
            )
            answer = response.text

        elif request.model.lower() == "togetherai":
            if not Config.TOGETHERAI_API_KEY:
                raise HTTPException(400, "TogetherAI API key not configured")

            async with httpx.AsyncClient() as http_client:
                resp = await http_client.post(
                    "https://api.together.xyz/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {Config.TOGETHERAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "mistralai/Mistral-7B-Instruct-v0.2",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.7,
                        "max_tokens": 500,
                    },
                    timeout=30.0,
                )
            if resp.status_code != 200:
                raise HTTPException(500, f"TogetherAI API error: {resp.text}")
            answer = resp.json()["choices"][0]["message"]["content"]

        else:
            raise HTTPException(400, f"Unsupported model: {request.model}")

        if current_user:
            cm.save_chat_history(chatbot_id, request.query, answer)

        return JSONResponse(
            content={
                "status": "success",
                "response": answer,
                "context_used": contexts,
                "model_used": request.model,
            }
        )

    except HTTPException:
        raise
    except Exception as model_error:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error generating response with {request.model}: {str(model_error)}",
        )


@router.get("/chatbot/{chatbot_id}/history")
async def get_chat_history(
    chatbot_id: str, current_user: User = Depends(get_current_active_user)
):
    cm = _get_chatbot_manager()
    _check_chatbot_access(chatbot_id, current_user, cm)

    try:
        history = cm.get_chat_history(chatbot_id)
        return {"history": history}
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))


@router.get("/public-chatbots")
async def list_public_chatbots():
    cm = _get_chatbot_manager()
    chatbots = cm.get_public_chatbots()
    return {"chatbots": chatbots}


@router.post("/chatbot/{chatbot_id}/update-visibility")
async def update_chatbot_visibility(
    chatbot_id: str,
    request: Request,
    current_user: User = Depends(get_current_active_user),
):
    cm = _get_chatbot_manager()

    if chatbot_id not in cm.chatbots:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chatbot {chatbot_id} not found",
        )

    if not (current_user.is_host or current_user.username == Config.HOST_USERNAME):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can change chatbot visibility",
        )

    data = await request.json()
    is_public = data.get("is_public", False)
    cm.chatbots[chatbot_id]["is_public"] = is_public
    cm.save_chatbots()

    return {
        "status": "success",
        "message": f"Chatbot {chatbot_id} visibility updated",
        "is_public": is_public,
    }
