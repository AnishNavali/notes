from datetime import datetime
import pytz
from pymongo import MongoClient
mongo_client = MongoClient("mongodb://localhost:27017")
db = mongo_client["reminders_db"]
reminders_coll = db["reminders"]

def set_reminder(message: str,
    due_datetime: str,  # ISO: "2026-03-17T22:30:00+05:30"
    user_id: str):
    """Use this tool to set a reminder.
    Args:
    message(str): the reminder message.
    due_datetime(str): the due date and time of the reminder in ISO format with time zone.
    user_id(str): the user's user name.
    Returns: str
    """
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
    
def add_to_workspace(user_id: str, component: dict):
    """Use this tool to add a note component to the workspace.
    Args:
        user_id(str): the user name of the user.
        component(dict): the component dict to be added to the workspace.
    Returns: str

    """
    workspace=db["workspace"]
    workspace.update_one({"user":user_id},{"$push":{"workspace":component}})
    print(component)
    return "Added component successfully to the workspace"

def get_workspace(user_id:str):
    """Use this tool to get the entire workspace of the user.
    Args: user_id(str): the user name of the user.
    Returns dict"""

    workspace=db["workspace"]
    return workspace.find_one({"user":user_id})["workspace"]
def update_component(user_id:str , component_title:str, updated_component:dict):
    """Use this tool to update an existing notes component.
    Args:
    user_id(str): the user name of the user.
    component_title(str) : the name of the component that you want to update.
    updated_component(str): the new updated component that is going to overwrite on the existing one."""
    workspace=db["workspace"]
    workspace.update_one({"user":user_id,"workspace.title":component_title},{"$set":{"workspace.$":updated_component}})
    return f"{component_title} updated successfully"

def get_component_format(component_type:str):
    """Use this tool to get the format of the component to be added to the workspace.
    Args:
    component_type(str): the type of the component for which format is returned.
    Returns : dict """
    components={
        "table":{
    "type": "table",
    "title": "Title of the table",
    "data": {
      "w": "width of the component on a scale of 1-12",
      "h": "height of the component on a scale of 1-12",
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
    "data": {
       "w": "width of the component on a scale of 1-12",
      "h": "height of the component on a scale of 1-12",
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
    "data": {
       "w": "width of the component on a scale of 1-12",
      "h": "height of the component on a scale of 1-12",
      "items": [
        { "text": "Name of the to do item", "completed": False },
        { "text": "Name of the to do item", "completed": True },
      ],
    },
  },
  "journal":{
    "type": "journal",
    "title": "Name of the journal",
    "data": {
       "w": "width of the component on a scale of 1-12",
      "h": "height of the component on a scale of 1-12",
      "date": "date as yyyy-mm-dd",
      "content": "Journal entry",
      "mood": "good",
    },
  },
  "goal":{
    "type": "goal",
    "title": "Name of the Goal",
    "data": {
       "w": "width of the component on a scale of 1-12",
      "h": "height of the component on a scale of 1-12",
      "milestones": [
        { "text": "Goal item1 ", "completed": True },
        { "text": "Goal item 2", "completed": True },
      ],
    },
  },
  "event":{
    "type": "event",
    "title": "Name of the event",
    "data": {
       "w": "width of the component on a scale of 1-12",
      "h": "height of the component on a scale of 1-12",
      "events": [
        { "title": "event item1", "date": "2026-03-25", "time": "09:00" },
        { "title": "event item 2", "date": "2026-03-25", "time": "14:00" },
      ],
    },
  },
  "commitment":{
    "type": "commitment",
    "title": "Name of the component",
    "data": {
       "w": "width of the component on a scale of 1-12",
      "h": "height of the component on a scale of 1-12",
      "commitments": [
        { "text": "commitement item 1", "completed": True },
        { "text": "commitement item 2", "completed": False },
      ],
    },
  },
  "project":{
    "type": "project",
    "title": "name of the component",
    "data": {
      "w": 4,
      "h": 4,
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
