from agent import rank_jobs
import os, sqlite3, json, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template, g
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
DATABASE = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "jobpilot.db"))
JOBVETTA_BASE_URL = "https://api.jobvetta.com/v1"

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def init_db():
    conn = sqlite3.connect(DATABASE)
    conn.execute("""CREATE TABLE IF NOT EXISTS saved_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL UNIQUE,
        title TEXT, company TEXT, location TEXT, url TEXT, job_json TEXT,
        created_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, title TEXT, company TEXT,
        status TEXT NOT NULL DEFAULT 'Interested', notes TEXT DEFAULT '',
        updated_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS profile (
        id INTEGER PRIMARY KEY CHECK (id=1), name TEXT DEFAULT '', skills TEXT DEFAULT '',
        roles TEXT DEFAULT '', locations TEXT DEFAULT '', resume_text TEXT DEFAULT '')""")
    conn.execute("INSERT OR IGNORE INTO profile(id) VALUES (1)")
    conn.commit()
    conn.close()

def api_json(url, headers=None, method="GET", payload=None, timeout=25):
    data = None
    hdrs = {"Accept": "application/json", "User-Agent": "JobPilotAI/1.0"}
    if headers:
        hdrs.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try: detail = json.loads(body)
        except Exception: detail = {"message": body[:500]}
        return {"error": "upstream_error", "status": e.code, "details": detail}, e.code
    except Exception as e:
        return {"error": "connection_error", "message": str(e)}, 502

def get_profile():
    row = db().execute("SELECT * FROM profile WHERE id=1").fetchone()
    return dict(row) if row else {}

def all_text(value):
    return str(value or "").strip()

def normalize_jobs(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("jobs", "results", "data", "items"):
            v = data.get(k)
            if isinstance(v, list): return v
            if isinstance(v, dict):
                for kk in ("jobs", "results", "items"):
                    if isinstance(v.get(kk), list): return v[kk]
    return []

def job_field(job, *keys):
    for k in keys:
        val = job.get(k)
        if val is not None and val != "":
            if isinstance(val, (str, int, float)): return str(val)
    return ""

def match_score(job, profile):
    blob = " ".join(str(job.get(k, "")) for k in ("title","description","skills","company","location","job_title","job_description")).lower()
    terms = []
    for field in ("skills", "roles", "locations"):
        terms.extend(x.strip().lower() for x in str(profile.get(field, "")).replace("\n", ",").split(",") if x.strip())
    terms = list(dict.fromkeys(terms))
    if not terms: return None
    hits = sum(1 for t in terms if t in blob)
    return min(100, round(100 * hits / max(1, min(len(terms), 8))))

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "JobPilot AI", "time": datetime.now(timezone.utc).isoformat()})

@app.get("/api/config")
def config():
    return jsonify({
        "job_api_configured": True, "job_source": "Himalayas (public API; no key required)",
        "ai_configured": bool(os.environ.get("AI_API_KEY")),
        "ai_provider": os.environ.get("AI_PROVIDER", "openai-compatible"),
        "app_name": "JobPilot AI"
    })


@app.get("/api/jobs")
def jobs_search():
    q = all_text(request.args.get("q"))
    location = all_text(request.args.get("location"))
    days = max(1, min(365, int(request.args.get("days", "30") or "30")))
    limit = max(1, min(20, int(request.args.get("limit", "10") or "10")))
    # Himalayas public API is unauthenticated; it focuses on remote roles.
    params = {"limit": limit, "page": 1, "sort": "recent"}
    if q:
        params["q"] = q
    # Only send country when user explicitly enters a country; generic city/Remote
    # values are not equivalent to the API's country filter.
    if location.lower() in ("india", "united states", "united kingdom", "canada", "australia", "germany"):
        params["country"] = location
    url = "https://himalayas.app/jobs/api/search?" + urllib.parse.urlencode(params)
    data, status = api_json(url)
    if status >= 400:
        return jsonify({"error": "himalayas_request_failed", "status": status, "details": data,
                        "hint": "The free Himalayas endpoint may be temporarily unavailable. Try again later."}), status
    found = normalize_jobs(data)
    profile = get_profile()
    output = []
    for job in found:
        if not isinstance(job, dict): continue
        jid = job_field(job, "guid", "id", "job_id", "slug", "applicationLink", "url") or str(len(output))
        title = job_field(job, "title", "jobTitle", "name") or "Untitled role"
        company = job_field(job, "companyName", "company", "company_name", "employer") or "Company not listed"
        loc = job_field(job, "location", "locationRestriction", "country") or "Remote"
        link = job_field(job, "applicationLink", "guid", "url", "jobUrl")
        # Respect API applicationLink as the apply destination and preserve source attribution.
        if link and link.startswith("/"):
            link = "https://himalayas.app" + link
        if link and not link.startswith("http"):
            link = ""
        description = job_field(job, "description", "excerpt", "summary", "jobDescription")
        output.append({
            "id": jid, "title": title, "company": company, "location": loc,
            "url": link, "description": description,
            "posted_at": job_field(job, "pubDate", "publishedAt", "postedAt", "createdAt"),
            "source": "Himalayas", "source_url": "https://himalayas.app",
            "match_score": match_score(job, profile), "raw": job
        })
    # Filter for user-provided location text locally when practical; remote API coverage is not India-wide onsite.
    if location and location.lower() not in ("remote", "worldwide", "anywhere"):
        filtered = [j for j in output if location.lower() in (j["location"] + " " + json.dumps(j["raw"], ensure_ascii=False)).lower()]
        if filtered:
            output = filtered
    return jsonify({"jobs": output, "count": len(output), "source": "Himalayas public jobs API",
                    "note": "Himalayas specializes in remote roles; listings refresh daily and may not cover onsite India jobs."})

@app.get("/api/jobs/<path:job_id>")
def job_detail(job_id):
    return jsonify({"error": "detail_endpoint_not_supported",
                    "message": "Open the source listing using the job's application link."}), 404

@app.get("/api/profile")
def profile_read():
    return jsonify(get_profile())

@app.post("/api/profile")
def profile_save():
    data = request.get_json(silent=True) or {}
    fields = {k: all_text(data.get(k)) for k in ("name", "skills", "roles", "locations", "resume_text")}
    conn = db()
    conn.execute("UPDATE profile SET name=?, skills=?, roles=?, locations=?, resume_text=? WHERE id=1",
                 (fields["name"], fields["skills"], fields["roles"], fields["locations"], fields["resume_text"]))
    conn.commit()
    return jsonify({"ok": True, "profile": get_profile()})

@app.get("/api/saved")
def saved_list():
    rows = db().execute("SELECT * FROM saved_jobs ORDER BY id DESC").fetchall()
    return jsonify({"jobs": [dict(r) for r in rows]})

@app.post("/api/saved")
def saved_add():
    data = request.get_json(silent=True) or {}
    jid = all_text(data.get("id") or data.get("job_id"))
    if not jid: return jsonify({"error": "job_id_required"}), 400
    conn = db()
    conn.execute("""INSERT INTO saved_jobs(job_id,title,company,location,url,job_json,created_at)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(job_id) DO NOTHING""",
        (jid, all_text(data.get("title")), all_text(data.get("company")), all_text(data.get("location")),
         all_text(data.get("url")), json.dumps(data, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
    conn.commit()
    return jsonify({"ok": True})

@app.delete("/api/saved/<path:job_id>")
def saved_delete(job_id):
    db().execute("DELETE FROM saved_jobs WHERE job_id=?", (job_id,))
    db().commit()
    return jsonify({"ok": True})

@app.get("/api/applications")
def applications_list():
    rows = db().execute("SELECT * FROM applications ORDER BY updated_at DESC").fetchall()
    return jsonify({"applications": [dict(r) for r in rows]})

@app.post("/api/applications")
def applications_add():
    data = request.get_json(silent=True) or {}
    title = all_text(data.get("title"))
    if not title: return jsonify({"error": "title_required"}), 400
    conn = db()
    conn.execute("INSERT INTO applications(job_id,title,company,status,notes,updated_at) VALUES(?,?,?,?,?,?)",
        (all_text(data.get("job_id")), title, all_text(data.get("company")),
         all_text(data.get("status")) or "Interested", all_text(data.get("notes")), datetime.now(timezone.utc).isoformat()))
    conn.commit()
    return jsonify({"ok": True})

@app.patch("/api/applications/<int:app_id>")
def applications_update(app_id):
    data = request.get_json(silent=True) or {}
    allowed = {"Interested", "Applied", "Interview", "Offer", "Rejected", "Withdrawn"}
    status = all_text(data.get("status"))
    if status and status not in allowed: return jsonify({"error": "invalid_status"}), 400
    conn = db()
    row = conn.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    if not row: return jsonify({"error": "not_found"}), 404
    conn.execute("UPDATE applications SET status=?, notes=?, updated_at=? WHERE id=?",
        (status or row["status"], all_text(data.get("notes", row["notes"])), datetime.now(timezone.utc).isoformat(), app_id))
    conn.commit()
    return jsonify({"ok": True})

@app.delete("/api/applications/<int:app_id>")
def applications_delete(app_id):
    db().execute("DELETE FROM applications WHERE id=?", (app_id,))
    db().commit()
    return jsonify({"ok": True})

def chatbot_reply(message, context):
    api_key = os.environ.get("AI_API_KEY", "").strip()
    if not api_key:
        return {"reply": "The AI provider is not configured yet. Add AI_API_KEY and AI_BASE_URL in the server environment. I can still help with live job search once JOBVETTA_API_KEY is configured.", "mode": "setup"}
    base = os.environ.get("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("AI_MODEL", "gpt-4o-mini")
    profile = get_profile()
    system = (
      "You are JobPilot AI, a practical job-search assistant. Help with job search strategy, resume improvement, "
      "job-match explanations, interview preparation, and application email drafts. Never claim you applied for a job, "
      "sent an email, or verified a listing unless the system actually did so. Do not invent candidate experience. "
      "Ask for missing facts. Keep answers clear and actionable. User profile JSON: " + json.dumps(profile, ensure_ascii=False) +
      ". Context from current screen: " + json.dumps(context or {}, ensure_ascii=False)[:5000]
    )
    payload = {"model": model, "messages": [{"role":"system","content":system},{"role":"user","content":message}],
               "temperature":0.4}
    data, status = api_json(base + "/chat/completions", {"Authorization":"Bearer " + api_key}, "POST", payload, 45)
    if status >= 400:
        return {"reply": "AI provider request failed (HTTP " + str(status) + "). Check AI_BASE_URL, AI_MODEL, API key, and provider billing/limits. Details: " + json.dumps(data)[:500], "mode":"error"}
    choices = data.get("choices", [])
    reply = choices[0].get("message", {}).get("content", "") if choices else ""
    return {"reply": reply or "I could not generate a response. Please try again.", "mode":"live"}

@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    message = all_text(data.get("message"))
    if not message: return jsonify({"error":"message_required"}), 400
    if len(message) > 6000: return jsonify({"error":"message_too_long"}), 413
    return jsonify(chatbot_reply(message, data.get("context", {})))

@app.get("/api/agent/search")
def agent_search():
    query = all_text(request.args.get("q"))
    limit = max(1, min(20, int(request.args.get("limit", "10") or "10")))

    params = {"limit": limit, "page": 1, "sort": "recent"}
    if query:
        params["q"] = query

    url = "https://himalayas.app/jobs/api/search?" + urllib.parse.urlencode(params)
    data, status = api_json(url)

    if status >= 400:
        return jsonify({
            "error": "job_source_unavailable",
            "message": "Could not fetch jobs. Please try again later."
        }), 502

    profile = get_profile()
    jobs = []

    for job in normalize_jobs(data):
        if not isinstance(job, dict):
            continue

        job_id = job_field(job, "guid", "id", "job_id", "slug", "url")
        title = job_field(job, "title", "jobTitle", "name") or "Untitled role"
        company = job_field(job, "companyName", "company", "company_name", "employer") or "Company not listed"
        location = job_field(job, "location", "locationRestriction", "country") or "Remote"
        description = job_field(job, "description", "excerpt", "summary", "jobDescription")

        link = job_field(job, "applicationLink", "url", "jobUrl")
        if link.startswith("/"):
            link = "https://himalayas.app" + link
        if not link.startswith("https://") and not link.startswith("http://"):
            link = ""

        jobs.append({
            "id": job_id,
            "title": title,
            "company": company,
            "location": location,
            "description": description,
            "url": link
        })

    ranked_jobs = rank_jobs(jobs, profile)

    return jsonify({
        "agent": "JobPilot AI",
        "task": "job_search_and_matching",
        "query": query,
        "count": len(ranked_jobs),
        "jobs": ranked_jobs,
        "source": "Himalayas public jobs API",
        "note": "Match scores are keyword-based estimates, not hiring probabilities."
    })

@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error":"request_too_large"}), 413

init_db()
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
