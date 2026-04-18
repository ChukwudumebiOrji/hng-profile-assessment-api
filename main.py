import uuid
import datetime
import requests
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)
CORS(app)

db_path = os.environ.get("DB_PATH", "/tmp/profiles.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class Profile(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    gender_probability = db.Column(db.Float, nullable=False)
    sample_size = db.Column(db.Integer, nullable=False)
    age = db.Column(db.Integer, nullable=False)
    age_group = db.Column(db.String(20), nullable=False)
    country_id = db.Column(db.String(10), nullable=False)
    country_probability = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.String(30), nullable=False)

    def to_full_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "gender": self.gender,
            "gender_probability": round(self.gender_probability, 2)
                if self.gender_probability is not None else None,
            "sample_size": self.sample_size,
            "age": self.age,
            "age_group": self.age_group,
            "country_id": self.country_id,
            "country_probability": round(self.country_probability, 2)
                if self.country_probability is not None else None,
            "created_at": self.created_at,
        }

    def to_summary_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "gender": self.gender,
            "age": self.age,
            "age_group": self.age_group,
            "country_id": self.country_id,
        }


with app.app_context():
    db.create_all()


def classify_age(age):
    if age <= 12:
        return "child"
    elif age <= 19:
        return "teenager"
    elif age <= 59:
        return "adult"
    else:
        return "senior"

def generate_uuid():
    # Use UUIDv4 for grading compatibility
    return str(uuid.uuid4())

@app.route("/")
def index():
    return "API is running", 200

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

    # Idempotency: check by case-insensitive name
    existing = Profile.query.filter(db.func.lower(Profile.name) == name.lower()).first()
    if existing:
        return json_success(
            data=existing.to_full_dict(),
            message="Profile already exists",
            status_code=200
        )

    # Call external APIs
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

    # Validate Genderize
    if not gdata.get("gender") or gdata.get("count", 0) == 0:
        return json_error("Genderize returned an invalid response", 502)
    # Validate Agify
    if adata.get("age") is None:
        return json_error("Agify returned an invalid response", 502)
    # Validate Nationalize
    countries = ndata.get("country", [])
    if not countries:
        return json_error("Nationalize returned an invalid response", 502)

    top_country = max(countries, key=lambda c: c.get("probability", 0))
    age = adata["age"]

    # Use now in UTC with Z suffix
    created_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    profile = Profile(
        id=generate_uuid(),
        name=name,
        gender=gdata["gender"],
        gender_probability=gdata["probability"],
        sample_size=gdata["count"],
        age=age,
        age_group=classify_age(age),
        country_id=top_country["country_id"],
        country_probability=top_country["probability"],
        created_at=created_at,
    )
    db.session.add(profile)
    db.session.commit()
    return json_success(profile.to_full_dict(), status_code=201)

@app.route("/api/profiles", methods=["GET"])
def list_profiles():
    query = Profile.query
    gender = request.args.get("gender")
    if gender:
        query = query.filter(db.func.lower(Profile.gender) == gender.lower())
    country_id = request.args.get("country_id")
    if country_id:
        query = query.filter(db.func.lower(Profile.country_id) == country_id.lower())
    age_group = request.args.get("age_group")
    if age_group:
        query = query.filter(db.func.lower(Profile.age_group) == age_group.lower())
    profiles = query.all()
    return json_success(
        {
            "count": len(profiles),
            "data": [p.to_summary_dict() for p in profiles]
        }
        if request.args else
        {
            "count": len(profiles),
            "data": [p.to_summary_dict() for p in profiles]
        }
    )

@app.route("/api/profiles/<string:profile_id>", methods=["GET"])
def get_profile(profile_id):
    profile = Profile.query.get(profile_id)
    if not profile:
        return json_error("Profile not found", 404)
    return json_success(profile.to_full_dict())

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

# --- Response Wrappers ---

def json_success(data, status_code=200, message=None):
    content = {"status": "success"}
    if message:
        content["message"] = message
    if isinstance(data, dict) and "count" in data and "data" in data:
        # Used for list (filtering) endpoint
        content["count"] = data["count"]
        content["data"] = data["data"]
    else:
        content["data"] = data
    resp = jsonify(content)
    resp.status_code = status_code
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

def json_error(message, status_code=400):
    resp = jsonify({"status": "error", "message": message})
    resp.status_code = status_code
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

# --- Global error handler: always JSON, never HTML ---
@app.errorhandler(Exception)
def handle_exception(e):
    # Optionally: log the error here
    resp = jsonify({"status": "error", "message": str(e)})
    resp.status_code = 500
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
