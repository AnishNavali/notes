from fastapi import APIRouter, Request
from pydantic import BaseModel
import db
from dependencies import CurrentUser
from datetime import datetime
import pytz
from ai import agent

router = APIRouter()


@router.get("/get_workspace")
async def get_workspace(current_user:CurrentUser):#current_user:CurrentUser
    """Return the workspace for the authenticated user."""
    # print(current_user)
    user_id = current_user.get("email", "")#"Anish"
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
def update_workspace(data: Component, current_user:CurrentUser):
    """Update a workspace component for the authenticated user."""
    user_id = current_user.get("email", "")#"Anish"#current_user.get("name") or current_user.get("email", "")
    update = db.save(
        collection="workspace",
        key={"user": user_id, "workspace.title": data.title},
        doc={"workspace.$": data.component},
    )
    if update:
        return True
    
@router.delete("/delete_component")
def delete_component(data:Component, current_user:CurrentUser):
    user_id=current_user.get("email", "")#"Anish"
    print(data)
    delete=db.delete_one_item(collection="workspace",key={"user":user_id},doc={"workspace":{"title":data.title}})
    print(delete)
    if delete:
        return True
    
@router.post("/add_to_workspace")
def add_to_workspace(data:Component, current_user:CurrentUser):
    user_id = current_user.get("email", "")#"Anish"#current_user.get("name") or current_user.get("email", "")
    print(data)
    update = db.push(
        collection="workspace",
        key={"user": user_id},
        doc={"workspace": data.component},
    )
    print(update)
    if update:
        return True
    
class Signup(BaseModel):
    country_code: str
    phone : str
    subscription : str | None ="paid"

@router.get("/check_user")
def check_user(current_user:CurrentUser):
    email=current_user.get("email", "")#"anish.navali@gmail.com"
    check=db.get_one(collection="workspace",key={"user":email})
    print(check)
    if check:
        data=db.get_one(collection="users",key={"email":email})
        print(data)
        return {"valid":True,"data":data}
    else: 
        db.save(collection="workspace",key={"user":email},doc={"workspace":[]})
        return {"valid":False,"data":dict(current_user)}

@router.post("/signup")
def signup(data:Signup,current_user:CurrentUser):
    email=current_user.get("email", "")#"anish.navali@gmail.com"
    save=db.save(collection="users",key={"email":email},doc=dict(data))
    print(save)
    return True
# signup(data=Signup(country_code="+91",phone="9606024155"))
# print(check_user())
class Msg(BaseModel):
    msg:str
@router.post("/llm")
async def llm(msg:Msg,current_user:CurrentUser):
    email=current_user.get("email", "")
    user_data=db.query(collection="users",query={"email":email})
    from_number=user_data[0]['whatsapp_number']
    print("user data", user_data)
    
    text=msg.msg
    
    time=datetime.now(pytz.timezone('Asia/Kolkata'))
    response=agent.run(input=f"""<user_name>{user_data[0]['name']}</user_name>
                       <user_id>{user_data[0]['email']}
                      <message>{text}</message> 
                     <datetime>{time}</datetime>""",session_id=from_number)
    return response.content