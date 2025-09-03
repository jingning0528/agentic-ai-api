"""
Form-filling agent based on LangGraph for automatically populating web forms.
This module defines the core agent logic and workflow for auto-filling forms
based on user input and interactive form field completion.
"""
import os
from typing import Dict, List, Any, Optional, TypedDict, Literal
from uuid import uuid4
from dotenv import load_dotenv
from .llm_client import llm as model
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import AzureChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.redis import RedisSaver
import redis

from app.formfiller.agents import analyze_form_executor, process_field_executor
import json
import re
import logging

# Load environment variables
load_dotenv()

# Initialize the model
model = AzureChatOpenAI(
    azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
    azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME"),
    openai_api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
)

#redis_client = redis.Redis(host="localhost", port=6379, db=0)

# Create a checkpointer for persistence
checkpointer = MemorySaver()

# for local development for now
# install local redis using docker docker run -d --name redis -p 6379:6379 redis
#checkpointer = RedisSaver(redis_url="redis://localhost:6379/0")


# Define form field structure
class FormField(TypedDict):
    """Structure for individual form fields"""
    field_id: str  # Corresponds to data_id in the API model
    label: str  # Corresponds to field_label in the API model
    type: str  # input, select, radio, checkbox, textarea, etc. - Corresponds to field_type
    value: Optional[str]  # Corresponds to field_value in the API model
    required: bool  # Corresponds to is_required in the API model
    options: Optional[List[str]]  # For dropdown, radio, etc. - Same in API model
    description: Optional[str]  # Help text - Not in API model but preserved
    validation: Optional[str]  # Validation rules - Not in API model but preserved

# Define the state structure for our graph
class FormFillerState(TypedDict):
    """State for the form-filling workflow"""
    user_message: str
    form_fields: list
    filled_fields: dict[str, Any]
    missing_fields: list[str]
    current_field: Optional[List[dict]] = None
    #next_field: Optional[List[dict]] = None
    conversation_history: List[Dict[str, Any]]
    status: Literal["in_progress", "awaiting_info", "completed"]
    response: str
    thread_id: str

# Node 1: Initial form analysis: orchestrator node
async def analyze_form(state: FormFillerState) -> FormFillerState:
    """
    Analyzes user input and form fields to extract available information and identify missing fields.
    """
    user_message = state["user_message"]
    form_fields = state["form_fields"]
    
    # Create system prompt for form analysis
    system_prompt = """
    You are a form-filling assistant. Analyze the user's message and extract information to fill in form fields.
    For each form field provided, determine:
    1. If the field can be filled based on the user's message
    2. The appropriate value for the field
    3. If additional information is needed
    
    Return a JSON object with filled fields and a list of missing fields.
    """
    
    # Format form fields for the model
    # field_descriptions = []
    
    # # Dynamically handle different field formats
    # for field in form_fields:
    #     # Create a formatted description for each field
    #     try:
    #         # Start with basic field information
    #         field_desc = ""
            
    #         # Add field ID if available
    #         if 'field_id' in field:
    #             field_desc += f"Field ID: {field['field_id']}\n"
    #         elif 'id' in field:
    #             field_desc += f"Field ID: {field['id']}\n"
                
    #         # Add label if available
    #         if 'label' in field:
    #             field_desc += f"Label: {field['label']}\n"
    #         elif 'field_label' in field:
    #             field_desc += f"Label: {field['field_label']}\n"
    #         elif 'fieldLabel' in field:
    #             field_desc += f"Label: {field['fieldLabel']}\n"
                
    #         # Add type if available
    #         if 'type' in field:
    #             field_desc += f"Type: {field['type']}\n"
    #         elif 'field_type' in field:
    #             field_desc += f"Type: {field['field_type']}\n"
    #         elif 'fieldType' in field:
    #             field_desc += f"Type: {field['fieldType']}\n"
            
    #         # Add description if available
    #         if field.get('description'):
    #             field_desc += f"Description: {field['description']}\n"
                
    #         # Add options if available
    #         if field.get('options') and isinstance(field['options'], list):
    #             field_desc += f"Options: {', '.join(str(opt) for opt in field['options'])}\n"
                
    #         # Add validation if available
    #         if field.get('validation'):
    #             field_desc += f"Validation: {field['validation']}\n"
                
    #         # Add required status
    #         is_required = field.get('required', field.get('is_required', field.get('isRequired', False)))
    #         field_desc += f"Required: {'Yes' if is_required else 'No'}\n"
            
    #         # Add current value if available
    #         if 'value' in field and field['value']:
    #             field_desc += f"Current value: {field['value']}\n"
    #         elif 'field_value' in field and field['field_value']:
    #             field_desc += f"Current value: {field['field_value']}\n"
    #         elif 'fieldValue' in field and field['fieldValue']:
    #             field_desc += f"Current value: {field['fieldValue']}\n"
                
    #         field_descriptions.append(field_desc)
    #     except Exception as e:
    #         import logging
    #         logging.getLogger(__name__).error(f"Error formatting field {field}: {str(e)}")
    #         # Add a basic description for fields that couldn't be properly formatted
    #         field_descriptions.append(f"Field: {str(field)}\n")
    
    # all_field_descriptions = "\n\n".join(field_descriptions)
    
    # messages = [
    #     SystemMessage(content=system_prompt),
    #     HumanMessage(content=f"User message: {user_message}\n\nForm fields:\n{all_field_descriptions}")
    # ]
    messages = []
    # Add conversation history for context if available
    if state.get("conversation_history"):
        history_context = "Previous conversation:\n"
        for entry in state["conversation_history"]:
            role = "User" if entry["role"] == "user" else "Assistant"
            history_context += f"{role}: {entry['content']}\n"
        messages.append(SystemMessage(content=history_context))
    

    
    # Get response from the LLM
    #response = await model.ainvoke(messages)
    response = await analyze_form_executor.ainvoke({"message": state["user_message"], "formFields": state["form_fields"] })
    
    # import pdb; pdb.set_trace()
    output_text = (
        response.get("output") if isinstance(response, dict) else None
    ) or str(response)
    
    cleaned_str = output_text.replace('True', 'true').replace('False', 'false')
    
    form_data = json.loads(cleaned_str)
    #cache_checkpointer_to_file()
    # Update conversation history
    history = state.get("conversation_history", [])
    history.append({"role": "user", "content": user_message})
    
    # Determine next steps based on missing fields
    missing_fields = form_data.get("missing_fields", [])
    filled_fields = form_data.get("filled_fields", {})
    #formFields = form_data.get("formFields", [])
    
    status = "completed" if not missing_fields else "awaiting_info"
    current_field = missing_fields[0] if missing_fields else None
    
    # Generate response based on analysis
    if status == "completed":
        response_text = "Great! I've filled out the entire form based on your information."
    else:
        # Find the current field details
        #current_field_details = next((f for f in form_fields if f["data_id"] == current_field), {})
        #field_label = current_field_details.get("label", current_field)

        response_text = form_data.get("message", "")
        # if current_field_details.get("description"):
        #     response_text += f" ({current_field_details['description']})"
        # if current_field_details.get("options"):
        #     options_text = ", ".join(current_field_details["options"])
        #     response_text += f" Options are: {options_text}"
    
    history.append({"role": "assistant", "content": response_text})
    
    return {
        **state,
        "filled_fields": filled_fields,
        "missing_fields": missing_fields,
        "current_field": current_field,
        "conversation_history": history,
        "status": status,
        "response": response_text,

    }

# Node 2: Process user input for specific field
async def process_field_input(state: FormFillerState) -> FormFillerState:
    """
    Processes user input for a specific requested field.
    """
    # read_checkpointer_from_file()
    user_message = state["user_message"]
    current_field = state["current_field"]
    form_fields = state["form_fields"]
    filled_fields = state["filled_fields"].copy()
    missing_fields = state["missing_fields"].copy()
    
    # import pdb; pdb.set_trace()
    #cache_checkpointer_to_file()
    # Get the current field details
    current_field_id = current_field["data_id"] if isinstance(current_field, dict) else current_field
    current_field_details = next((f for f in form_fields if f["data_id"] == current_field_id), None)    
    
    if not current_field_details:
        return state
    
    # Get response from the LLM
    response = await process_field_executor.ainvoke(
        {
            "user_message": state["user_message"],
            "current_field_details": current_field_details,
            "validation_message": current_field_details.get("validation_message", "")
        }
    )

    output_text = (response.get("output") if isinstance(response, dict) else None) or str(response)
    # If output is a string and not JSON, treat as validation message
    try:
        cleaned_str = output_text.replace('True', 'true').replace('False', 'false')
        form_data = json.loads(cleaned_str)
    except Exception:
        # output_text is not JSON, treat as validation message
        current_field_details["validation_message"] = output_text
        response_text = output_text
        status = "failed"
        history = state["conversation_history"]
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": response_text})
        return {
            **state,
            "current_field": current_field,
            "conversation_history": history,
            "status": status,
            "response": response_text
        }

    history = state["conversation_history"]
    history.append({"role": "user", "content": user_message})

    # If success, update and return in requested format
    if form_data.get('status') == "success":
        # Ensure filled_fields is a list of dicts
        raw_filled = form_data.get("filled_fields", [])
        if isinstance(raw_filled, dict):
            filled_fields = [
                {"data_id": k, "field_value": v} for k, v in raw_filled.items()
            ]
        elif isinstance(raw_filled, list):
            filled_fields = raw_filled
        else:
            filled_fields = []

        # Ensure missing_fields is a list of dicts
        raw_missing = form_data.get("missing_fields", [])
        if raw_missing and isinstance(raw_missing[0], str):
            # If missing_fields is a list of strings, convert to dicts with default keys
            missing_fields = [
                {"data_id": m, "field_label": "", "field_type": "", "field_value": "", "is_required": True, "validation_message": ""}
                for m in raw_missing
            ]
        elif isinstance(raw_missing, list):
            missing_fields = raw_missing
        else:
            missing_fields = []

        response_text = form_data.get("message", "")
        status = form_data.get("status", "awaiting_info")
        thread_id = state.get("thread_id", "")
        history.append({"role": "assistant", "content": response_text})

        # update state values with the current state
        state["thread_id"] = thread_id
        state["conversation_history"] = history
        state["status"] = status
        state["response"] = response_text
        state["filled_fields"] = filled_fields
        state["missing_fields"] = missing_fields

        return {
            "thread_id": thread_id,
            "response": response_text,
            "status": status,
            "filled_fields": filled_fields,
            "missing_fields": missing_fields
        }
    else:
        # Not success, keep asking for correct info
        response_text = form_data.get("message", "Please provide the correct information for the field.")
        status = "awaiting_info"
        history.append({"role": "assistant", "content": response_text})
        return {
            **state,
            "conversation_history": history,
            "status": status,
            "response": response_text
        }

# Conditional edge function
def route_next_step(state: FormFillerState) -> str:
    """
    Determines the next step in the workflow based on the current state.
    """
    if state["status"] == "completed":
        return END  # Changed from "end" to END constant
    elif state["status"] == "awaiting_info":
        return "human_input" 
    else:
        return "analyze_form"

# Human in the loop node (placeholder)
async def human_input(state: FormFillerState) -> FormFillerState:
    """
    Placeholder node for receiving human input. In a real system, this would be an interrupt
    point where the system waits for user input.
    """
    return state

# Create the graph
form_filler_graph = StateGraph(FormFillerState)

# Add nodes
form_filler_graph.add_node("analyze_form", analyze_form)
form_filler_graph.add_node("process_field_input", process_field_input)
form_filler_graph.add_node("human_input", human_input)

# Add edges
form_filler_graph.add_edge(START, "analyze_form")
form_filler_graph.add_conditional_edges("analyze_form", route_next_step)
form_filler_graph.add_edge("human_input", "process_field_input")
form_filler_graph.add_conditional_edges("process_field_input", route_next_step)
# Remove this line: form_filler_graph.add_edge("end", END)

# Compile the graph with checkpointing and human-in-the-loop support
compiled_graph = form_filler_graph.compile(
    checkpointer=checkpointer,
    interrupt_before=["human_input"]
)

# Helper function to initialize the form-filling process
async def start_form_filling(user_message: str, form_fields: list) -> Dict[str, Any]:
    """
    Initializes a new form-filling session.
    
    Args:
        user_message: The initial user message
        form_fields: List of form fields to fill
        
    Returns:
        Initial state and response information
    """
    thread_id = str(uuid4())
    
    initial_state = {
        "user_message": user_message,
        "form_fields": form_fields,
        "filled_fields": {},
        "missing_fields": [],
        "current_field": None,
        #"next_field": None,
        "conversation_history": [],
        "status": "in_progress",
        "response": "",
        "thread_id": thread_id
    }
    
    config = {"configurable": {"thread_id": thread_id}}
    
    result = await compiled_graph.ainvoke(initial_state, config)
    # import pdb; pdb.set_trace()
    return {
        "thread_id": thread_id,
        "response": result["response"],
        "status": result["status"],
        "filled_fields": result["filled_fields"],
        "missing_fields": result["missing_fields"],
        "current_field": result["current_field"]
    }

# Helper function to continue the form-filling process
async def continue_form_filling(thread_id: str, user_message: str) -> Dict[str, Any]:
    """
    Continues an existing form-filling session.
    
    Args:
        thread_id: The conversation thread ID
        user_message: The user's response to the previous question
        
    Returns:
        Updated state and response information
    """
    config = {"configurable": {"thread_id": thread_id}}
    
    # Get current state
    state = compiled_graph.get_state(config)
    
    if not state:
        raise ValueError(f"No session found for thread_id {thread_id}")
    
    # Update state with new user message
    compiled_graph.update_state(config, {"message": user_message})
    
    # Continue graph execution
    result = await compiled_graph.ainvoke(None, config)
    
    # import pdb; pdb.set_trace()
    # compiled_graph.update_state with the current state
    compiled_graph.update_state(config, state)    

    return {
        "thread_id": thread_id,
        "response": result["response"],
        "status": result["status"],
        "filled_fields": result["filled_fields"],
        "missing_fields": result["missing_fields"],
        "current_field": result["current_field"],
        #"next_field": result["next_field"]
    }
