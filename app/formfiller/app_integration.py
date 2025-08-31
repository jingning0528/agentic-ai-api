"""
API router for form filling functionality
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from uuid import uuid4
from .graph import compiled_graph, start_form_filling, FormField

router = APIRouter(
    prefix="/formfiller",
    tags=["formfiller"],
    responses={404: {"description": "Not found"}},
)

# Request and response models
class FormFillerRequest(BaseModel):
    message: str
    form_fields: List[Dict[str, Any]]
    conversation_id: Optional[str] = None

class FormFillerResponse(BaseModel):
    conversation_id: str
    status: str
    filled_fields: Dict[str, Any]
    missing_fields: List[str]
    current_field: Optional[str] = None
    response: str

@router.post("/start", response_model=FormFillerResponse)
async def start_form_filling_session(request: FormFillerRequest):
    """
    Start a new form filling session or continue an existing one.
    """
    try:
        # Convert the form_fields dictionaries to FormField objects
        form_fields = [FormField(**field) for field in request.form_fields]
        
        # Generate a unique conversation ID if not provided
        conversation_id = request.conversation_id or str(uuid4())
        
        # Start the form filling process
        result = await start_form_filling(request.message, form_fields)
        
        # Prepare and return the response
        return FormFillerResponse(
            conversation_id=conversation_id,
            status=result["status"],
            filled_fields=result["filled_fields"],
            missing_fields=result["missing_fields"],
            current_field=result["current_field"],
            response=result["response"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting form filling session: {str(e)}")

@router.post("/continue", response_model=FormFillerResponse)
async def continue_form_filling(request: FormFillerRequest):
    """
    Continue an existing form filling session with new user input.
    """
    try:
        if not request.conversation_id:
            raise HTTPException(status_code=400, detail="conversation_id is required for continuing a session")
        
        # Configure the graph with the conversation ID
        config = {
            "configurable": {
                "thread_id": request.conversation_id,
                "checkpoint_id": request.conversation_id
            }
        }
        
        # Update the state with the new user message
        graph_state = compiled_graph.get_state(config)
        if not graph_state:
            raise HTTPException(status_code=404, detail=f"No active session found for conversation_id: {request.conversation_id}")
        
        # Resume the graph with the new user message
        result = await compiled_graph.ainvoke({"user_message": request.message}, config)
        
        # Prepare and return the response
        return FormFillerResponse(
            conversation_id=request.conversation_id,
            status=result["status"],
            filled_fields=result["filled_fields"],
            missing_fields=result["missing_fields"],
            current_field=result["current_field"],
            response=result["response"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error continuing form filling session: {str(e)}")