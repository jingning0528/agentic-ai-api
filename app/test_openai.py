import os
import json
from openai import AzureOpenAI

def get_weather(location: str, unit: str = "celsius") -> str:
    """
    Get the current weather for a given location.
    
    Args:
        location (str): The city and state/country, e.g. "San Francisco, CA"
        unit (str): Temperature unit, either "celsius" or "fahrenheit"
    
    Returns:
        str: Weather information in JSON format
    """
    # Mock weather data for testing
    weather_data = {
        "location": location,
        "temperature": 22 if unit == "celsius" else 72,
        "unit": unit,
        "description": "Partly cloudy",
        "humidity": 65,
        "wind_speed": 10
    }
    return json.dumps(weather_data)

def test_openai_function_calling():
    """Test OpenAI function calling with Azure OpenAI"""
    
    # Initialize Azure OpenAI client
    client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2024-02-01",
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", "https://pen-match-v2-foundry.openai.azure.com/")
    )
    
    # Define the function schema for OpenAI
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather for a given location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city and state/country, e.g. San Francisco, CA"
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "Temperature unit"
                        }
                    },
                    "required": ["location"]
                }
            }
        }
    ]
    
    # Test messages
    messages = [
        {"role": "user", "content": "What's the weather like in Toronto, Canada?"}
    ]
    
    try:
        print("🚀 Testing OpenAI Function Calling...")
        print(f"📍 Endpoint: {client._base_url}")
        print(f"📝 User Query: {messages[0]['content']}")
        print("-" * 50)
        
        # Make the initial API call
        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini"),
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        
        # Get the assistant's response
        assistant_message = response.choices[0].message
        print(f"🤖 Assistant Response: {assistant_message.content}")
        
        # Check if the assistant wants to call a function
        if assistant_message.tool_calls:
            print("🔧 Function call detected!")
            
            # Add the assistant's message to conversation
            messages.append(assistant_message)
            
            # Process each function call
            for tool_call in assistant_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                print(f"📞 Calling function: {function_name}")
                print(f"📋 Arguments: {function_args}")
                
                # Call the actual function
                if function_name == "get_weather":
                    function_result = get_weather(**function_args)
                    print(f"📊 Function Result: {function_result}")
                    
                    # Add function result to conversation
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_result
                    })
            
            # Get the final response with function results
            final_response = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini"),
                messages=messages
            )
            
            print("-" * 50)
            print(f"✅ Final Response: {final_response.choices[0].message.content}")
            
        else:
            print("ℹ️  No function call was made")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False
    
    return True

if __name__ == "__main__":
    # Check required environment variables
    required_vars = ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("\nSet them using:")
        for var in missing_vars:
            print(f"export {var}='your_value_here'")
        exit(1)
    
    print("🧪 Starting OpenAI Function Calling Test")
    print("=" * 60)
    
    success = test_openai_function_calling()
    
    print("=" * 60)
    if success:
        print("✅ Test completed successfully!")
    else:
        print("❌ Test failed!")