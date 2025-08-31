"""
FastAPI endpoints for the form-filling agent.
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from uuid import UUID
from .graph import FormField, start_form_filling, continue_form_filling

router = APIRouter()

# Request and response models
class FormFieldModel(BaseModel):
    """Pydantic model for form fields"""
    data_id: str
    field_label: str
    field_type: str
    field_value: Optional[str] = ""
    is_required: bool = False
    options: Optional[List[str]] = None

class StartFormRequest(BaseModel):
    """Request model for starting a new form-filling session"""
    user_message: str
    form_fields: List[FormFieldModel] = Field(..., min_items=1)

class ContinueFormRequest(BaseModel):
    """Request model for continuing an existing form-filling session"""
    thread_id: str
    user_message: str

class FormResponse(BaseModel):
    """Response model for form-filling operations"""
    thread_id: str
    response: str
    status: str
    filled_fields: Dict[str, Any] = {}
    missing_fields: List[str] = []

@router.post("/start", response_model=FormResponse)
async def start_session(request: StartFormRequest):
    """
    Start a new form-filling session.
    
    Args:
        request: Contains user message and form fields to fill
        
    Returns:
        Initial agent response and session information
    """
    try:
        # Convert Pydantic models to dictionaries and map field names
        form_fields = []
        for field in request.form_fields:
            field_dict = field.dict()
            # Map to the format expected by the backend
            form_fields.append({
                "field_id": field_dict["data_id"],
                "label": field_dict["field_label"],
                "type": field_dict["field_type"],
                "value": field_dict["field_value"],
                "required": field_dict["is_required"],
                "options": field_dict["options"]
            })
        
        result = await start_form_filling(request.user_message, form_fields)
        
        return FormResponse(
            thread_id=result["thread_id"],
            response=result["response"],
            status=result["status"],
            filled_fields=result["filled_fields"],
            missing_fields=result["missing_fields"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting form session: {str(e)}")

@router.post("/continue", response_model=FormResponse)
async def continue_session(request: ContinueFormRequest):
    """
    Continue an existing form-filling session.
    
    Args:
        request: Contains thread ID and user response
        
    Returns:
        Updated agent response and session information
    """
    try:
        result = await continue_form_filling(request.thread_id, request.user_message)
        
        return FormResponse(
            thread_id=result["thread_id"],
            response=result["response"],
            status=result["status"],
            filled_fields=result["filled_fields"],
            missing_fields=result["missing_fields"]
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error continuing form session: {str(e)}")
