from app.llm.tools.ai_search_tool import ai_search_tool
from ..llm_client import llm
from langchain.agents import create_react_agent, AgentExecutor
from app.formfiller.prompts.analyze_form_prompt import analyze_form_prompt

analyze_form_tools = [ai_search_tool]

analyze_form_agent = create_react_agent(llm, analyze_form_tools, analyze_form_prompt)

analyze_form_executor = AgentExecutor(
    agent=analyze_form_agent,
    tools=analyze_form_tools,
    verbose=True,
    handle_parsing_errors=True,
    max_iterations=20,
    return_intermediate_steps=True,
)