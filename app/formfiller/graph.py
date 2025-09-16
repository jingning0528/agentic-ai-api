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
import ast

from app.llm.tools.ai_search_tool import ai_search_tool

# simple search function (you could plug in SerpAPI, Tavily, Bing, etc.)
def search_tool(query: str) -> str:
        return ai_search_tool(query)
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
class FormFillerState(TypedDict, total=False):
    """State for the form-filling workflow"""
    user_message: str  # required
    form_fields: list  # optional
    filled_fields: dict[str, Any]  # optional
    missing_fields: list[str]  # optional
    current_field: Optional[List[dict]]  # optional
    #next_field: Optional[List[dict]]  # optional
    conversation_history: List[Dict[str, Any]]  # optional
    status: Literal["in_progress", "awaiting_info", "completed"]  # optional
    response_message: str  # optional
    thread_id: str  # optional

def extract_json_from_output(output: str):
    # Clean up formatting
    output = output.strip().strip("`").strip()

    # Remove "Final Answer:" prefix if present
    if output.startswith("Final Answer:"):
        output = output.replace("Final Answer:", "", 1).strip()

    # Try to extract the JSON block using regex
    match = re.search(r"({.*})", output, re.DOTALL)
    if not match:
        return {
            "error": "Agent failed to complete analysis. No valid JSON found.",
            "raw_output": output
        }

    json_str = match.group(1).strip()

    # Try parsing as real JSON
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass  # Try next method

    # Try parsing as Python dict (e.g., single quotes)
    try:
        return ast.literal_eval(json_str)
    except Exception as e:
        return {
            "error": "Failed to parse output as JSON or Python dict.",
            "exception": str(e),
            "raw_output": json_str
        }

# Node 1: Initial form analysis: orchestrator node
async def analyze_form(state: FormFillerState) -> FormFillerState:
    """
    Orchestrator agent: analyzes user input and form fields, identifies missing fields, and routes to process_field_input if needed.
    """
    # Initialize optional fields if not present
    user_message = state["user_message"]
    form_fields = state.get("form_fields", [])
    filled_fields = state.get("filled_fields", {})
    missing_fields = state.get("missing_fields", [])
    current_field = state.get("current_field")
    conversation_history = state.get("conversation_history", [])
    status = state.get("status", "in_progress")
    response_message = state.get("response_message", "")
    thread_id = state.get("thread_id", str(uuid4()))

    # Add conversation history for context if available
    messages = []
    if conversation_history:
        history_context = "Previous conversation:\n"
        for entry in conversation_history:
            role = "User" if entry["role"] == "user" else "Assistant"
            history_context += f"{role}: {entry['content']}\n"
        messages.append(SystemMessage(content=history_context))

    # get labels for all the fields
    search_results = search_tool(json.dumps({"message": user_message, "formFields": form_fields}))
    # Get response from the LLM
    response = await analyze_form_executor.ainvoke({"message": user_message, "formFields": form_fields, "search_results": search_results})

    cleaned_str = extract_json_from_output(response['text'])

    if isinstance(cleaned_str, str):
        return {
            **state,
            "filled_fields": {},
            "missing_fields": [],
            "current_field": None,
            "conversation_history": conversation_history,
            "status": "awaiting_info",
            "response_message": cleaned_str,
            "thread_id": thread_id,
        }

    # Update conversation history
    history = conversation_history.copy()
    history.append({"role": "user", "content": user_message})

    # Determine next steps based on missing fields
    missing_fields = cleaned_str.get("missing_fields", [])
    filled_fields = cleaned_str.get("filled_fields", {})
    status = "completed" if not missing_fields else "awaiting_info"
    current_field = missing_fields[0] if missing_fields else None

    # Generate response based on analysis
    if status == "completed" and filled_fields:
        response_message = "Great! I've filled out the entire form based on your information."
    else:
        response_message = cleaned_str.get("message", "")

    history.append({"role": "assistant", "content": response_message})

    # If there are missing fields, route to process_field_input
    if missing_fields:
        # Call process_field_input directly
        next_state = {
            **state,
            "filled_fields": filled_fields,
            "form_fields": form_fields,
            "missing_fields": missing_fields,
            "current_field": current_field,
            "conversation_history": history,
            "status": "awaiting_info",
            "response_message": response_message,
            "thread_id": thread_id,
        }
        return await process_field_input(next_state)

    return {
        **state,
        "filled_fields": filled_fields,
        "form_fields": form_fields,
        "missing_fields": missing_fields,
        "current_field": current_field,
        "conversation_history": history,
        "status": status,
        "response_message": response_message,
        "thread_id": thread_id,
    }

# Node 2: Process user input for specific field
async def process_field_input(state: FormFillerState) -> FormFillerState:
    """
    Processes user input for a specific requested field. Loops until all fields are filled.
    """
    user_message = state["user_message"]
    filled_fields = state.get("filled_fields", {})
    form_fields = state.get("form_fields", [])
    missing_fields = state.get("missing_fields", [])
    conversation_history = state.get("conversation_history", [])
    current_field = state.get("current_field")
    thread_id = state.get("thread_id", str(uuid4()))
    response_message = state.get("response_message", "")

    # If no current_field or missing_fields, return state
    if not current_field or not missing_fields:
        user_message = state["user_message"]
        filled_fields = state.get("filled_fields", {})
        missing_fields = state.get("missing_fields", [])
        conversation_history = state.get("conversation_history", [])
        current_field = state.get("current_field")
        thread_id = state.get("thread_id", str(uuid4()))

        # If no current_field or missing_fields, return state
        if not current_field or not missing_fields:
            return {
                **state,
                "status": "completed" if not missing_fields else "awaiting_info",
                "thread_id": thread_id,
            }

        # Always work on the current_field (assume it's a dict or list of dicts)
        if isinstance(current_field, list):
            field = current_field[0]
        else:
            field = current_field

        response = await process_field_executor.ainvoke(
            {
                "current_field_details": field,
                "data_id": field.get("data_id"),
                "field_label": field.get("field_label"),
                "field_type": field.get("field_type"),
                "is_required": field.get("is_required"),
                "validation_message": field.get("validation_message", ""),
                "options": field.get("options", []),
                "user_message": user_message
            }
        )

        output_text = (response.get("output") if isinstance(response, dict) else None) or str(response)

        try:
            cleaned_str = ast.literal_eval(output_text)
            form_data = json.loads(cleaned_str['text'])
        except Exception:
            form_data = {"status": "failed", "message": "Invalid input format."}

        history = conversation_history.copy()
        history.append({"role": "user", "content": user_message})

        current_field_details_updated = form_data.get('current_field_details')
        success = form_data.get('success', False)
        if isinstance(current_field_details_updated, dict) and success:
            # Update filled_fields (dict)
            filled_fields = filled_fields.copy() if filled_fields else {}
            filled_fields[current_field_details_updated['data_id']] = current_field_details_updated
            # Remove from missing_fields
            missing_fields = [f for f in missing_fields if (f.get('data_id') if isinstance(f, dict) else f) != current_field_details_updated['data_id']]
            current_field = missing_fields[0] if missing_fields else None
            status = "completed" if not missing_fields else "awaiting_info"
            response_text = form_data.get("message", "")

            # If more fields to fill, recursively call process_field_input
            if current_field:
                next_state = {
                    **state,
                    "filled_fields": filled_fields,
                    "missing_fields": missing_fields,
                    "current_field": current_field,
                    "conversation_history": history,
                    "status": status,
                    "response": response_text,
                    "thread_id": thread_id,
                }
                return await process_field_input(next_state)

            return {
                **state,
                "filled_fields": filled_fields,
                "form_fields": form_fields,
                "missing_fields": missing_fields,
                "current_field": current_field,
                "conversation_history": history,
                "status": status,
                "response": response_text,
                "thread_id": thread_id,
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
                "response": response_text,
                "thread_id": thread_id,
            }
    else:
        return {
            **state,
            "status": "completed" if not missing_fields else "awaiting_info",
            "thread_id": thread_id,
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
#form_filler_graph.add_node("human_input", human_input)

# Add edges
form_filler_graph.add_edge(START, "analyze_form")
form_filler_graph.add_edge("analyze_form", "process_field_input")
#form_filler_graph.add_conditional_edges("analyze_form", route_next_step)
#form_filler_graph.add_edge("human_input", "process_field_input")
form_filler_graph.add_conditional_edges("process_field_input", route_next_step)
# Remove this line: form_filler_graph.add_edge("end", END)

# Compile the graph with checkpointing and human-in-the-loop support
compiled_graph = form_filler_graph.compile(
    checkpointer=checkpointer
)
print(compiled_graph.get_graph().draw_ascii())

async def chat_analyze_form(state: FormFillerState) -> Dict[str, Any]:
    """
    Analyzes the user message and form fields for the chat-based form-filling process.

    Args:
        user_message: The initial user message
        form_fields: List of form fields to fill
        
    Returns:
        Initial state and response information
    """
    thread_id = str(uuid4())
    
    initial_state = {
        "user_message": state["user_message"],
        "form_fields": state["form_fields"],
        "filled_fields": [],
        "missing_fields": [],
        "current_field": None,
        #"next_field": None,
        "conversation_history": [],
        "status": "in_progress",
        "response_message": "",
        "thread_id": thread_id
    }
    
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = await compiled_graph.ainvoke(initial_state, config)
 
        return {
            "thread_id": thread_id,
            "response_message": result["response_message"],
            "status": result["status"],
            "filled_fields": result["filled_fields"],
            "form_fields": result["form_fields"],
            "missing_fields": result["missing_fields"],
            "current_field": result["current_field"],
            "conversation_history": result["conversation_history"]
        }
    except Exception as e:
            print("LangGraph Error:", e)
            traceback.print_exc()
            return {"error": str(e), "traceback": traceback.format_exc()}

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
    
    #import pdb; pdb.set_trace()
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
