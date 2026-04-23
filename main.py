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
    """
    if Profile.query.count() > 0:
        return  # Skip seeding if any data exists

    try:
        with open(json_path, "r") as f:
            profiles = json.load(f)
            profiles = profiles.get("profiles")
            
            for p in profiles:
                profile = Profile(
                    id=generate_uuid(),
                    name=p["name"],
                    gender=p["gender"],
                    gender_probability=p["gender_probability"],
                    age=p["age"],
                    age_group=classify_age(p["age"]),
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
    if result is not None:
        print(result.get_json()) 
    else:        
        print("Seed data already exists, skipping seeding.")

# ---------------- Basic Ping Endpoint --------------------

@app.route("/")
def index():
    return "API is running", 200

# --------------- Create Profile API Endpoint ---------------

@app.route("/api/profiles", methods=["POST"])
def create_profile():
    body = request.get_json(silent=True)
    if not body or "name" not in body:
        return json_error("Missing or empty name", 400)
    name = body.get("name")
    if not isinstance(name, str):
        return json_error("Invalid type", 422)
    name = name.strip()
    if not name:
        return json_error("Missing or empty name", 400)

    existing = Profile.query.filter(db.func.lower(Profile.name) == name.lower()).first()
    if existing:
        return json_success(
            data=existing.to_full_dict(),
            message="Profile already exists",
            status_code=200
        )

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

    if not gdata.get("gender") or gdata.get("count", 0) == 0:
        return json_error("Genderize returned an invalid response", 502)
    if adata.get("age") is None:
        return json_error("Agify returned an invalid response", 502)
    countries = ndata.get("country", [])
    if not countries:
        return json_error("Nationalize returned an invalid response", 502)

    top_country = max(countries, key=lambda c: c.get("probability", 0))
    age = adata["age"]
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    profile = Profile(
        id=generate_uuid(),
        name=name,
        gender=gdata["gender"],
        gender_probability=gdata["probability"],
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
    query = Profile.query
    start = time.time()

    allowed_filters = ["gender", "country_id", "age_group", "min_age", "max_age", "min_gender_probability", "min_country_probability"]
    allowed_sorts = ["page", "limit", "sort_by", "order"]

    for param in request.args:
        if param not in allowed_filters and param not in allowed_sorts:
            return json_error(f"Invalid query parameter: {param}", 400)
        
    # Apply text filters
    string_filters = ["gender", "country_id", "age_group"]
    for param in string_filters:
        val = request.args.get(param)
        if val:
            attr = getattr(Profile, param, None)
            if attr:
                query = query.filter(db.func.lower(attr) == val.lower())
    
    # Numeric filters
    min_age = request.args.get("min_age", type=int)
    max_age = request.args.get("max_age", type=int)
    if min_age is not None: query = query.filter(Profile.age >= min_age)
    if max_age is not None: query = query.filter(Profile.age <= max_age)
    
    min_g_prob = request.args.get("min_gender_probability", type=float)
    if min_g_prob is not None: query = query.filter(Profile.gender_probability >= min_g_prob)

    min_c_prob = request.args.get("min_country_probability", type=float)
    if min_c_prob is not None: query = query.filter(Profile.country_probability >= min_c_prob)

    # Sorting logic
    sort_filters = ["gender", "country_id", "age_group", "age", "gender_probability", "country_probability", "created_at"]
    sort_by = request.args.get("sort_by", "created_at")
    order = request.args.get("order", "desc").lower()

    if sort_by not in sort_filters:
        return json_error(f"Invalid sort_by parameter: {sort_by}", 400)
    if order not in ["asc", "desc"]:
        return json_error("Invalid order parameter", 400)

    sort_attr = getattr(Profile, sort_by)
    
    # Use Profile.id.asc() as a secondary sort key to make duplicate values deterministic
    if order == "asc":
        query = query.order_by(sort_attr.asc(), Profile.id.asc())
    else:
        query = query.order_by(sort_attr.desc(), Profile.id.asc())

    total_count = query.count()
    
    # Safe pagination validation and execution
    try:
        page = int(request.args.get("page", 1))
        if page < 1: 
            return json_error("Page must be >= 1", 400)
    except ValueError:
        return json_error("Invalid page parameter", 400)

    try:
        limit = int(request.args.get("limit", 10))
        if limit < 1: 
            return json_error("Limit must be >= 1", 400)
        if limit > 50: 
            limit = 50 # Quietly max-cap at 50
    except ValueError:
        return json_error("Invalid limit parameter", 400)

    offset_value = (page - 1) * limit
    profiles = query.offset(offset_value).limit(limit).all()

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
    profile = Profile.query.get(profile_id)
    if not profile:
        return json_error("Profile not found", 404)
    return json_success(profile.to_full_dict())

# --------------- Delete Profile API -------------------

@app.route("/api/profiles/<string:profile_id>", methods=["DELETE"])
def delete_profile(profile_id):
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
    query_str = request.args.get("q", "")
    if not query_str:
        return json_error("Query parameter 'q' is required", 400)

    interpreted_filters = parse_natural_query(query_str)
    if interpreted_filters is None:
        return json_error("Unable to interpret query", 400)

    query = Profile.query

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
    
    try:
        page = int(request.args.get("page", 1))
        if page < 1: page = 1
    except ValueError:
        return json_error("Invalid page parameter", 400)

    try:
        limit = int(request.args.get("limit", 10))
        if limit < 1: limit = 10
        if limit > 50: limit = 50
    except ValueError:
        return json_error("Invalid limit parameter", 400)
    
    profiles = query.offset((page - 1) * limit).limit(limit).all()

    # Wrap natural queries in consistent API Success Envelopes
    return json_success({
        "page": page,
        "limit": limit,
        "total": total,
        "count": len(profiles),
        "data": [p.to_summary_dict() for p in profiles]
    })

# --- Global Error Handler ---

@app.errorhandler(Exception)
def handle_exception(e):
    resp = jsonify({"status": "error", "message": str(e)})
    resp.status_code = 500
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

# --- Main Entrypoint ---

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
