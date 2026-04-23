# --- JSON Response Wrappers: For API Envelopes ---
from flask import jsonify
import os, re
from uuid7 import uuid7

# ---------------- Helper Functions -------------------------------

def classify_age(age):
    """
    Maps numerical age to an age group string.
    """
    if age <= 12:
        return "child"
    elif age <= 19:
        return "teenager"
    elif age <= 59:
        return "adult"
    else:
        return "senior"

def generate_uuid():
    """
    Generates a UUIDv7 string for new records.
    """
    return str(uuid7())

def parse_natural_query(q):
    """
    Parses a plain-English user query into recognized filters using regex and rule-based logic.
    Only rule-based parsing: no machine learning.
    Returns a filter dictionary or None if the query can't be interpreted.
    """
    q = q.lower()
    filters = {}

    # Detect genders
    if "female" in q:
        filters["gender"] = "female"
    elif "male" in q:
        filters["gender"] = "male"

    # "young" → age 16-24
    if "young" in q:
        filters["min_age"] = 16
        filters["max_age"] = 24
    # Child rules
    if "child" in q:
        filters["age_group"] = "child"
    # Teenager rules
    if "teenager" in q or "teen" in q:
        filters["age_group"] = "teenager"
    # Adult rule
    if "adult" in q:
        filters["age_group"] = "adult"
    # Senior rule
    if "senior" in q or "old" in q:
        filters["age_group"] = "senior"

    # Numerical ages via text
    above_match = re.search(r"(?:above|over|older than)\s+(\d+)", q)
    under_match = re.search(r"(?:under|below|younger than)\s+(\d+)", q)
    
    if above_match:
        filters["min_age"] = int(above_match.group(1))
    if under_match:
        filters["max_age"] = int(under_match.group(1))

    # Map known country names to their codes (expand as needed)
    from countries import country_map  # Imported from countries.py
    for country_name, code in country_map.items():
        if country_name in q:
            filters["country_id"] = code

    # Return None if nothing found to filter on
    if not filters:
        return None
    return filters


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
