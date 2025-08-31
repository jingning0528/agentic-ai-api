"""
Main FastAPI application with POST endpoint backbone
"""

import os
import logging
from typing import Optional, List
from fastapi import FastAPI, HTTPException
#from app.api import router as api_router
from app.formfiller import router as formfiller_router  # Updated import
from pydantic import BaseModel
from dotenv import load_dotenv
from app.llm.workflow import app_workflow, get_conversation, list_conversations, delete_conversation
from uuid import uuid4
from app.llm.models import StartRequest, GraphResponse, ResumeRequest
from app.llm.graph import graph

# Import agentic AI router conditionally
try:
    from app.agenticai.endpoints import router as agenticai_router
    AGENTICAI_AVAILABLE = True
except ImportError as e:
    print(f"Agentic AI not available: {e}")
    agenticai_router = None
    AGENTICAI_AVAILABLE = False

# Minimal request/response models for FastAPI endpoint typing
class RequestModel(BaseModel):
    message: str
    formFields: Optional[List[dict]] = None
    conversation_id: Optional[str] = None

class ResponseModel(BaseModel):
    status: str
    message: str
    formFields: Optional[List[dict]] = None
    conversation_id: str

# Models for memory endpoints
class ConversationItem(BaseModel):
    role: str
    content: str

class ConversationHistory(BaseModel):
    conversation_id: str
    history: List[ConversationItem]

class ConversationListResponse(BaseModel):
    conversations: List[str]

load_dotenv()

# Configure logging (honor LOG_LEVEL env var; default INFO)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
_level = getattr(logging, LOG_LEVEL, logging.INFO)

logger = logging.getLogger(__name__)
logger.setLevel(_level)

# Ensure at least one handler is configured so logs are emitted when launched via uv/uvicorn
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


# Initialize FastAPI app
app = FastAPI(
    title="NR Agentic AI API",
    description=(
        "An agentic AI API built with FastAPI, LangGraph, and LangChain. "
        "Features intelligent form filling and multi-agent workflows."
    ),
    version="0.1.0"
)

# Include agentic AI router if available
if AGENTICAI_AVAILABLE and agenticai_router:
    app.include_router(agenticai_router)
    print("✅ Agentic AI endpoints loaded successfully")
else:
    print("⚠️ Agentic AI endpoints not available")

# Log app init once
logger.info("NR Agentic AI API initialized (log level=%s)", LOG_LEVEL)

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "NR Agentic AI API is running"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "NR Agentic AI API"}


@app.post("/api/process", response_model=ResponseModel)
async def process_request(request: RequestModel):
    """
    Main POST endpoint to receive and process requests
    
    This endpoint uses the orchestrator agent to process incoming requests.
    Supports conversation continuity via conversation_id.
    """
    try:
        # Log the incoming request (INFO so it appears by default)
        logger.info(
            "Processing message len=%d; formFields=%s",
            len(request.message) if request.message else 0,
            "yes" if request.formFields else "no",
        )
        if request.formFields:
            logger.info("Form fields count: %d", len(request.formFields))
        
        # Generate a thread_id for this request
        thread_id = str(uuid4())
        
        # Prepare initial state
        initial_state = {
            "message": request.message, 
            "formFields": request.formFields or [],
            "conversation_id": request.conversation_id
        }
        
        # Use the LangGraph workflow (async) to process the request with proper checkpointing
        workflow_result = await app_workflow.ainvoke(
            initial_state,
            config={
                "thread_id": thread_id,
                "checkpoint_id": request.conversation_id or thread_id
            }
        )

        response = workflow_result["response"]
        # response is a dict with keys 'message', 'formFields', and 'conversation_id'
        return ResponseModel(
            status="success",
            message=response.get("message", ""),
            formFields=response.get("formFields", None),
            conversation_id=response.get("conversation_id", "")
        )
        
    except Exception as e:
        logger.exception("Unhandled error in /api/process: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing request: {str(e)}"
        ) from e

# Memory endpoints
@app.get("/api/memory/{conversation_id}", response_model=ConversationHistory)
async def get_conversation_history(conversation_id: str):
    """
    Retrieve conversation history for a specific conversation ID
    """
    history = get_conversation(conversation_id)
    if not history:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return ConversationHistory(conversation_id=conversation_id, history=history)

@app.delete("/api/memory/{conversation_id}")
async def delete_conversation_history(conversation_id: str):
    """
    Delete conversation history for a specific conversation ID
    """
    success = delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {"status": "success", "message": f"Conversation {conversation_id} deleted"}

@app.get("/api/memory", response_model=ConversationListResponse)
async def list_all_conversations():
    """
    List all available conversation IDs
    """
    conversations = list_conversations()
    return ConversationListResponse(conversations=conversations)

# Include API router
app.include_router(formfiller_router, prefix="/api/v1")  # Updated router inclusion

def run_graph_and_response(input_state, config):
    result = graph.invoke(input_state, config)
    state = graph.get_state(config)
    next_nodes = state.next
    thread_id = config["configurable"]["thread_id"]
    if next_nodes and "human_feedback" in next_nodes:
        run_status = "user_feedback"
    else:
        run_status = "finished"
    return GraphResponse(
        thread_id=thread_id,
        run_status=run_status,
        assistant_response=result["assistant_response"]
    )

@app.post("/graph/start", response_model=GraphResponse)
def start_graph(request: StartRequest):
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {"human_request": request.human_request}

    return run_graph_and_response(initial_state, config)

@app.post("/graph/resume", response_model=GraphResponse)
def resume_graph(request: ResumeRequest):
    config = {"configurable": {"thread_id": request.thread_id}}
    state = {"status": request.review_action}
    if request.human_comment is not None:
        state["human_comment"] = request.human_comment
    print(f"State to update: {state}")
    graph.update_state(config, state)

    return run_graph_and_response(None, config)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level=LOG_LEVEL.lower())