from fastapi import APIRouter, Request
from pydantic import BaseModel
import db
from dependencies import CurrentUser
from datetime import datetime
import pytz
import json
import secrets
import string
from func import *
from ai import agent

router = APIRouter(prefix="/api")


@router.get("/get_workspace")
async def get_workspace(current_user: CurrentUser):  
    """Return the workspace for the authenticated user."""
    user_id = current_user.get("email", "") 
    workspace = db.get_one(collection="workspace", key={"user": user_id})
    if not workspace:
        return {"workspace": []}
    return {"workspace": workspace.get("workspace", [])}


class Component(BaseModel):
    title: str | None = None
    component: dict | None = None
    x: int | None = None
    y: int | None = None
    w: int | None = None
    h: int | None = None


@router.post("/update_workspace")
def update_workspace(data: Component, current_user: CurrentUser):
    """Update a workspace component for the authenticated user."""
    user_id = current_user.get(
        "email", ""
    )  
    update = db.save(
        collection="workspace",
        key={"user": user_id, "workspace.title": data.title},
        doc={"workspace.$": data.component},
    )
    if update:
        return True

@router.delete("/clear_workspace")
def clear_workspace(current_user: CurrentUser):
    user_id = current_user.get(
        "email", ""
    ) 
    clear=db.save(collection="workspace",key={"user":user_id},doc={"workspace":[]})
    if clear:
        return True
    else:
        False
@router.delete("/delete_component")
def delete_component(data: Component, current_user: CurrentUser):
    user_id = current_user.get("email", "") 
    delete = db.delete_one_item(
        collection="workspace",
        key={"user": user_id},
        doc={"workspace": {"title": data.title}},
    )
    if delete:
        return True


@router.post("/add_to_workspace")
def add_to_workspace(data: Component, current_user: CurrentUser):
    user_id = current_user.get(
        "email", ""
    ) 
  
    update = db.push(
        collection="workspace",
        key={"user": user_id},
        doc={"workspace": data.component},
    )

    if update:
        return True


class Signup(BaseModel):
    country_code: str
    phone: str
    timezone:str
    state:str
    


@router.get("/check_user")
def check_user(current_user: CurrentUser):
    email = current_user.get("email", "") 
    try:
        check = db.get_one(collection="users", key={"email": email})["whatsapp_number"]
        if check:
            data = db.get_one(collection="users", key={"email": email})
           
            return {"valid": True, "data": data}
    except Exception as e:
        print(str(e))
        db.save(collection="workspace", key={"user": email}, doc={"workspace": []})
        return {"valid": False, "data": dict(current_user)}


@router.post("/signup")
def signup(data: Signup, current_user: CurrentUser):

    email = current_user.get("email", "")  
    whatsapp_number = data.country_code.split("+")[1] + data.phone
    print(whatsapp_number)
    phone_check=db.get_one(collection="users",key={"whatsapp_number":whatsapp_number})
    if phone_check:
        return False
    else:
        doc = dict(data)
        doc["whatsapp_number"] = whatsapp_number
        alphabet = string.ascii_letters + string.digits
        doc["password"] = "".join(secrets.choice(alphabet) for _ in range(8))
        doc["input_tokens"]=0
        doc["output_tokens"]=0
        doc["subscription"]={"plan":"free"}
        print(doc)
        save = db.save(collection="users", key={"email": email}, doc=doc)
        print(save)
        print(data.timezone)
        return True



class Msg(BaseModel):
    msg: str


@router.post("/llm")
async def llm(msg: Msg, current_user: CurrentUser):
    email = current_user.get("email", "")
 
    allow=check_sub_status(filter={"email":email})
    print(allow)
    if allow[0]:
        user_data=allow[1]
        from_number = user_data[0]["whatsapp_number"]
        print("user data", user_data)

        text = msg.msg

        time = datetime.now(pytz.timezone(user_data[0]["timezone"]))
        response = agent.run(
            input=f"""
        <user_name>{user_data[0]["name"]}</user_name>
        <user_id>{user_data[0]["email"]}</user_id>
        <password>{user_data[0]["password"]}</password>
        <platform>web</platform>
        <message>{text}</message> 
        <datetime>{time}</datetime>""",
            session_id=from_number,
        )
        tokens = response.metrics.to_dict()
        db.inc(
                collection="users",
                key={"whatsapp_number": from_number},
                doc={
                    "input_tokens": tokens["input_tokens"],
                    "output_tokens": tokens["output_tokens"],
                },
            )
   
        print(response.content)
        return {"answer": response.content, "update": True}
    else:
        return {"answer": "You have hit your usage limits", "update": False}
    
    


@router.get("/test")
def test():
    return True


@router.post("/update_settings")
async def update_settings(data: dict, current_user: CurrentUser):
    email = current_user.get("email", "")
    update = db.save(collection="users", key={"email": email}, doc=data)
    if update:
        return True

@router.get("/check_invite_code")
async def check_invite_code( request:Request,current_user: CurrentUser):
    email = current_user.get("email", "")
    invite_code=request.query_params["invite_code"]
    data=db.get_one(collection="invite_codes", key={"email":email})
    if invite_code==data["inivte_code"]:
        db.save(collection="users",key={"email":email},doc={"subscription":{"plan":"invite"}})
        return True
    else:
        return False
    
class Invite(BaseModel):
    user:str
    password:str
    email:str
@router.post("/create_invite")
async def create_invite(data:Invite):
    if data.user=="anish" and data.password=="Point2212@!@#":
        invite_code=data.email[:4].upper()+"AI_APP"
        db.save(collection="invite_codes",key={"email":data.email},doc={"inivte_code":invite_code})
        return invite_code
    else:
        return False
