from flask import Flask, render_template, request, redirect, session
import os, json, random
import os

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_secret")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

DATA = "data.json"

# ---------- helpers ----------
def load():
    if not os.path.exists(DATA):
        with open(DATA, "w") as f:
            json.dump({"teams": [], "waitlist": [], "max": 8, "results": {}}, f)
    with open(DATA) as f:
        return json.load(f)

def save(d):
    with open(DATA, "w") as f:
        json.dump(d, f, indent=2)

# ---------- public ----------
@app.route("/", methods=["GET", "POST"])
def index():
    d = load()
    teams = d["teams"]
    waitlist = d.get("waitlist", [])
    if request.method == "POST":
        name = request.form["team"].strip()
        # enforce limit
        if len(teams) < d["max"]:
            teams.append(name)
        else:
            waitlist.append(name)
        d["waitlist"] = waitlist
        save(d)
        return redirect("/")
    full = len(teams) >= d["max"]
    return render_template(
        "index.html",
        teams=teams,
        waitlist=waitlist,
        full=full,
        admin=session.get("admin"),
        max=d["max"]
    )

# ---------- admin-only actions ----------
@app.route("/remove/<int:i>")
def remove(i):
    if not session.get("admin"):
        return redirect("/")
    d = load()
    teams = d["teams"]
    waitlist = d.get("waitlist", [])
    if 0 <= i < len(teams):
        teams.pop(i)
        # promote next waiting team
        if waitlist:
            promoted = waitlist.pop(0)
            teams.append(promoted)
        d["teams"], d["waitlist"] = teams, waitlist
        save(d)
    return redirect("/")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["password"] == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/")
        return render_template("login.html", error="Wrong password!")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect("/")

@app.route("/set_limit", methods=["POST"])
def set_limit():
    if not session.get("admin"):
        return redirect("/")
    d = load()
    new_limit = max(2, int(request.form["max"]))
    d["max"] = new_limit
    save(d)
    return redirect("/")

@app.route("/clear")
def clear():
    if not session.get("admin"):
        return redirect("/")
    save({"teams": [], "waitlist": [], "max": load()["max"], "results": {}})
    return redirect("/")

# ---------- bracket ----------
@app.route("/bracket", methods=["GET", "POST"])
def bracket():
    data = load()
    teams = data["teams"][: data["max"]]
    results = data.get("results", {})

    # --- Handle one-match POST ---
    if request.method == "POST":
        match_id = request.form["match_id"]
        score1 = request.form["score1"]
        score2 = request.form["score2"]
        results[match_id] = [score1, score2]
        data["results"] = results
        save(data)
        return redirect("/bracket")

    # --- Build matches ---
    if len(teams) < 2:
        return render_template("bracket.html", matches=[], not_enough=True)

    if len(teams) % 2:
        teams.append("BYE")

    random.shuffle(teams)
    matches = []
    for i in range(0, len(teams), 2):
        match_id = str(i // 2 + 1)
        score = results.get(match_id, ["", ""])
        matches.append({
            "id": match_id,
            "team1": teams[i],
            "team2": teams[i + 1],
            "score1": score[0],
            "score2": score[1]
        })

    return render_template("bracket.html", matches=matches, not_enough=False)

if __name__ == "__main__":
    app.run(debug=True)
