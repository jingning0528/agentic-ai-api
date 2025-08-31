"""
Form-filling agent based on LangGraph for automatically populating web forms.
This module defines the core agent logic and workflow for auto-filling forms
based on user input and interactive form field completion.
"""
import os
from typing import Dict, List, Any, Optional, TypedDict, Literal
from uuid import uuid4
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import AzureChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

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
    form_fields: List[FormField]
    filled_fields: Dict[str, Any]
    missing_fields: List[str]
    current_field: Optional[str]
    conversation_history: List[Dict[str, Any]]
    status: Literal["in_progress", "awaiting_info", "completed"]
    response: str
    thread_id: str

# Node 1: Initial form analysis
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
    field_descriptions = []
    for field in form_fields:
        field_desc = f"Field ID: {field['field_id']}\nLabel: {field['label']}\nType: {field['type']}\n"
        if field.get('description'):
            field_desc += f"Description: {field['description']}\n"
        if field.get('options'):
            field_desc += f"Options: {', '.join(field['options'])}\n"
        if field.get('validation'):
            field_desc += f"Validation: {field['validation']}\n"
        field_desc += f"Required: {'Yes' if field.get('required', False) else 'No'}\n"
        field_descriptions.append(field_desc)
    
    all_field_descriptions = "\n\n".join(field_descriptions)
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"User message: {user_message}\n\nForm fields:\n{all_field_descriptions}")
    ]
    
    # Add conversation history for context if available
    if state.get("conversation_history"):
        history_context = "Previous conversation:\n"
        for entry in state["conversation_history"]:
            role = "User" if entry["role"] == "user" else "Assistant"
            history_context += f"{role}: {entry['content']}\n"
        messages.append(SystemMessage(content=history_context))
    
    # Get response from the LLM
    response = await model.ainvoke(messages)
    
    # Parse the model's response - in a real system, you'd have more robust parsing
    try:
        import json
        import re
        
        # Try to extract JSON from the response
        json_match = re.search(r'```json\n(.*?)\n```', response.content, re.DOTALL)
        if json_match:
            form_data = json.loads(json_match.group(1))
        else:
            # Fallback to see if the entire response is JSON
            form_data = json.loads(response.content)
    except:
        # Handle parsing failure gracefully
        form_data = {
            "filled_fields": {},
            "missing_fields": [field["field_id"] for field in form_fields]
        }
    
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
        # Find the current field details
        current_field_details = next((f for f in form_fields if f["field_id"] == current_field), {})
        field_label = current_field_details.get("label", current_field)
        
        response_text = f"I need some additional information. Can you provide the {field_label}?"
        if current_field_details.get("description"):
            response_text += f" ({current_field_details['description']})"
        if current_field_details.get("options"):
            options_text = ", ".join(current_field_details["options"])
            response_text += f" Options are: {options_text}"
    
    history.append({"role": "assistant", "content": response_text})
    
    return {
        **state,
        "filled_fields": filled_fields,
        "missing_fields": missing_fields,
        "current_field": current_field,
        "conversation_history": history,
        "status": status,
        "response": response_text
    }

# Node 2: Process user input for specific field
async def process_field_input(state: FormFillerState) -> FormFillerState:
    """
    Processes user input for a specific requested field.
    """
    user_message = state["user_message"]
    current_field = state["current_field"]
    form_fields = state["form_fields"]
    filled_fields = state["filled_fields"].copy()
    missing_fields = state["missing_fields"].copy()
    
    # Get the current field details
    current_field_details = next((f for f in form_fields if f["field_id"] == current_field), None)
    
    if not current_field_details:
        return state
    
    # Create system prompt for field validation
    system_prompt = f"""
    You are a form-filling assistant. The user is providing information for the field: {current_field_details['label']}.
    
    Field details:
    - Type: {current_field_details['type']}
    - Required: {'Yes' if current_field_details.get('required', False) else 'No'}
    {f"- Options: {', '.join(current_field_details['options'])}" if current_field_details.get('options') else ""}
    {f"- Validation: {current_field_details['validation']}" if current_field_details.get('validation') else ""}
    
    Extract the appropriate value from the user's response and validate it according to the field requirements.
    Return only the extracted value as it should be entered in the form field.
    """
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"User response for {current_field_details['label']}: {user_message}")
    ]
    
    # Get response from the LLM
    response = await model.ainvoke(messages)
    field_value = response.content.strip()
    
    # Update the filled_fields and missing_fields
    filled_fields[current_field] = field_value
    if current_field in missing_fields:
        missing_fields.remove(current_field)
    
    # Update conversation history
    history = state["conversation_history"]
    history.append({"role": "user", "content": user_message})
    
    # Determine next steps
    next_field = missing_fields[0] if missing_fields else None
    
    if not next_field:
        status = "completed"
        response_text = "Great! I've filled out the entire form. Here's a summary of the information:"
        for field in form_fields:
            field_id = field["field_id"]
            if field_id in filled_fields:
                response_text += f"\n- {field['label']}: {filled_fields[field_id]}"
    else:
        status = "awaiting_info"
        next_field_details = next((f for f in form_fields if f["field_id"] == next_field), {})
        field_label = next_field_details.get("label", next_field)
        
        response_text = f"Thanks! Now, can you provide the {field_label}?"
        if next_field_details.get("description"):
            response_text += f" ({next_field_details['description']})"
        if next_field_details.get("options"):
            options_text = ", ".join(next_field_details["options"])
            response_text += f" Options are: {options_text}"
    
    history.append({"role": "assistant", "content": response_text})
    
    return {
        **state,
        "filled_fields": filled_fields,
        "missing_fields": missing_fields,
        "current_field": next_field,
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
async def start_form_filling(user_message: str, form_fields: List[FormField]) -> Dict[str, Any]:
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
        "conversation_history": [],
        "status": "in_progress",
        "response": "",
        "thread_id": thread_id
    }
    
    config = {"configurable": {"thread_id": thread_id}}
    
    result = await compiled_graph.ainvoke(initial_state, config)
    return {
        "thread_id": thread_id,
        "response": result["response"],
        "status": result["status"],
        "filled_fields": result["filled_fields"],
        "missing_fields": result["missing_fields"]
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
    compiled_graph.update_state(config, {"user_message": user_message})
    
    # Continue graph execution
    result = await compiled_graph.ainvoke(None, config)
    
    return {
        "thread_id": thread_id,
        "response": result["response"],
        "status": result["status"],
        "filled_fields": result["filled_fields"],
        "missing_fields": result["missing_fields"]
    }
