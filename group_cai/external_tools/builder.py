def build_param(typ, desc):
    return {"type": typ, "description": desc}
def build_params(**kwargs):
    return kwargs
def build_function(name, desc, required, params):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {
                "type": "object",
                "properties": params,
                "required": required
            }
        }
    }