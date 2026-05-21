from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
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


def ensure_workspace_format(user_id: str) -> dict:
    """Ensure workspace is in new object format, migrate if needed."""
    workspace = db.get_one(collection="workspace", key={"user": user_id})
    
    # Case 1: No workspace document at all - create new one
    if not workspace:
        db.save(collection="workspace", key={"user": user_id}, doc={"workspace": {"Main": []}})
        return {"Main": []}
    
    workspace_data = workspace.get("workspace")
    
    # Case 2: workspace is a list (old format) or empty list - migrate to object using replace
    if isinstance(workspace_data, list):
        new_doc = {"user": user_id, "workspace": {"Main": workspace_data}}
        db.replace_doc(collection="workspace", key={"user": user_id}, doc=new_doc)
        return {"Main": workspace_data}
    
    # Case 3: workspace is dict (already new format)
    if isinstance(workspace_data, dict):
        return workspace_data
    
    # Case 4: workspace is empty list or None - replace with new format
    new_doc = {"user": user_id, "workspace": {"Main": []}}
    db.replace_doc(collection="workspace", key={"user": user_id}, doc=new_doc)
    return {"Main": []}


@router.get("/get_workspace")
async def get_workspace(current_user: CurrentUser, page: str = "Main"):
    """Return the workspace for the authenticated user for a specific page."""
    user_id = current_user.get("email", "")
    print(f"get_workspace: user={user_id}, page=[{page}]")
    print(f"get_workspace: full query params in request")
    workspace_data = ensure_workspace_format(user_id)
    print(f"get_workspace: workspace_data={workspace_data}")
    page_components = workspace_data.get(page, [])
    pages = list(workspace_data.keys()) if workspace_data else ["Main"]
    print(f"get_workspace: returning page={page}, components={len(page_components)}, pages={pages}")
    return {"workspace": page_components, "pages": pages}


@router.get("/get_pages")
async def get_pages(current_user: CurrentUser):
    """Return all page names for the authenticated user."""
    user_id = current_user.get("email", "")
    workspace_data = ensure_workspace_format(user_id)
    pages = list(workspace_data.keys()) if workspace_data else ["Main"]
    return {"pages": pages}


class CreatePage(BaseModel):
    page_name: str


@router.post("/create_page")
async def create_page(data: CreatePage, current_user: CurrentUser):
    """Create a new page in the workspace."""
    user_id = current_user.get("email", "")
    page_name = data.page_name
    workspace_data = ensure_workspace_format(user_id)
    if page_name in workspace_data:
        return {"error": "Page already exists"}
    db.save(collection="workspace", key={"user": user_id}, doc={f"workspace.{page_name}": []})
    return {"success": True, "pages": list(workspace_data.keys()) + [page_name]}


class RenamePage(BaseModel):
    old_name: str
    new_name: str


@router.post("/rename_page")
async def rename_page(data: RenamePage, current_user: CurrentUser):
    """Rename a page in the workspace."""
    user_id = current_user.get("email", "")
    old_name = data.old_name
    new_name = data.new_name
    
    if old_name == "Main" or new_name == "Main":
        return {"error": "Cannot rename Main page"}
    
    if old_name == new_name:
        return {"success": True}
    
    workspace_data = ensure_workspace_format(user_id)
    
    if old_name not in workspace_data:
        return {"error": "Page not found"}
    
    if new_name in workspace_data:
        return {"error": "Page already exists"}
    
    # Get components from old page
    old_components = workspace_data.get(old_name, [])
    
    # Create new page with old components and delete old page
    db.save(collection="workspace", key={"user": user_id}, doc={f"workspace.{new_name}": old_components})
    db.unset(collection="workspace", key={"user": user_id}, doc={f"workspace.{old_name}": ""})
    
    return {"success": True, "pages": list(workspace_data.keys())}


@router.delete("/delete_page")
async def delete_page(current_user: CurrentUser, page: str = "Main"):
    """Delete a page from the workspace."""
    user_id = current_user.get("email", "")
    if page == "Main":
        return {"error": "Cannot delete Main page"}
    ensure_workspace_format(user_id)
    db.unset(collection="workspace", key={"user": user_id}, doc={f"workspace.{page}": ""})
    return {"success": True}


class Component(BaseModel):
    title: str | None = None
    old_title: str | None = None  # For when title is being changed
    component: dict | None = None
    x: int | None = None
    y: int | None = None
    w: int | None = None
    h: int | None = None


@router.post("/update_workspace")
def update_workspace(data: Component, current_user: CurrentUser, page: str = "Main"):
    """Update a workspace component for the authenticated user on a specific page."""
    user_id = current_user.get("email", "")
    ensure_workspace_format(user_id)
    
    workspace = db.get_one(collection="workspace", key={"user": user_id})
    if not workspace:
        return False
    
    workspace_data = workspace.get("workspace", {})
    page_components = workspace_data.get(page, [])
    
    search_title = (data.title or "").strip()
    component_type = data.component.get("type") if data.component else None
    
    component_index = None
    
    # First try: find by exact title match
    for i, comp in enumerate(page_components):
        if comp.get("title", "").strip() == search_title:
            component_index = i
            break
    
    # Second try: if not found by title, find by type (title changed case)
    if component_index is None and component_type:
        for i, comp in enumerate(page_components):
            if comp.get("type") == component_type:
                component_index = i
                break
    
    if component_index is None:
        return False
    
    # Update the component at the found index
    update_key = f"workspace.{page}.{component_index}"
    update = db.save(
        collection="workspace",
        key={"user": user_id},
        doc={update_key: data.component},
    )
    if update:
        return True
    return False

@router.delete("/clear_workspace")
def clear_workspace(current_user: CurrentUser):
    """Clear ALL workspace data - removes all pages and components completely."""
    user_id = current_user.get("email", "")
    # Completely reset workspace to only have Main page with empty components
    db.save(collection="workspace", key={"user": user_id}, doc={"workspace": {"Main": []}})
    return True
@router.delete("/delete_component")
def delete_component(data: Component, current_user: CurrentUser, page: str = "Main"):
    user_id = current_user.get("email", "")
    ensure_workspace_format(user_id)  # Migrate if needed
    delete = db.delete_one_item(
        collection="workspace",
        key={"user": user_id},
        doc={f"workspace.{page}": {"title": data.title}},
    )
    if delete:
        return True


@router.post("/add_to_workspace")
def add_to_workspace(data: Component, current_user: CurrentUser, page: str = "Main"):
    user_id = current_user.get("email", "")
    ensure_workspace_format(user_id)  # Migrate if needed
    update = db.push(
        collection="workspace",
        key={"user": user_id},
        doc={f"workspace.{page}": data.component},
    )
    if update:
        return True

    
class Invite(BaseModel):
    user:str
    password:str
    email:str
@router.post("/create_invite")
async def create_invite(data:Invite):
    if data.user=="anish" and data.password=="Point2212@!@#":
        invite_code=data.email[:4].upper()+"AI_APP"
        db.save(collection="invite_codes",key={"email":data.email},doc={"inivte_code":invite_code})
        return True
    else:
        return False

class Signup(BaseModel):
    country_code: str
    phone: str
    timezone: str
    state: Optional[str] = None
    


@router.get("/check_user")
def check_user(current_user: CurrentUser):
    email = current_user.get("email", "")  # "anish.navali@gmail.com"
    try:
        check = db.get_one(collection="users", key={"email": email})["whatsapp_number"]
        if check:
            data = db.get_one(collection="users", key={"email": email})
            print(data)
            return {"valid": True, "data": data}
    except KeyError as k:
        db.save(collection="workspace", key={"user": email}, doc={"workspace": []})
        return {"valid": False, "data": dict(current_user)}


@router.post("/signup")
def signup(data: Signup, current_user: CurrentUser):

    email = current_user.get("email", "")
    
    # Check if user already exists
    existing_user = db.get_one(collection="users", key={"email": email})
    if existing_user and existing_user.get("whatsapp_number"):
        return {"success": False, "error": "User already exists"}
    
    whatsapp_number = data.country_code.split("+")[1] + data.phone
    print(whatsapp_number)
    doc = dict(data)
    doc["whatsapp_number"] = whatsapp_number
    alphabet = string.ascii_letters + string.digits
    doc["password"] = "".join(secrets.choice(alphabet) for _ in range(8))
    doc["input_tokens"]=0
    doc["output_tokens"]=0
    print(doc)
    save = db.save(collection="users", key={"email": email}, doc=doc)
    print(save)
    print(data.timezone)
    return True


# signup(data=Signup(country_code="+91",phone="9606024155"))
# print(check_user())


class Msg(BaseModel):
    msg: str


@router.post("/llm")
async def llm(msg: Msg, current_user: CurrentUser, page: str | None = None):
    print(f"LLM endpoint received - page param: {page}")
    email = current_user.get("email", "")
    # user_data = db.query(collection="users", query={"email": email})
    # user_data=check_sub_status()
    allow=check_sub_status(filter={"email":email})
    print(allow)
    if allow[0]:
        user_data=allow[1]
        from_number = user_data[0]["whatsapp_number"]
        print("user data", user_data)

        text = msg.msg

        time = datetime.now(pytz.timezone(user_data[0]["timezone"]))
        
        # Build input with optional page
        page_context = f"<page>{page}</page>" if page else ""
        
        response = agent.run(
            input=f"""
        <user_name>{user_data[0]["name"]}</user_name>
        <user_id>{user_data[0]["email"]}</user_id>
        <password>{user_data[0]["password"]}</password>
        <platform>web</platform>
        <message>{text}</message> 
        {page_context}
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
        #   <response_structure>Return in a json structure: answer: Your answer, update: True if there is an update to the workspace else False</response_structure>

        # response_data=extract_json(response.content)
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
    if invite_code==data["invite_code"]:
        db.save(collection="users",key={"email":email},doc={"subscription":{"plan":"invite"}})
        return True
    else:
        return False

@router.get("/get_pages")
async def get_pages(current_user: CurrentUser):
    """Get all page names for the authenticated user."""
    email = current_user.get("email", "")
    workspace = db.get_one(collection="workspace", key={"user": email})
    if not workspace:
        return {"pages": ["Main"]}
    workspace_data = workspace.get("workspace", {})
    if not workspace_data:
        return {"pages": ["Main"]}
    page_names = list(workspace_data.keys())
    if not page_names:
        return {"pages": ["Main"]}
    return {"pages": page_names}

class PageName(BaseModel):
    page_name: str

@router.post("/create_page")
async def create_page(data: PageName, current_user: CurrentUser):
    """Create a new page in the workspace."""
    email = current_user.get("email", "")
    page_name = data.page_name
    workspace = db.get_one(collection="workspace", key={"user": email})
    if workspace and workspace.get("workspace", {}).get(page_name):
        return {"success": False, "message": f"Page '{page_name}' already exists"}
    db.save(collection="workspace", key={"user": email}, doc={f"workspace.{page_name}": []})
    return {"success": True, "message": f"Page '{page_name}' created successfully"}

@router.delete("/delete_page")
async def delete_page(data: PageName, current_user: CurrentUser):
    """Delete a page from the workspace."""
    email = current_user.get("email", "")
    page_name = data.page_name
    if page_name == "Main":
        return {"success": False, "message": "Cannot delete the Main page"}
    db.save(collection="workspace", key={"user": email}, doc={f"workspace.{page_name}": None})
    return {"success": True, "message": f"Page '{page_name}' deleted successfully"}

