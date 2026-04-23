# HNG Gender Classification & Profile Intelligence API

This project implements a robust gender, age, and nationality profile intelligence engine. It supports classification, advanced filtering, search, data ingestion from external APIs, and natural language query interpretation. Built with Python and Flask for the HNG backend task.

---

## Features

- **/api/classify** – Classifies name gender using Genderize API
- **/api/profiles** – Full CRUD for person profiles, with:
  - Advanced query filtering
  - Sorting and pagination
  - Automated data seeding from JSON
- **/api/profiles/search** – Natural language-to-query translation
- **Reliable input validation and standardized error responses**
- **Performance-aware: Efficient with large datasets and supports SQLAlchemy query logging**
- **CORS enabled (`Access-Control-Allow-Origin: *`)**
- **Full country code mapping with clean modularization**
- **All timestamps are returned in UTC ISO 8601 format**
- **All profile IDs are UUIDv7**

---

## Tech Stack

- **Language/Framework**: Python 3, Flask, Flask-CORS, Flask-SQLAlchemy
- **HTTP library**: Requests (for external API calls)
- **Database**: SQLite (default, swap as needed)
- **Data model**: SQLAlchemy ORM

---

## Data Model

**Profile Table**
| Field                  | Type       | Notes                      |
|------------------------|------------|----------------------------|
| id                     | UUIDv7     | Primary key                |
| name                   | VARCHAR    | Unique, full name          |
| gender                 | VARCHAR    | 'male' or 'female'         |
| gender_probability     | FLOAT      | Genderize confidence score |
| sample_size            | INT        | Genderize count            |
| age                    | INT        | Agify age                  |
| age_group              | VARCHAR    | child, teenager, adult, senior |
| country_id             | VARCHAR(2) | ISO 3166                      |
| country_name           | VARCHAR    | Full country name              |
| country_probability    | FLOAT      | Nationalize confidence         |
| created_at             | TIMESTAMP  | UTC ISO 8601                  |

---

## Setup

1. **Clone the repository**

    ```bash
    git clone <repo_url>
    cd <repo_folder>
    ```

2. **Install dependencies**

    ```bash
    pip install -r requirements.txt
    ```

3. **Place a seed JSON**

    Place your `seed_profiles.json` (2026 profiles, matching schema) in the root directory.

4. **Run the application**

    ```bash
    python app.py
    ```
    - By default, will use SQLite at `/tmp/profiles.db`
    - The seed runs automatically the first time if empty (no duplicates)
    - App listens on port `8000` by default (`PORT` env variable is respected)

---

## API Endpoints

### 1. **Classify Name Gender**

- **Endpoint:** `GET /api/classify?name=<Name>`
- **Description:** Calls the Genderize API and returns the gender, its probability, and sample size. Adds `is_confident` and the server processing timestamp.

- **Sample Success Response:**
    ```json
    {
      "status": "success",
      "data": {
        "name": "Joy",
        "gender": "female",
        "probability": 0.99,
        "sample_size": 1234,
        "is_confident": true,
        "processed_at": "2026-04-16T12:00:00Z"
      }
    }
    ```

- **Sample Error Response:**
    ```json
    {
      "status": "error",
      "message": "Name query parameter is required"
    }
    ```

### 2. **Profiles (CRUD, Filter, Sort, Pagination)**

- **Endpoint:** `GET /api/profiles`
- **Query Parameters:**
    - `gender`, `age_group`, `country_id`
    - `min_age`, `max_age`
    - `min_gender_probability`, `min_country_probability`
    - `sort_by` (`age`, `created_at`, `gender_probability`)
    - `order` (`asc`, `desc`)
    - `page` (default: 1)
    - `limit` (default: 10, max: 50)
- **Sample Request:**  
    `/api/profiles?gender=male&country_id=NG&min_age=25&sort_by=age&order=desc&page=2&limit=10`
- **Response:**
    ```json
    {
      "status": "success",
      "page": 2,
      "limit": 10,
      "total": 2026,
      "count": 10,
      "data": [
        {
          "id": "...",
          "name": "...",
          "gender": "...",
          "age": ...,
          "age_group": "...",
          "country_id": "..."
        }
        // ...
      ]
    }
    ```

- **Error Response:**  
    Returns a standardized error structure for invalid filters or unknown query params.

### 3. **Profile Details**

- **Endpoint:** `GET /api/profiles/<profile_id>`
- **Returns:** The full data for the specific profile or 404 if not found.

### 4. **Delete Profile**

- **Endpoint:** `DELETE /api/profiles/<profile_id>`
- **Effect:** Removes the profile if it exists.

### 5. **Natural Language Search**

- **Endpoint:** `GET /api/profiles/search?q=young males from angola`
- **Behavior:** Automatic, rule-based translation of English queries to filters.
    - e.g., `"young males from nigeria"` → `gender=male + min_age=16 + max_age=24 + country_id=NG`
- **Supports pagination via `page` and `limit`.**

- **Error:**  
    ```json
    { "status": "error", "message": "Unable to interpret query" }
    ```

---

## Sample Usage

**List all adult females in Kenya, sorted by age, descending:**
```
GET /api/profiles?gender=female&age_group=adult&country_id=KE&sort_by=age&order=desc
```

**Natural query for teenage males in Brazil:**
```
GET /api/profiles/search?q=male teenagers from brazil
```

---

## Project Structure

```
app.py                # Main Flask application
countries.py          # ISO 3166-1 alpha-2 country mapping
seed_profiles.json    # [You must supply] Profile seed data file (2026 records)
requirements.txt      # Python dependencies
README.md             # Project documentation (this file)
```

---

## Error Handling

All errors return:
```json
{ "status": "error", "message": "<message>" }
```
with appropriate HTTP status codes (`400`, `404`, `422`, `500`).

---

## CORS Policy

*All* responses include:  
`Access-Control-Allow-Origin: *`

---

## AI Usage Declaration

AI tools were used strictly as a research and code clarification assistant:
- For understanding Flask route structure
- For validation logic and error handling advice  
**All implementation, bugfixes, and testing were performed manually.**

---

## License

[MIT License](LICENSE)

---

## Acknowledgments

- [Genderize.io](https://genderize.io), [Agify.io](https://agify.io), [Nationalize.io](https://nationalize.io) API teams
- [ISO country code list](https://en.wikipedia.org/wiki/List_of_ISO_3166_country_codes)
