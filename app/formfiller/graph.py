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
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
import redis
import traceback
import asyncio
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


# Create a checkpointer for persistence
checkpointer = MemorySaver()

# for local development for now
# install local redis using docker docker run -d --name redis -p 6379:6379 redis
# DB_URI = "redis://localhost:6379"
# with RedisSaver.from_conn_string(DB_URI) as checkpointer:
#     checkpointer.setup()

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
 
    messages = []
    #import pdb; pdb.set_trace()
    # Add conversation history for context if available
    if state.get("conversation_history"):
        history_context = "Previous conversation:\n"
        for entry in state["conversation_history"]:
            role = "User" if entry["role"] == "user" else "Assistant"
            history_context += f"{role}: {entry['content']}\n"
        messages.append(SystemMessage(content=history_context))

    # Get response from the LLM
    response = await analyze_form_executor.ainvoke({"message": user_message, "formFields": form_fields })
    
    # import pdb; pdb.set_trace()
    output_text = (
        response.get("output") if isinstance(response, dict) else None
    ) or str(response)
    
    cleaned_str = output_text.replace('True', 'true').replace('False', 'false')
    
    if not cleaned_str.strip():
        raise ValueError("Input string to json.loads() is empty.")

    form_data = json.loads(cleaned_str)

    # Update conversation history
    history = state.get("conversation_history", [])
    history.append({"role": "user", "content": user_message})
    
    # Determine next steps based on missing fields
    missing_fields = form_data.get("missing_fields", [])
    filled_fields = form_data.get("filled_fields", {})    
    status = "completed" if not missing_fields else "awaiting_info"
    current_field = missing_fields[0] if missing_fields else None
    
    # Generate response based on analysis
    if status == "completed":
        response_text = "Great! I've filled out the entire form based on your information."
    else:
        response_text = form_data.get("message", "")

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
    current_field_details = state["current_field"]
    #form_fields = state["form_fields"]
    filled_fields = state["filled_fields"].copy()
    missing_fields = state["missing_fields"].copy()
    
    #import pdb; pdb.set_trace()
    #cache_checkpointer_to_file()
    # Get the current field details
    # current_field_id = current_field["data_id"] if isinstance(current_field, dict) else current_field
    # current_field_details = next((f for f in current_field if f["data_id"] == current_field_id), None)    
    
    if not current_field_details:
        return state
    #import pdb; pdb.set_trace()
    # Get response from the LLM
    response = await process_field_executor.ainvoke(
        {
            "current_field_details": current_field_details,
            "data_id": current_field_details["data_id"],
            "field_label": current_field_details["field_label"],
            "field_type": current_field_details["field_type"],
            "is_required": current_field_details["is_required"],
            "validation_message": current_field_details.get("validation_message", ""),
            "options": current_field_details.get("options", []),
            "user_message": state["user_message"]
        }
    )

    output_text = (response.get("output") if isinstance(response, dict) else None) or str(response)

    print(output_text)
    #import pdb; pdb.set_trace()
    # If output is a string and not JSON, treat as validation message
    try:
        import ast
        cleaned_str = ast.literal_eval(output_text)
        form_data = json.loads(cleaned_str['text'])
    except Exception:
        form_data = {"status": "failed", "message": "Invalid input format."}

    history = state["conversation_history"]
    history.append({"role": "user", "content": user_message})

    current_field_details_updated = form_data['current_field_details']
    if isinstance(current_field_details_updated, dict) and form_data['success']:
        state["filled_fields"].append(current_field_details_updated)
        state["missing_fields"] = [f for f in state["missing_fields"] if f["data_id"] != current_field_details_updated['data_id']]
        state["current_field"] = state["missing_fields"][0] if state["missing_fields"] else None
        state["next_field"] = state["current_field"] if state["current_field"] else None
        
        if not state["missing_fields"]:
            state["status"] = "completed"
        else:
            state["status"] = "awaiting_info"

        state["response"] = ""

        return {
            "response": state["response"],
            "status": state["status"],
            "filled_fields": state["filled_fields"],
            "missing_fields": state["missing_fields"],
            "current_field": state["current_field"]
        }
    # else:
    #     # Not success, keep asking for correct info
    #     response_text = form_data.get("message", "Please provide the correct information for the field.")
    #     status = "awaiting_info"
    #     history.append({"role": "assistant", "content": response_text})
    #     return {
    #         **state,
    #         "conversation_history": history,
    #         "status": status,
    #         "response": response_text
    #     }

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

    try:
        result = await compiled_graph.ainvoke(initial_state, config)
 
        return {
            "thread_id": thread_id,
            "response": result["response"],
            "status": result["status"],
            "filled_fields": result["filled_fields"],
            "missing_fields": result["missing_fields"],
            "current_field": result["current_field"],
            "conversation_history": result["conversation_history"]
        }
    except Exception as e:
            print("LangGraph Error:", e)
            traceback.print_exc()
            return {"error": str(e), "traceback": traceback.format_exc()}
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
    compiled_graph.update_state(config, {"user_message": user_message})
    
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
