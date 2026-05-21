from datetime import datetime
import pytz
from pymongo import MongoClient
import db as database
import os
from dotenv import load_dotenv
load_dotenv()
mongo_client = MongoClient(os.getenv("MONGO_URI"))
db = mongo_client["reminders_db"]
reminders_coll = db["reminders"]

def set_reminder(message: str,
    due_datetime: str,  # ISO: "2026-03-17T22:30:00+05:30"
    user_id: str,
    password: str):
    """Use this tool to set a reminder.
    Args:
    message(str): the reminder message.
    due_datetime(str): the due date and time of the reminder in ISO format with time zone.
    user_id(str): the user's user name.
    password(str): the user's password.
    Returns: str
    """
    user_password=database.get_one(collection="users",key={"email":user_id},projection={"password":1})["password"]
    if password!=user_password:
        return "invalid password"
    try:
        due_time = datetime.fromisoformat(due_datetime)
        now = datetime.now(pytz.timezone('Asia/Kolkata'))
        
        if due_time <= now:
            # raise HTTPException(status_code=400, detail="Due time must be in future")
            return "Due time must be in future"
        
        delay_seconds = int((due_time - now).total_seconds())
        
        # Save to MongoDB
        reminder_doc = {
            "user_id": user_id,
            "message": message,
            "due_datetime": due_time,
            "status": "scheduled",
            "created_at": now,
            "delay_seconds": delay_seconds,
            "task_id": None
        }
        result = reminders_coll.insert_one(reminder_doc)
        rid = str(result.inserted_id)
        
        print(f"📅 Scheduled reminder {rid} for user {user_id} in {delay_seconds}s")
        return "Reminder set successfully"
    except Exception as e:
        # raise HTTPException(status_code=400, detail="Invalid datetime format")
        
        print("invalid datetime format")
        raise e
    
def add_to_workspace(user_id: str, password:str , component: dict, page:str="Main"):
    """Use this tool to add a note component to the workspace.
    Args:
        user_id(str): the user name of the user.
        password(str): the user's password.
        component(dict): the component dict to be added to the workspace.
        page(str): the page name in the workspace where component will be added.
    Returns: str

    """
    user_password=database.get_one(collection="users",key={"email":user_id},projection={"password":1})["password"]
    if password!=user_password:
        return "invalid password"
    
    workspace=db["workspace"]
    user_doc = workspace.find_one({"user": user_id})
    if not user_doc:
        return "User workspace not found"
    
    # Check if page exists in workspace - do NOT create new pages
    workspace_data = user_doc.get("workspace", {})
    if page not in workspace_data:
        return f"Page '{page}' does not exist. Ask user to create the page first."
    
    workspace.update_one({"user":user_id},{"$push":{f"workspace.{page}": component}})
    print(component)
    return f"Added component successfully to page '{page}'"

def get_workspace(user_id:str,password:str, page:str="Main"):
    """Use this tool to get the entire workspace of the user.
    Args: user_id(str): the user name of the user.
          password(str): the user's password.
          page(str): the page name in the workspace to get components from.
    Returns dict"""
    user_password=database.get_one(collection="users",key={"email":user_id},projection={"password":1})["password"]
    if password!=user_password:
        return "invalid password"
    workspace=db["workspace"]
    user_doc = workspace.find_one({"user":user_id})
    if not user_doc:
        return []
    page_data = user_doc.get("workspace", {}).get(page, [])
    if page_data == [] or page_data is None:
        return []
    return page_data
def update_component(user_id:str , password:str, component_title:str, updated_component:dict, page:str="Main"):
    """Use this tool to update an existing notes component.
    Args:
    user_id(str): the user name of the user.
    password(str): the user's password.
    component_title(str) : the name of the component that you want to update.
    updated_component(dict): the new updated component that is going to overwrite on the existing one.
    page(str): the page name in the workspace where the component is located."""
    user_password=database.get_one(collection="users",key={"email":user_id},projection={"password":1})["password"]
    if password!=user_password:
        return "invalid password"
    
    workspace=db["workspace"]
    user_doc = workspace.find_one({"user": user_id})
    if not user_doc:
        return "User workspace not found"
    
    # Check if page exists in workspace
    workspace_data = user_doc.get("workspace", {})
    if page not in workspace_data:
        return f"Page '{page}' not found"
    
    # Find component index by title in that page
    page_components = workspace_data.get(page, [])
    component_index = None
    for i, comp in enumerate(page_components):
        if comp.get("title") == component_title:
            component_index = i
            break
    
    if component_index is None:
        return f"Component '{component_title}' not found on page '{page}'"
    
    # Update using direct index path
    workspace.update_one(
        {"user": user_id},
        {"$set": {f"workspace.{page}.{component_index}": updated_component}}
    )
    return f"{component_title} updated successfully in page '{page}'"

def get_page_names(user_id: str, password: str):
    """Use this tool to get all page names in the user's workspace.
    Args:
        user_id(str): the user name of the user.
        password(str): the user's password.
    Returns: list of page names"""
    user_password=database.get_one(collection="users",key={"email":user_id},projection={"password":1})["password"]
    if password!=user_password:
        return "invalid password"
    workspace=db["workspace"]
    user_doc = workspace.find_one({"user":user_id})
    if not user_doc:
        return ["Main"]
    workspace_data = user_doc.get("workspace", {})
    if not workspace_data:
        return ["Main"]
    page_names = list(workspace_data.keys())
    if not page_names:
        return ["Main"]
    return page_names

def create_page(user_id: str, password: str, page_name: str):
    """Use this tool to create a new page in the workspace.
    Args:
        user_id(str): the user name of the user.
        password(str): the user's password.
        page_name(str): the name of the new page to create.
    Returns: str"""
    user_password=database.get_one(collection="users",key={"email":user_id},projection={"password":1})["password"]
    if password!=user_password:
        return "invalid password"
    workspace=db["workspace"]
    user_doc = workspace.find_one({"user":user_id})
    if user_doc and user_doc.get("workspace", {}).get(page_name):
        return f"Page '{page_name}' already exists"
    workspace.update_one({"user":user_id},{"$set":{f"workspace.{page_name}": []}})
    return f"Page '{page_name}' created successfully"

def delete_page(user_id: str, password: str, page_name: str):
    """Use this tool to delete a page from the workspace.
    Args:
        user_id(str): the user name of the user.
        password(str): the user's password.
        page_name(str): the name of the page to delete.
    Returns: str"""
    user_password=database.get_one(collection="users",key={"email":user_id},projection={"password":1})["password"]
    if password!=user_password:
        return "invalid password"
    if page_name == "Main":
        return "Cannot delete the Main page"
    workspace=db["workspace"]
    workspace.update_one({"user":user_id},{"$unset":{f"workspace.{page_name}": ""}})
    return f"Page '{page_name}' deleted successfully"

def get_component_format(component_type:str):
    """Use this tool to get the format of the component to be added to the workspace.
    Args:
    component_type(str): the type of the component for which format is returned.
    Returns : dict """
    components={
        "table":{
    "type": "table",
    "title": "Title of the table",
    "x":"x coordinate of the component ranges from 0-11",
    "y":"y coordinate of the component starts from 0",
    "w": "width of the component on a scale of 1-12",
    "h": "height of the component on a scale of 1-12",
    "data": {
      "headers": ["list of column names"],
      "data": [
        ["Row name1", "rowdata1", "rowdata2"],
        ["Row name2", "rowdata1", "rowdata2"],
      ],
    },
  },
  "task-list":{
    "type": "task-list",
    "title": "Title of the task-list",
    "x":"x coordinate of the component ranges from 0-11",
    "y":"y coordinate of the component starts from 0",
    "w": "width of the component on a scale of 1-12",
    "h": "height of the component on a scale of 1-12",
    "data": {
      "tasks": [
        {
          "title": "name of the task",
          "priority": "high/medium/low",
          "completed": False,
        },
      ],
    },
  },
  "todo":{
    "type": "todo",
    "title":"title of the todo list",
    "x":"x coordinate of the component ranges from 0-11",
    "y":"y coordinate of the component starts from 0",
    "w": "width of the component on a scale of 1-12",
    "h": "height of the component on a scale of 1-12",
    "data": {
      "items": [
        { "text": "Name of the to do item", "completed": False },
        { "text": "Name of the to do item", "completed": True },
      ],
    },
  },
  "journal":{
    "type": "journal",
    "title": "Name of the journal",
    "x":"x coordinate of the component ranges from 0-11",
    "y":"y coordinate of the component starts from 0",
    "w": "width of the component on a scale of 1-12",
    "h": "height of the component on a scale of 1-12",
    "data": {

      "date": "date as yyyy-mm-dd",
      "content": "Journal entry",
      "mood": "good",
    },
  },
  "goal":{
    "type": "goal",
    "title": "Name of the Goal",
    "x":"x coordinate of the component ranges from 0-11",
    "y":"y coordinate of the component starts from 0",
    "w": "width of the component on a scale of 1-12",
    "h": "height of the component on a scale of 1-12",
    "data": {
      "milestones": [
        { "text": "Goal item1 ", "completed": True },
        { "text": "Goal item 2", "completed": True },
      ],
    },
  },
  "event":{
    "type": "event",
    "title": "Name of the event",
    "x":"x coordinate of the component ranges from 0-11",
    "y":"y coordinate of the component starts from 0",
    "w": "width of the component on a scale of 1-12",
    "h": "height of the component on a scale of 1-12",
    "data": {
      "events": [
        { "title": "event item1", "date": "2026-03-25", "time": "09:00" },
        { "title": "event item 2", "date": "2026-03-25", "time": "14:00" },
      ],
    },
  },
  "commitment":{
    "type": "commitment",
    "title": "Name of the component",
    "x":"x coordinate of the component ranges from 0-11",
    "y":"y coordinate of the component starts from 0",
    "w": "width of the component on a scale of 1-12",
    "h": "height of the component on a scale of 1-12",
    "data": {
      "commitments": [
        { "text": "commitement item 1", "completed": True },
        { "text": "commitement item 2", "completed": False },
      ],
    },
  },
  "project":{
    "type": "project",
    "title": "name of the component",
    "x":"x coordinate of the component ranges from 0-11",
    "y":"y coordinate of the component starts from 0",
    "w": "width of the component on a scale of 1-12",
    "h": "height of the component on a scale of 1-12",
    "data": {
      "description":
        "description of the project , for example: Complete overhaul of the company website with modern design and improved UX",
      "progress": 50,
      "deadline": "2026-04-15",
      "status": "active",
      "tasks": [
        {
          "id": "p1",
          "title": "Design mockups",
          "priority": "high",
          "completed": True,
        },
        {
          "id": "p2",
          "title": "Setup Next.js project",
          "priority": "high",
          "completed": True,
        },
      ],
    },
  },
  "reminder":{
    "type": "reminder",
    "title": "Reminders for me",
    "x":"x coordinate of the component ranges from 0-11",
    "y":"y coordinate of the component starts from 0",
    "w": "width of the component on a scale of 1-12",
    "h": "height of the component on a scale of 1-12",
    "data": {
      "reminders": [
           {
              "title": 'Title of the reminder',
              "date": '2026-03-31',
              "time": '21:00',
              "priority": 'medium',
              "repeat": 'none',
              "completed": False,
              "createdAt": '2026-03-30T10:56:51.869Z'
            }
      ],
    },
  },
  "chart":{
  "type": "chart",
  "title": "Your Chart Title",
  "x":"x coordinate of the component ranges from 0-11",
  "y":"y coordinate of the component starts from 0",
  "w": "width of the component on a scale of 1-12",
  "h": "height of the component on a scale of 1-12",
  "data": {
    "chartType": "Bar/Line/Area/Pie/Donut/Scatter/Funnel",
    "chartData": [
      { "id": "1", "name": "Label(x-axis)", "value": 1234 },
    ],
  },
}
    }
    return components[component_type]
# print(get_workspace(user_id="Anish"))
# workspace=db["workspace"]
# ad=workspace.update_one({"user":"Anish"},{"$set":{"workspace":[]}},upsert=True)
# print(ad)
# print(get_component_format(component_type="todo"))
# add_to_workspace(user_id="Anish",
#                  component={
#     "type": "event",
#     "title": "Calendar for me",
#     "data": {
#       "w": 4,
#       "h": 4,
#       "events": [
#         { "title": "Team Standup", "date": "2026-03-25", "time": "09:00" },
#         { "title": "Project Review", "date": "2026-03-25", "time": "14:00" },
#         { "title": "Dentist Appointment", "date": "2026-03-26", "time": "11:00" },
#       ],
#     },
#   })
