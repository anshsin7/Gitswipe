#!/usr/bin/env python3
import json, os, webbrowser, threading
import requests
from pathlib import Path
from urllib.parse import urlencode
from flask import Flask, render_template, jsonify, request, session as flask_session, redirect
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"

GH_CLIENT_ID     = os.getenv("GITHUB_CLIENT_ID", "")
GH_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")

# fallback read-only token for searching/fetching profiles (no user scope needed)
GH_TOKEN = os.getenv("GITHUB_TOKEN", "")
GH_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
if GH_TOKEN:
    GH_HEADERS["Authorization"] = f"Bearer {GH_TOKEN}"

def user_headers():
    """Headers using the logged-in user's token, falling back to app token."""
    token = flask_session.get("gh_token") or GH_TOKEN
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h

session = {"usernames": [], "criteria": [], "cache": {}, "evaluations": {}, "accepted": []}


# ── helpers ──────────────────────────────────────────────────────────────────

def llm(messages):
    r = client.chat.completions.create(
        model=MODEL, messages=messages, temperature=0.3,
        response_format={"type": "json_object"},
    )
    return json.loads(r.choices[0].message.content)


def gh(url, params=None):
    r = requests.get(url, headers=GH_HEADERS, params=params, timeout=10)
    if r.status_code == 403 and "rate limit" in r.text.lower():
        raise RuntimeError("GitHub rate limit hit — add a GITHUB_TOKEN to your .env to get 5000 req/hr instead of 60.")
    if r.status_code == 422:
        raise RuntimeError("GitHub rejected the search query. Try simpler criteria.")
    r.raise_for_status()
    return r.json()


def build_query(criteria: list[str]) -> str:
    data = llm([
        {"role": "system", "content": (
            "Convert user networking criteria into a GitHub user search query string.\n"
            "GitHub supports: location:city, language:python, followers:>N, repos:>N, 'keyword' in:bio\n"
            "Return JSON: {\"query\": \"...\", \"explanation\": \"...\"}\n"
            "Keep it broad enough to return results. Max 3 filters."
        )},
        {"role": "user", "content": f"Criteria:\n{json.dumps(criteria)}"},
    ])
    return data.get("query", " ".join(criteria[:2]))


def fetch_profile(username: str) -> dict:
    if username in session["cache"]:
        return session["cache"][username]

    user = gh(f"https://api.github.com/users/{username}")

    try:
        repos_raw = gh(
            f"https://api.github.com/users/{username}/repos",
            params={"sort": "stars", "per_page": 6, "type": "owner"},
        )
        repos = [
            {
                "name": r["name"],
                "description": (r.get("description") or "")[:120],
                "stars": r["stargazers_count"],
                "language": r.get("language") or "",
                "topics": (r.get("topics") or [])[:4],
                "url": r["html_url"],
            }
            for r in repos_raw if not r["fork"]
        ][:3]
    except Exception:
        repos = []

    blog = (user.get("blog") or "").strip()
    if blog and not blog.startswith("http"):
        blog = "https://" + blog

    profile = {
        "username": username,
        "name": (user.get("name") or username).strip(),
        "bio": (user.get("bio") or "").strip(),
        "company": (user.get("company") or "").strip().lstrip("@"),
        "location": (user.get("location") or "").strip(),
        "avatar_url": user.get("avatar_url", ""),
        "github_url": user.get("html_url", f"https://github.com/{username}"),
        "blog": blog,
        "email": (user.get("email") or "").strip(),
        "twitter": (user.get("twitter_username") or "").strip(),
        "followers": user.get("followers", 0),
        "public_repos": user.get("public_repos", 0),
        "repos": repos,
    }
    session["cache"][username] = profile
    return profile


def evaluate(profile: dict, criteria: list[str], idx: int) -> dict:
    if idx in session["evaluations"]:
        return session["evaluations"][idx]

    repos_text = "\n".join(
        f"  - {r['name']} (★{r['stars']}, {r['language']}): {r['description']}"
        for r in profile.get("repos", [])
    ) or "  No notable public repos"

    data = llm([
        {"role": "system", "content": "Evaluate GitHub profiles for professional networking. Return only valid JSON."},
        {"role": "user", "content": f"""Criteria:
{json.dumps(criteria, indent=2)}

GitHub Profile:
  Name: {profile['name']} (@{profile['username']})
  Bio: {profile['bio'] or 'No bio'}
  Company: {profile['company'] or '—'}
  Location: {profile['location'] or '—'}
  Followers: {profile['followers']}
  Top repos:
{repos_text}

Return JSON:
  verdict       – "strong_match" | "possible_match" | "weak_match"
  fit_score     – integer 0-100
  summary       – 2 concrete sentences about who this person is technically
  reasons       – array of 2-3 short strings explaining the score
  note          – 1 personalized GitHub/LinkedIn connection message <220 chars, mention a specific repo"""},
    ])
    session["evaluations"][idx] = data
    return data


# ── routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search", methods=["POST"])
def search():
    body = request.json
    criteria = [s.strip() for s in body.get("criteria", []) if s.strip()]
    if not criteria:
        return jsonify({"error": "No criteria provided"}), 400

    session.update({"criteria": criteria, "evaluations": {}, "accepted": [], "cache": {}})

    query = build_query(criteria)
    data = gh("https://api.github.com/search/users",
              params={"q": query, "per_page": 30, "sort": "followers"})

    session["usernames"] = [u["login"] for u in data.get("items", [])]
    return jsonify({"total": len(session["usernames"]), "query": query})


@app.route("/api/profile/<int:idx>")
def get_profile(idx):
    if idx >= len(session["usernames"]):
        return jsonify({"done": True})
    try:
        profile = fetch_profile(session["usernames"][idx])
        ev = evaluate(profile, session["criteria"], idx)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"index": idx, "total": len(session["usernames"]),
                    "profile": profile, "evaluation": ev, "done": False})


@app.route("/api/decide", methods=["POST"])
def decide():
    body = request.json
    idx, decision = body.get("index"), body.get("decision")
    if decision == "yes" and idx < len(session["usernames"]):
        uname = session["usernames"][idx]
        p = session["cache"].get(uname, {})
        ev = session["evaluations"].get(idx, {})
        session["accepted"].append({
            "name": p.get("name"), "username": uname,
            "github_url": p.get("github_url"),
            "avatar_url": p.get("avatar_url"),
            "fit_score": ev.get("fit_score"),
            "summary": ev.get("summary"),
            "connection_note": ev.get("note"),
        })
    return jsonify({"accepted": len(session["accepted"])})


@app.route("/auth/login")
def auth_login():
    if not GH_CLIENT_ID:
        return "GITHUB_CLIENT_ID not set in .env", 500
    params = urlencode({"client_id": GH_CLIENT_ID, "scope": "user:follow"})
    return redirect(f"https://github.com/login/oauth/authorize?{params}")


@app.route("/auth/callback")
def auth_callback():
    code = request.args.get("code")
    if not code:
        return redirect("/")
    r = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={"client_id": GH_CLIENT_ID, "client_secret": GH_CLIENT_SECRET, "code": code},
        timeout=10,
    )
    token = r.json().get("access_token")
    if token:
        flask_session["gh_token"] = token
        me = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            timeout=10,
        ).json()
        flask_session["gh_user"] = {
            "login":      me.get("login"),
            "name":       me.get("name") or me.get("login"),
            "avatar_url": me.get("avatar_url"),
        }
    return redirect("/")


@app.route("/auth/logout")
def auth_logout():
    flask_session.pop("gh_token", None)
    flask_session.pop("gh_user", None)
    return redirect("/")


@app.route("/api/me")
def api_me():
    user = flask_session.get("gh_user")
    return jsonify({"logged_in": bool(user), "user": user})


@app.route("/api/follow/<username>", methods=["POST"])
def follow_user(username):
    token = flask_session.get("gh_token")
    if not token:
        return jsonify({"error": "not_logged_in"}), 401
    r = requests.put(
        f"https://api.github.com/user/following/{username}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
        timeout=10,
    )
    if r.status_code == 204:
        return jsonify({"ok": True})
    if r.status_code in (401, 403):
        return jsonify({"error": "Session expired — please log in again"}), 403
    return jsonify({"error": f"GitHub error {r.status_code}"}), 500


@app.route("/api/email/<username>")
def find_email(username):
    # 1. profile email
    profile = session["cache"].get(username, {})
    if profile.get("email"):
        return jsonify({"email": profile["email"], "source": "profile"})
    # 2. scan recent commit authors
    try:
        repos_raw = gh(
            f"https://api.github.com/users/{username}/repos",
            params={"sort": "pushed", "per_page": 5, "type": "owner"},
        )
        for repo in repos_raw[:4]:
            commits = gh(
                f"https://api.github.com/repos/{username}/{repo['name']}/commits",
                params={"author": username, "per_page": 1},
            )
            if commits:
                email = commits[0].get("commit", {}).get("author", {}).get("email", "")
                if email and "@" in email and "noreply" not in email and "users.noreply" not in email:
                    return jsonify({"email": email, "source": "commits"})
    except Exception:
        pass
    return jsonify({"email": None})


@app.route("/api/results")
def results():
    return jsonify(session["accepted"])


@app.route("/api/save")
def save():
    p = Path("accepted_profiles.json")
    p.write_text(json.dumps(session["accepted"], indent=2), encoding="utf-8")
    return jsonify({"saved_to": str(p), "count": len(session["accepted"])})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)
