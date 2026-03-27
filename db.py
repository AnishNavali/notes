from pymongo import MongoClient
import hashlib
import urllib
import hmac
import certifi


def connect_db():
    # with open('config.toml','r') as f:
    #     secrets=toml.load(f)
    # mongo_username = secrets['mongo']['username']
    # mongo_password = secrets['mongo']['password']
    connection = "mongodb://127.0.0.1:27017"
    # connection = "mongodb+srv://Anish:Fjk22%26%2331@chatbotjs-mongo.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000"
    client = MongoClient(
        connection
        #                  ,tls=True,
        # tlsCAFile=certifi.where(),
        # serverSelectionTimeoutMS=5000
    )
    db = client["reminders_db"]
    return db


def get_user(uname):
    db = connect_db()
    user_db = db["users"]
    result = user_db.find_one({"email": uname})
    return result


def get_phone(uname):
    db = connect_db()
    user_db = db["users"]
    result = user_db.find_one({"email": uname})
    return result


def get_hashed(text):
    digest = hmac.new(
        bytes("data-in-knowledge-out", "UTF-8"),
        msg=bytes(text, "UTF-8"),
        digestmod=hashlib.sha256,
    )
    signature = digest.hexdigest()
    return signature


def check_password(uname, pwd):
    db = connect_db()
    user_db = db["users"]
    result = user_db.find_one(
        {"email": uname, "password": get_hashed(pwd)}, {"_id": 0, "password": 0}
    )
    return result


def get_collection(collection):
    db = connect_db()
    col = db[collection]
    return col


def query(collection=None, query=None, username=None):
    db = connect_db()
    data_db = db[collection]
    projection = {}
    projection["_id"] = 0

    result = list(data_db.find(query, projection))
    return result


def get_one_item(collection=None, id=None, username=None):
    db = connect_db()
    data_db = db[collection]
    projection = {}
    projection["_id"] = 0

    result = data_db.find_one({"_id": id, "user": username}, projection)
    return result


def get_list(collection=None, attribute=None, username=None):
    print(collection, attribute, username)
    db = connect_db()
    data_db = db[collection]
    projection = {}
    projection[attribute] = 1
    projection["_id"] = 0

    result = list(data_db.find({"email": username}, projection))
    print(result)
    if result is None:
        return {"status": False, "data": None}
    else:
        return {"status": True, "data": result}


def save(collection=None, key=None, doc=None):
    client = connect_db()
    db = client[collection]
    result = db.update_one(key, {"$set": doc}, upsert=True)
    return result
def push(collection=None, key=None, doc=None):
    client = connect_db()
    db = client[collection]
    result = db.update_one(key, {"$push": doc}, upsert=True)
    return result

def insert(collection=None, doc=None):
    client = connect_db()
    db = client[collection]
    result = db.insert_one(document=doc)
    return result


def delete_collection(collection):
    db = connect_db()
    result = db.drop_collection(name_or_collection=collection)
    return result


def get_one_item(collection=None, id=None, username=None):
    db = connect_db()
    data_db = db[collection]
    projection = {}
    projection["_id"] = 0

    result = data_db.find_one({"_id": id, "email": username}, projection)
    return result

def delete_one_item(collection=None, key=None, doc=None):
    client = connect_db()
    db = client[collection]
    result = db.update_one(key, {"$pull": doc}, upsert=True)
    return result


def get_one(collection=None, key=None, username=None, projection=None):
    # print ("get_one key", key)
    db = connect_db()
    data_db = db[collection]
    if projection is None:
        projection = {}
    projection['_id'] = 0

    result = data_db.find_one(key, projection)
    return result


def delete_inference(collection, rulename, inference, result_statement):
    db = connect_db()
    result = db[collection].update_one(
        {"rulename": rulename},
        {
            "$pull": {
                "statements": {
                    "inference": inference,
                    "result_statement": result_statement,
                }
            }
        },
    )
    return result



def get_list(collection=None, attributes=[], username=None):
    db = connect_db()
    data_db = db[collection]
    projection = {}
    for attribute in attributes:
        projection[attribute] = 1
    projection["_id"] = 0

    result = list(data_db.find({"email": username}, projection))

    if result is None:
        return {"status": False, "data": None}
    else:
        return {"status": True, "data": result}


def update_inference(collection=None, rule_name=None, new_inference=None):
    client = connect_db()
    db = client[collection]

    document = db.find_one({"rulename": rule_name})
    if not document:
        return {"status": False, "message": "No matching rule found."}


# ---------------------------------------------------------------------------
# OAuth / user helpers
# ---------------------------------------------------------------------------


def upsert_oauth_user(
    provider: str, provider_id: str, email: str, name=None, picture=None
) -> dict:
    """
    Insert or update a user record identified by (provider, provider_id).
    Returns the full document including the string '_id'.
    """
    from datetime import datetime, timezone

    db = connect_db()
    users = db["users"]
    now = datetime.now(timezone.utc)
    filter_query = {"provider": provider, "provider_id": provider_id}
    update = {
        "$set": {
            "email": email,
            "name": name,
            "picture": picture,
            "updated_at": now,
        },
        "$setOnInsert": {
            "provider": provider,
            "provider_id": provider_id,
            "created_at": now,
        },
    }
    users.update_one(filter_query, update, upsert=True)
    doc = users.find_one(filter_query)
    doc["_id"] = str(doc["_id"])
    

    return doc


def get_user_by_id(user_id: str) -> dict | None:
    """Fetch a user document by its MongoDB _id string."""
    from bson import ObjectId

    db = connect_db()
    users = db["users"]
    try:
        doc = users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc
