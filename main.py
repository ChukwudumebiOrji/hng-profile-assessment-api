import uuid
import datetime
import requests
from flask import Flask, request, jsonify
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
            "gender_probability": self.gender_probability,
            "sample_size": self.sample_size,
            "age": self.age,
            "age_group": self.age_group,
            "country_id": self.country_id,
            "country_probability": self.country_probability,
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


def generate_uuid7():
    # UUID v7: timestamp-based, sortable
    timestamp_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
    timestamp_hex = format(timestamp_ms, "012x")
    random_bits = uuid.uuid4().hex[12:]
    hex_str = timestamp_hex + "7" + random_bits[:3] + format((int(random_bits[3], 16) & 0x3) | 0x8, "x") + random_bits[4:16]
    return str(uuid.UUID(hex_str))

@app.route("/")
def index():
    return "API is running", 200

@app.route("/api/profiles", methods=["POST"])
def create_profile():
    body = request.get_json(silent=True)

    if not body or "name" not in body:
        return jsonify({"status": "error", "message": "Missing or empty name"}), 400

    name = body.get("name")

    if not isinstance(name, str):
        return jsonify({"status": "error", "message": "Invalid type"}), 422

    name = name.strip()
    if not name:
        return jsonify({"status": "error", "message": "Missing or empty name"}), 400

    # Check idempotency
    existing = Profile.query.filter(db.func.lower(Profile.name) == name.lower()).first()
    if existing:
        return jsonify({
            "status": "success",
            "message": "Profile already exists",
            "data": existing.to_full_dict(),
        }), 200

    # Call external APIs
    try:
        gender_resp = requests.get(f"https://api.genderize.io?name={name}", timeout=10)
        gender_data = gender_resp.json()
    except Exception:
        return jsonify({"status": "error", "message": "Genderize returned an invalid response"}), 502

    try:
        age_resp = requests.get(f"https://api.agify.io?name={name}", timeout=10)
        age_data = age_resp.json()
    except Exception:
        return jsonify({"status": "error", "message": "Agify returned an invalid response"}), 502

    try:
        nation_resp = requests.get(f"https://api.nationalize.io?name={name}", timeout=10)
        nation_data = nation_resp.json()
    except Exception:
        return jsonify({"status": "error", "message": "Nationalize returned an invalid response"}), 502

    # Validate Genderize
    if not gender_data.get("gender") or gender_data.get("count", 0) == 0:
        return jsonify({"status": "error", "message": "Genderize returned an invalid response"}), 502

    # Validate Agify
    if age_data.get("age") is None:
        return jsonify({"status": "error", "message": "Agify returned an invalid response"}), 502

    # Validate Nationalize
    countries = nation_data.get("country", [])
    if not countries:
        return jsonify({"status": "error", "message": "Nationalize returned an invalid response"}), 502

    # Process data
    top_country = max(countries, key=lambda c: c.get("probability", 0))
    age = age_data["age"]

    profile = Profile(
        id=generate_uuid7(),
        name=name,
        gender=gender_data["gender"],
        gender_probability=gender_data["probability"],
        sample_size=gender_data["count"],
        age=age,
        age_group=classify_age(age),
        country_id=top_country["country_id"],
        country_probability=round(top_country["probability"], 2),
        created_at=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    db.session.add(profile)
    db.session.commit()

    return jsonify({"status": "success", "data": profile.to_full_dict()}), 201


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

    return jsonify({
        "status": "success",
        "count": len(profiles),
        "data": [p.to_summary_dict() for p in profiles],
    }), 200


@app.route("/api/profiles/<string:profile_id>", methods=["GET"])
def get_profile(profile_id):
    profile = Profile.query.get(profile_id)
    if not profile:
        return jsonify({"status": "error", "message": "Profile not found"}), 404
    return jsonify({"status": "success", "data": profile.to_full_dict()}), 200


@app.route("/api/profiles/<string:profile_id>", methods=["DELETE"])
def delete_profile(profile_id):
    profile = Profile.query.get(profile_id)
    if not profile:
        return jsonify({"status": "error", "message": "Profile not found"}), 404
    db.session.delete(profile)
    db.session.commit()
    return "", 204

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  
    app.run(host="0.0.0.0", port=port)
