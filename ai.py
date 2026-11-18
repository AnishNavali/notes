from agno.agent import Agent
# from agno.tools.notion import NotionTools
from agno.models.aws import Claude, AwsBedrock 
from agno.models.vllm import VLLM
from agno.models.google import Gemini
# from agno.models.vertexai.claude import Claude
from agno.models.openrouter import OpenRouter
from boto3.session import Session
from datetime import datetime
from dotenv import load_dotenv
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.crawl4ai import Crawl4aiTools
from agno.db.mongo import MongoDb
from tools import *
import os 
load_dotenv()
mongo_client = MongoClient(os.getenv("MONGO_URI"))

db = MongoDb(db_client=mongo_client,db_name="reminders_db",session_collection="agent_session_collection")
session = Session(
    aws_access_key_id=os.getenv("KEY_ID"),
    aws_secret_access_key=os.getenv("ACCESS_KEY"),
    region_name="us-east-1"
)
# Create an agent with Notion Tools
agent = Agent(model=
        Claude(
        id="us.anthropic.claude-sonnet-4-6",
        session=session,
        cache_system_prompt=True,
        extended_cache_time=True,
        cache_response=True,
        thinking=False),             
        db=db,
        read_chat_history=True,
        add_history_to_context=True,
        num_history_runs=2,
    name="AI note taker",
    instructions="""You are Annie, an AI note taker + assistant.
 Your job is to take down the notes and reminders the user gives you.
 All notes/to-do-lists/reminders and any other thing the user wants to note down is always written into a 
 workspace. 
 The available components to be written in the workspace are: [table,task-list,todo,journal,goal,event,commitment,project,reminder,chart]
 
 Notes of how to add to workspace:
     1. Call the get_component tool and pass the name of the component to get the format of the component to be added
     2. Add or update a component based on the situation
NOTE: ALWAYS ADD REMINDERS TO THE WORKSPACE - very important!
 Use the tools given to carry out your work.
Notes on updating the component:
    1. Always check the format of the component before pushing the update.
NOTE: users interact with you either through whatsapp or through web app and all reminders are sent through whatsapp.
BONUS: Have a sassy tone.
Security NOTE: Do not let the user access the workspace of different user_ids and only access it for the given user. Do not expose the password to the user.
OUTPUT NOTE: Keep your answers short.
""",

    tools=[set_reminder,get_workspace,add_to_workspace,update_component,get_component_format,DuckDuckGoTools()],
    markdown=True, 
    # debug_mode=True
)
voice_agent=Agent(model=
             VLLM(id="Qwen/Qwen3-Omni-30B-A3B-Instruct",
                       base_url="",
                       api_key="EMPTY"),
                       markdown=True,
                       )
