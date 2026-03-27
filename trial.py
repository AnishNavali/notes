from agno.agent import Agent
# from agno.tools.notion import NotionTools
from agno.models.aws import Claude, AwsBedrock 
from boto3.session import Session
from datetime import datetime
from dotenv import load_dotenv
from tools import *
load_dotenv()
session = Session(
    aws_access_key_id="AKIA3AHH2NGRTY55WOIN",
    aws_secret_access_key="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",
    region_name="us-east-1"
)
# Create an agent with Notion Tools
agent = Agent(model=
        # Claude(
        # id="us.anthropic.claude-sonnet-4-6",
        # session=session,
        # cache_system_prompt=True,
        # extended_cache_time=True),
        AwsBedrock(
            id="mistral.ministral-3-14b-instruct",
            session=session

        ))
# agent.print_response("can you understand image inputs?")