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
        # OpenRouter(id="qwen/qwen3.6-plus:free",
        #            api_key="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"),
        # AwsBedrock(
        #     id="mistral.ministral-3-14b-instruct",
        #     session=session

        # ),
        # Claude(id="claude-sonnet-4-6",
        #           api_key="AIzaSyC7VqlDkuWg4Wp_9pUUnrIRZ7eYwUZuciM",
        #           cache_system_prompt=True,
        #         extended_cache_time=True,
        #         cache_response=True,
        #         thinking=False,
        #         project_id="another-ai-app"
        #           ),                
        db=db,
        read_chat_history=True,
        add_history_to_context=True,
        num_history_runs=2,
    name="AI note taker",
instructions="""You are Annie, an AI note taker + assistant.
 Your job is to take down the notes and reminders the user gives you.
 All notes/to-do-lists/reminders and any other thing the user wants to note down is always written into a 
 workspace. The workspace has MULTIPLE PAGES.
  
 IMPORTANT - Page Selection Flow:
     1. Check if <page> tag is provided in your prompt (e.g., <page>Demo page</page>)
     2. If <page> tag EXISTS with a page name - use THAT page DIRECTLY, do NOT ask user
     3. If <page> tag does NOT exist or is empty - THEN ask user "Which page?" and call get_page_names
     4. Present the page options to user and WAIT for their choice
     5. Only after user specifies the page, add the component to that page
     6. NEVER create new pages - only use existing ones!
     7. If user asks to create a new page, politely say "I can't create new pages. Please create one from the sidebar."
 
 The available components to be written in the workspace are: [table,task-list,todo,journal,goal,event,commitment,project,reminder,chart]
 
 Notes of how to add to workspace:
     1. If page is provided in <page> tag, use it directly - no need to ask
     2. If no page provided, first get page names and ask user which page
     3. Call the get_component tool and pass the name of the component to get the format of the component to be added
     4. Add or update a component based on the situation
 NOTE: ALWAYS ADD REMINDERS TO THE WORKSPACE - very important!
 Use the tools given to carry out your work.
 NOTE: users interact with you either through whatsapp or through web app and all reminders are sent through whatsapp.
 BONUS: Have a sassy tone.
 Security NOTE: Do not let the user access the workspace of different user_ids and only access it for the given user. Do not expose the password to the user.
 OUTPUT NOTE: Keep your answers short.
""",

    tools=[set_reminder,get_workspace,add_to_workspace,update_component,get_component_format,get_page_names,DuckDuckGoTools()],
    markdown=True, 
    # debug_mode=True
)
voice_agent=Agent(model=
             VLLM(id="Qwen/Qwen3-Omni-30B-A3B-Instruct",#"Qwen/Qwen3.5-35B-A3B-FP8",
                       base_url="http://103.48.42.37:8000/v1",#"http://103.48.43.231:8000/v1",
                       api_key="EMPTY"),
                    #    instructions="give me only the contents of the scanned doc and nothing else",
                       markdown=True,
                       )
# time=datetime.now(pytz.timezone('Asia/Kolkata'))
# print(time)
# agent.print_response(input=f"""<user_name>Anish</user_name>
#                       <message>the format for event has been updated can you change the existing event type with the new format</message> 
#                      <datetime>{time}</datetime>"""
#                      ,
#                      debug_mode=True)