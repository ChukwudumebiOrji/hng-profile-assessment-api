# Standard library imports
import uuid 
import time 
import requests  
from flask import Flask, json, request, jsonify, make_response 
from flask_cors import CORS 
from flask_sqlalchemy import SQLAlchemy
import os, re, logging 
from helpers import json_success, json_error, parse_natural_query, classify_age, generate_uuid

# ---------------------- Flask Application Setup ------------------

app = Flask(__name__)      # Initialize Flask app
CORS(app)                  # Enable Cross-Origin Resource Sharing for all endpoints (required by frontend clients)

# Database Location: Use environment variable or default to /tmp/profiles.db for SQLite
db_path = os.environ.get("DB_PATH", "/tmp/profiles.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"   # SQLite database URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False             # Disable costly event notification system
db = SQLAlchemy(app)     # Initialize SQLAlchemy extension for ORM

# SQLAlchemy Logging: Print all generated SQL queries for debugging and profiling (dev use)
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# --------------- Database Model: Profile ------------------------

class Profile(db.Model):
    # The Profile table structure (matches project requirements)
    id = db.Column(db.String(36), primary_key=True, index=True)  # UUID, primary key, indexed
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)  # Unique name
    gender = db.Column(db.String(20), nullable=False, index=True)  # "male" or "female"
    gender_probability = db.Column(db.Float, nullable=False, index=True)  # Prediction score
    # sample_size = db.Column(db.Integer, nullable=False, index=True)  # Sample size from Genderize
    age = db.Column(db.Integer, nullable=False, index=True)  # Exact age
    age_group = db.Column(db.String(20), nullable=False, index=True)  # "child", "teenager", "adult", "senior"
    country_id = db.Column(db.String(10), nullable=False, index=True)  # ISO country code (NG, US, etc)
    country_name = db.Column(db.String(100), nullable=False, index=True)   # Full country name
    country_probability = db.Column(db.Float, nullable=False, index=True)  # Country prediction probability
    created_at = db.Column(db.String(30), nullable=False, index=True)      # UTC ISO timestamp as string

    # Utility: Full dict representation (for detailed API responses)
    def to_full_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "gender": self.gender,
            "gender_probability": round(self.gender_probability, 2)
                if self.gender_probability is not None else None,
            # "sample_size": self.sample_size,
            "age": self.age,
            "age_group": self.age_group,
            "country_id": self.country_id,
            "country_name" : self.country_name,
            "country_probability": round(self.country_probability, 2)
                if self.country_probability is not None else None,
            "created_at": self.created_at,
        }

    # Utility: Summary dict (for summary API responses/lists)
    def to_summary_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "gender": self.gender,
            "age": self.age,
            "age_group": self.age_group,
            "country_id": self.country_id,
        }
    
# -------------------- Data Seeding Function ----------------------

def seed_data(json_path="seed_profiles.json"):
    """
    Seeds the Profile table from a JSON file.
    Will not insert any records if the table already has any profiles (idempotent).
    Each profile is mapped to the Profile model. Uses provided created_at or current time.
    """
    if Profile.query.count() > 0:
        return  # Skip seeding if any data exists

    try:
        with open(json_path, "r") as f:
            profiles = json.load(f)
            profiles = profiles.get("profiles")
            print("Seed profiles loaded:", type(profiles), profiles[:1])
            
            for p in profiles:
                # Each profile entry is loaded and transformed to db row
                profile = Profile(
                    id=generate_uuid(),
                    name=p["name"],
                    gender=p["gender"],
                    gender_probability=p["gender_probability"],
                    # sample_size=p.get("sample_size", 0),
                    age=p["age"],
                    age_group=classify_age(p["age"]),  # Use helper for age_group
                    country_id=p["country_id"],
                    country_name=p["country_name"],
                    country_probability=p["country_probability"],
                    created_at=p.get("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                )
                db.session.add(profile)
            db.session.commit()
        return json_success(message="Seed data loaded successfully", data={"count": len(profiles)})
    except FileNotFoundError:
        return json_error(f"File not found at {json_path}", status_code=404)
    except Exception as e:
        return json_error(f"Failed to load seed data: {str(e)}", status_code=500)

# --------------- Database Creation and Seeding --------------------

with app.app_context():
    db.create_all()        # Create tables if not exist
    result = seed_data()   # Attempt to seed
    if result is not None: # Print seeding results/errors
        print(result.get_json()) 
    else:        
        print("Seed data already exists, skipping seeding.")


# ---------------- Basic Ping Endpoint --------------------

@app.route("/")
def index():
    # Health check endpoint
    return "API is running", 200

# --------------- Create Profile API Endpoint ---------------

@app.route("/api/profiles", methods=["POST"])
def create_profile():
    """
    Creates a new profile using the provided 'name' field.
    Calls external APIs (genderize, agify, nationalize) for details.
    Implements idempotency by re-using the profile if name exists.
    Validates request and each API; returns error codes if any fail.
    """
    body = request.get_json(silent=True)
    if not body or "name" not in body:
        return json_error("Missing or empty name", 400)
    name = body.get("name")
    if not isinstance(name, str):
        return json_error("Invalid type", 422)
    name = name.strip()
    if not name:
        return json_error("Missing or empty name", 400)

    # Idempotency: check by name (case-insensitive)
    existing = Profile.query.filter(db.func.lower(Profile.name) == name.lower()).first()
    if existing:
        return json_success(
            data=existing.to_full_dict(),
            message="Profile already exists",
            status_code=200
        )

    # Get attributes via external APIs
    try:
        gresp = requests.get("https://api.genderize.io", params={"name": name}, timeout=10)
        gdata = gresp.json()
    except Exception:
        return json_error("Genderize returned an invalid response", 502)
    try:
        aresp = requests.get("https://api.agify.io", params={"name": name}, timeout=10)
        adata = aresp.json()
    except Exception:
        return json_error("Agify returned an invalid response", 502)
    try:
        nresp = requests.get("https://api.nationalize.io", params={"name": name}, timeout=10)
        ndata = nresp.json()
    except Exception:
        return json_error("Nationalize returned an invalid response", 502)

    # Validate each API result
    if not gdata.get("gender") or gdata.get("count", 0) == 0:
        return json_error("Genderize returned an invalid response", 502)
    if adata.get("age") is None:
        return json_error("Agify returned an invalid response", 502)
    countries = ndata.get("country", [])
    if not countries:
        return json_error("Nationalize returned an invalid response", 502)

    # Take highest-probability country result
    top_country = max(countries, key=lambda c: c.get("probability", 0))
    age = adata["age"]

    # Always store creation time as UTC ISO string
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    profile = Profile(
        id=generate_uuid(),
        name=name,
        gender=gdata["gender"],
        gender_probability=gdata["probability"],
        # sample_size=gdata["count"],
        age=age,
        age_group=classify_age(age),
        country_id=top_country["country_id"],
        country_name=top_country["country_name"],
        country_probability=top_country["probability"],
        created_at=created_at,
    )
    db.session.add(profile)
    db.session.commit()
    return json_success(profile.to_full_dict(), status_code=201)

# --------------- Profiles List API (Filter/Sort/Paginate) ------------

@app.route("/api/profiles", methods=["GET"])
def list_profiles():
    """
    Returns a paginated, filtered, and sortable list of profiles.
    Supports combined filters, allowed sorting keys, and strict query param validation.
    Prints query duration for performance benchmarking.
    """
    query = Profile.query
    start = time.time()  # For benchmarking query speed

    # Allowed filter/sort params for query validation
    allowed_filters = ["gender", "country_id", "age_group", "min_age", "max_age", "min_gender_probability", "min_country_probability"]
    allowed_sorts = ["page", "limit", "sort_by", "order"]

    # Validate for invalid query parameters
    for param in request.args:
        if param not in allowed_filters and param not in allowed_sorts:
            return json_error("Invalid query parameters", 400)
        
    # Apply each supported filter if specified
    for param in allowed_filters:
        val = request.args.get(param)
        if val:
            attr = getattr(Profile, param, None)
            if attr:
                query = query.filter(db.func.lower(attr) == val.lower())
    
    # Numeric filters (age, probability, etc.)
    min_age = request.args.get("min_age", type=int)
    max_age = request.args.get("max_age", type=int)
    if min_age is not None: query = query.filter(Profile.age >= min_age)
    if max_age is not None: query = query.filter(Profile.age <= max_age)

    # Sorting logic
    sort_filters = ["gender", "country_id", "age_group", "age", "gender_probability", "country_probability", "created_at"]
    sort_by = request.args.get("sort_by", "created_at")
    order = request.args.get("order", "desc").lower()

    if sort_by in sort_filters:
        sort_attr = getattr(Profile, sort_by)
        query = query.order_by(sort_attr.asc() if order == "asc" else sort_attr.desc())
    else:
        query = query.order_by(Profile.created_at.desc())

    # Pagination: count, page, limit, offset
    total_count = query.count()
    page = request.args.get("page", type=int, default=1)
    limit = min(request.args.get("limit", type=int, default=10), 50) # cap limit at 50
    offset_value = (page - 1) * limit
    profiles = query.offset(offset_value).limit(limit).all()

    # Performance logging
    elapsed = time.time() - start
    print(f"Query took {elapsed:.3f} seconds")

    return json_success({
        "page": page,
        "limit": limit,
        "total": total_count,
        "count": len(profiles),
        "data": [p.to_summary_dict() for p in profiles]
    })

# --------------- Get Single Profile API -------------------

@app.route("/api/profiles/<string:profile_id>", methods=["GET"])
def get_profile(profile_id):
    """
    Returns details for a single profile by its ID.
    404 error if not found.
    """
    profile = Profile.query.get(profile_id)
    if not profile:
        return json_error("Profile not found", 404)
    return json_success(profile.to_full_dict())

# --------------- Delete Profile API -------------------

@app.route("/api/profiles/<string:profile_id>", methods=["DELETE"])
def delete_profile(profile_id):
    """
    Deletes the profile by its ID.
    Returns 204 if deleted, 404 if not found.
    """
    profile = Profile.query.get(profile_id)
    if not profile:
        return json_error("Profile not found", 404)
    db.session.delete(profile)
    db.session.commit()
    resp = make_response("", 204)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

# --------------- Natural Language Search Endpoint ---------------

@app.route("/api/profiles/search", methods=["GET"])
def search_profiles():
    """
    Allows natural language queries via the 'q' parameter.
    Parses English query string using rule-based parse_natural_query().
    Applies filters returned by parse, supports paging and summary results.
    """
    query_str = request.args.get("q", "")
    if not query_str:
        return jsonify({"status": "error", "message": "Query parameter 'q' is required"}), 400

    interpreted_filters = parse_natural_query(query_str)
    if interpreted_filters is None:
        return jsonify({"status": "error", "message": "Unable to interpret query"}), 200

    query = Profile.query

    # Apply filters as parsed from natural language
    if "gender" in interpreted_filters:
        query = query.filter(Profile.gender == interpreted_filters["gender"])
    if "country_id" in interpreted_filters:
        query = query.filter(Profile.country_id == interpreted_filters["country_id"])
    if "age_group" in interpreted_filters:
        query = query.filter(Profile.age_group == interpreted_filters["age_group"])
    if "min_age" in interpreted_filters:
        query = query.filter(Profile.age >= interpreted_filters["min_age"])
    if "max_age" in interpreted_filters:
        query = query.filter(Profile.age <= interpreted_filters["max_age"])

    total = query.count()
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 10, type=int)
    limit = min(max(limit, 1), 50)
    
    profiles = query.offset((page - 1) * limit).limit(limit).all()

    return jsonify({
        "status": "success",
        "page": page,
        "limit": limit,
        "total": total,
        "data": [p.to_summary_dict() for p in profiles]
    }), 200

# --- Global Error Handler: Ensure All Errors Return JSON, Not HTML ---

@app.errorhandler(Exception)
def handle_exception(e):
    """
    Catches all uncaught exceptions and returns them as a JSON error.
    Use this to make sure the frontend/API never sees a Flask HTML error page.
    """
    resp = jsonify({"status": "error", "message": str(e)})
    resp.status_code = 500
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

# --- Main Entrypoint ---

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Use PORT env variable or default 8000
    app.run(host="0.0.0.0", port=port)        # Run the Flask server
