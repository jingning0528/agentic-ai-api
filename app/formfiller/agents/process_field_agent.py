from ..llm_client import llm
from langchain.agents import create_react_agent, AgentExecutor
from ..prompts.process_field_prompt import process_field_prompt

tools = []
process_field_agent = create_react_agent(llm, tools, process_field_prompt)

process_field_executor = AgentExecutor(
    agent=process_field_agent,
    tools=tools,
    verbose=True,
    handle_parsing_errors=True,
    max_iterations=10,
    return_intermediate_steps=True,
)