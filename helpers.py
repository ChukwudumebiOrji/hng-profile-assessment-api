# --- JSON Response Wrappers: For API Envelopes ---
from flask import jsonify

def json_success(data, status_code=200, message=None):
    """
    Standard success response.
    Includes status, optional message, and data.
    Adds CORS header to response.
    """
    content = {"status": "success"}
    if message:
        content["message"] = message
    if isinstance(data, dict) and "count" in data and "data" in data:
        content["count"] = data["count"]
        content["data"] = data["data"]
    else:
        content["data"] = data
    resp = jsonify(content)
    resp.status_code = status_code
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

def json_error(message, status_code=400):
    """
    Standard error response.
    Always returns JSON with 'status' and 'message'.
    Adds CORS header to response.
    """
    resp = jsonify({"status": "error", "message": message})
    resp.status_code = status_code
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp
