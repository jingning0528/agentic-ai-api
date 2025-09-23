"""
Simplified test for basic Azure OpenAI functionality using gpt-4o-mini.
"""
import os
import asyncio
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage

# Load environment variables
load_dotenv()

def test_basic_openai_connection():
    """Test basic connection to Azure OpenAI."""
    try:
        # Initialize Azure OpenAI LLM (same as your llm_client.py)
        llm = AzureChatOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            openai_api_version="2024-12-01-preview",
        )
        
        # Simple test message
        messages = [HumanMessage(content="Hello, respond with 'Connection successful' if you can see this.")]
        
        # Get response
        response = llm.invoke(messages)
        
        print("✅ Azure OpenAI Connection Test Passed")
        print(f"Response: {response.content}")
        return True
        
    except Exception as e:
        print(f"❌ Azure OpenAI Connection Test Failed: {str(e)}")
        return False

def test_gpt4o_mini_specific():
    """Test specifically targeting gpt-4o-mini functionality."""
    try:
        llm = AzureChatOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            openai_api_version="2024-12-01-preview",
            temperature=0.1,  # Low temperature for consistent responses
        )
        
        # Test with a simple prompt that should work well with gpt-4o-mini
        test_prompt = "What is 2+2? Answer with just the number."
        messages = [HumanMessage(content=test_prompt)]
        
        response = llm.invoke(messages)
        
        print("✅ GPT-4o-mini Test Passed")
        print(f"Question: {test_prompt}")
        print(f"Answer: {response.content}")
        
        # Verify the response contains "4"
        if "4" in response.content:
            print("✅ Response validation passed")
            return True
        else:
            print("⚠️  Response validation failed - unexpected answer")
            return False
            
    except Exception as e:
        print(f"❌ GPT-4o-mini Test Failed: {str(e)}")
        return False

async def test_async_functionality():
    """Test async functionality of Azure OpenAI."""
    try:
        llm = AzureChatOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
            openai_api_version="2024-12-01-preview",
        )
        
        messages = [HumanMessage(content="Say 'Async test successful'")]
        response = await llm.ainvoke(messages)
        
        print("✅ Async Test Passed")
        print(f"Response: {response.content}")
        return True
        
    except Exception as e:
        print(f"❌ Async Test Failed: {str(e)}")
        return False

def check_environment_variables():
    """Check if required environment variables are set."""
    required_vars = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT_NAME"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        return False
    else:
        print("✅ All required environment variables are set")
        return True

if __name__ == "__main__":
    print("🚀 Starting simplified Azure OpenAI tests...\n")
    
    # Check environment first
    env_ok = check_environment_variables()
    if not env_ok:
        print("\n❌ Environment check failed. Please set required variables in .env file")
        exit(1)
    
    print()
    
    # Run basic tests
    basic_test = test_basic_openai_connection()
    print()
    
    gpt4o_test = test_gpt4o_mini_specific()
    print()
    
    # Run async test
    async_test = asyncio.run(test_async_functionality())
    print()
    
    # Summary
    total_tests = 3
    passed_tests = sum([basic_test, gpt4o_test, async_test])
    
    print(f"📊 Test Summary: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("🎉 All tests passed! Your Azure OpenAI setup is working correctly.")
    else:
        print("⚠️  Some tests failed. Check your Azure OpenAI configuration.")