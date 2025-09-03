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
class StartFormRequest(BaseModel):
    """Request model for starting a new form-filling session"""
    message: str
    formFields: Optional[List[dict]] = None

class ContinueFormRequest(BaseModel):
    """Request model for continuing an existing form-filling session"""
    thread_id: str
    message: str

class FormResponse(BaseModel):
    """Response model for form-filling operations"""
    thread_id: str
    response: str
    status: str
    filled_fields: Optional[List[dict]] = None
    missing_fields: Optional[List[dict]] = None
    current_field: Optional[dict] = None
    next_field: Optional[dict] = None
    conversation_history: Optional[List[dict]] = None

@router.post("/start", response_model=FormResponse)
async def start_session(request: StartFormRequest):
    """
    Start a new form-filling session.
    
    Args:
        request: Contains message and formFields to fill
        
    Returns:
        Initial agent response and session information
    """
    try:
        result = await start_form_filling(request.message, request.formFields)

        # Ensure filled_fields is a list of dicts
        raw_filled = result.get("filled_fields", [])
        if isinstance(raw_filled, dict):
            filled_fields = [
                {"data_id": k, "field_value": v} for k, v in raw_filled.items()
            ]
        elif isinstance(raw_filled, list):
            filled_fields = raw_filled
        else:
            filled_fields = []

        # Ensure missing_fields is a list of dicts
        raw_missing = result.get("missing_fields", [])
        if raw_missing and isinstance(raw_missing[0], str):
            missing_fields = [
                {"data_id": m, "field_label": "", "field_type": "", "field_value": "", "is_required": True, "validation_message": ""}
                for m in raw_missing
            ]
        elif isinstance(raw_missing, list):
            missing_fields = raw_missing
        else:
            missing_fields = []
        import pdb; pdb.set_trace()
        return FormResponse(
            thread_id=result["thread_id"],
            response=result["response"],
            status=result["status"],
            filled_fields=filled_fields,
            missing_fields=missing_fields,
            current_field=result["current_field"],
            next_field=result["current_field"],
            conversation_history=result["conversation_history"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting form session: {str(e)}")

@router.post("/continue", response_model=FormResponse)
async def continue_session(request: ContinueFormRequest):
    """
    Continue an existing form-filling session.
    
    Args:
        request: Contains thread ID and message
        
    Returns:
        Updated agent response and session information
    """
    #read_checkpointer_from_file()
    try:
        result = await continue_form_filling(request.thread_id, request.message)
        
        # Ensure filled_fields is a list of dicts
        raw_filled = result.get("filled_fields", [])
        if isinstance(raw_filled, dict):
            filled_fields = [
                {"data_id": k, "field_value": v} for k, v in raw_filled.items()
            ]
        elif isinstance(raw_filled, list):
            filled_fields = raw_filled
        else:
            filled_fields = []

        # Ensure missing_fields is a list of dicts
        raw_missing = result.get("missing_fields", [])
        if raw_missing and isinstance(raw_missing[0], str):
            missing_fields = [
                {"data_id": m, "field_label": "", "field_type": "", "field_value": "", "is_required": True, "validation_message": ""}
                for m in raw_missing
            ]
        elif isinstance(raw_missing, list):
            missing_fields = raw_missing
        else:
            missing_fields = []

        return FormResponse(
            thread_id=result["thread_id"],
            response=result["response"],
            status=result["status"],
            filled_fields=filled_fields,
            missing_fields=missing_fields
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error continuing form session: {str(e)}")

@router.get("/schema")
def get_schema():
    """Get the expected schema for API requests"""
    return {
        "start_request": {
            "message": "string - the user's initial query",
            "formFields": [
                {
                    "data_id": "string - unique identifier for this field",
                    "field_label": "string - human-readable label for the field",
                    "field_type": "string - type of input (text, radio, select, etc.)",
                    "field_value": "string - initial value (empty string by default)",
                    "is_required": "boolean - whether this field must be filled",
                    "options": "array of strings - possible values for dropdown/radio fields (optional)"
                }
            ]
        },
        "continue_request": {
            "thread_id": "string - the session ID returned from start request",
            "message": "string - the user's response to previous agent message"
        },
        "example": {
            "message": "I need to apply for a fee exemption",
            "formFields": [
                {
                    "data_id": "V1IsEligibleForFeeExemption",
                    "field_label": "Are you eligible for fee exemption?",
                    "field_type": "radio",
                    "field_value": "",
                    "is_required": True,
                    "options": ["Yes", "No"]
                }
            ]
        }
    }