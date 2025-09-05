from ..llm_client import llm
from ..prompts.process_field_prompt import process_field_prompt
from langchain.chains import LLMChain

# You don't need tools or ReAct agent
process_field_executor = LLMChain(
    llm=llm,
    prompt=process_field_prompt,
    verbose=True
)