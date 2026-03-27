from fastapi import APIRouter, Request
from pydantic import BaseModel
import db
from dependencies import CurrentUser

router = APIRouter()


@router.get("/get_workspace")
async def get_workspace():#current_user:CurrentUser
    """Return the workspace for the authenticated user."""
    # print(current_user)
    user_id = "Anish"
    workspace = db.get_one(collection="workspace", key={"user": user_id})
    if not workspace:
        return {"workspace": []}
    return {"workspace": workspace.get("workspace", [])}


class Component(BaseModel):
    title: str | None = None
    component: dict | None = None


@router.post("/update_workspace")
def update_workspace(data: Component):
    """Update a workspace component for the authenticated user."""
    user_id = "Anish"#current_user.get("name") or current_user.get("email", "")
    update = db.save(
        collection="workspace",
        key={"user": user_id, "workspace.title": data.title},
        doc={"workspace.$": data.component},
    )
    if update:
        return True
    
@router.delete("/delete_component")
def delete_component(data:Component):
    user_id="Anish"
    print(data)
    delete=db.delete_one_item(collection="workspace",key={"user":user_id},doc={"workspace":{"title":data.title}})
    print(delete)
    if delete:
        return True
    
@router.post("/add_to_workspace")
def add_to_workspace(data:Component):
    user_id = "Anish"#current_user.get("name") or current_user.get("email", "")
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

# @router.post("/signup")
# def signup(data:Signup)