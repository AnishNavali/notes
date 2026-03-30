from agno.agent import Agent
from agno.tools.notion import NotionTools
from agno.models.aws import Claude
from boto3.session import Session
from dotenv import load_dotenv
load_dotenv()
session = Session(
    aws_access_key_id="AKIA3AHH2NGRTY55WOIN",
    aws_secret_access_key="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",
    region_name="us-east-1"
)
# Create an agent with Notion Tools
notion_agent = Agent(model=
        Claude(
        id="us.anthropic.claude-sonnet-4-6",
        session=session,
        cache_system_prompt=True,
        extended_cache_time=True),
    name="Notion Knowledge Manager",
    instructions=[
        "You are a smart assistant that helps organize information in Notion.",
        "When given content, analyze it and categorize it appropriately.",
        "Available categories: travel, tech, general-blogs, fashion, documents",
        "Always search first to avoid duplicate pages with the same tag.",
        "Be concise and helpful in your responses.",
    ],
    tools=[NotionTools()],
    markdown=True,
)

# notion_agent.print_response(input="can you read out the grocery list i have under the documents tag",stream=True)