import db
import json
def calculate_cost(tokens:tuple):
    input_cost=(3/1000000)*tokens[0]
    output_cost=(15/1000000)*tokens[1]
    total_cost=input_cost+output_cost
    return total_cost

def check_sub_status(filter: dict):
    user_data=db.query(collection="users", query=filter)
    if user_data[0].get("subscription")==None:
        return False
        
    else:
        return check_token_limit(tokens=(user_data[0]["input_tokens"],user_data[0]["output_tokens"]),subscription=user_data[0]["subscription"]["plan"]),user_data

def check_token_limit(tokens:tuple,subscription:str):
    cost=calculate_cost(tokens=tokens)
    print(cost)
    if subscription=="basic" or subscription=="invite":
        if cost < 3: 
            return True
        else:
            return False
    elif subscription=="pro":
        if cost < 6:
            return True
        else:
            return False
        
def extract_json(text: str):
    decoder = json.JSONDecoder()
    i = 0
    while i < len(text):
        if text[i] in ["{", "["]:
            try:  # decode json
                obj, _ = decoder.raw_decode(text[i:])
                return obj
            except json.JSONDecodeError:
                pass
        i += 1
    return None
