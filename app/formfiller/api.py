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
    field_label: Optional[str] = None
    field_type: Optional[str] = None
    field_value: Optional[str] = ""
    is_required: Optional[bool] = False
    options: Optional[List[str]] = None

class StartFormRequest(BaseModel):
    """Request model for starting a new form-filling session"""
    message: str
    formFields: List[FormFieldModel] = Field(..., min_items=1)

class ContinueFormRequest(BaseModel):
    """Request model for continuing an existing form-filling session"""
    thread_id: str
    message: str

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
        request: Contains message and formFields to fill
        
    Returns:
        Initial agent response and session information
    """
    try:
        # Convert Pydantic models to dictionaries and map field names
        form_fields = []
        for field in request.formFields:
            field_dict = field.dict(exclude_none=True)
            # Map to the format expected by the backend with defaults for optional fields
            form_fields.append({
                "field_id": field_dict["data_id"],
                "label": field_dict.get("field_label", ""),
                "type": field_dict.get("field_type", "text"),
                "value": field_dict.get("field_value", ""),
                "required": field_dict.get("is_required", False),
                "options": field_dict.get("options", None)
            })
        
        result = await start_form_filling(request.message, form_fields)
        
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
        request: Contains thread ID and message
        
    Returns:
        Updated agent response and session information
    """
    try:
        result = await continue_form_filling(request.thread_id, request.message)
        
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
