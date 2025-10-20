from flask import Flask, render_template, request, redirect, session, url_for
import json, os

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key")

DATA_FILE = os.path.join("data", "data.json")

# ---------- Helper Functions ----------

def load():
    """Load tournament data from JSON file or create defaults."""
    if not os.path.exists(DATA_FILE):
        os.makedirs("data", exist_ok=True)
        data = {
            "max": 8,
            "mode": "single",
            "teams": [],
            "waitlist": [],
            "bracket": {"rounds": []},
            "winner": None
        }
        save(data)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save(data):
    """Save tournament data back to JSON file."""
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
def rebalance_roster(data):
    """Ensure the number of active teams matches the max limit."""
    teams = data.get("teams", [])
    waitlist = data.get("waitlist", [])
    max_teams = data.get("max", 8)

    # Case 1: Too many teams → move excess to waiting list
    if len(teams) > max_teams:
        overflow = teams[max_teams:]
        waitlist = overflow + waitlist  # preserve order (push extras first)
        teams = teams[:max_teams]

    # Case 2: Too few teams → promote from waiting list
    elif len(teams) < max_teams and waitlist:
        needed = max_teams - len(teams)
        promoted = waitlist[:needed]
        teams += promoted
        waitlist = waitlist[needed:]

    # Update and return
    data["teams"] = teams
    data["waitlist"] = waitlist
    data["bracket"] = {"rounds": []}
    data.pop("winner", None)
    return data

import random

def generate_bracket(data):
    """Create first round bracket when tournament is full."""
    teams = data.get("teams", [])
    max_teams = data.get("max", 8)

    # Only generate if not already exists and tournament full
    if len(teams) < max_teams or data.get("bracket", {}).get("rounds"):
        return data

    # Shuffle team order for fairness
    random.shuffle(teams)

    # Build first round pairings
    matches = []
    for i in range(0, len(teams), 2):
        if i + 1 < len(teams):
            matches.append({
                "team1": teams[i]["team"],
                "team2": teams[i + 1]["team"],
                "score1": None,
                "score2": None,
                "winner": None
            })
        else:
            # odd number? auto-advance last team
            matches.append({
                "team1": teams[i]["team"],
                "team2": "BYE",
                "score1": None,
                "score2": None,
                "winner": teams[i]["team"]
            })

    data["bracket"] = {"rounds": [matches]}
    save(data)
    return data

def advance_rounds(data):
    """Check completed rounds and generate next round if needed."""
    rounds = data["bracket"]["rounds"]
    last_round = rounds[-1]

    # Only advance if every match has a winner
    if not all(m.get("winner") for m in last_round):
        return data

    winners = [m["winner"] for m in last_round if m["winner"]]

    # Tournament complete
    if len(winners) == 1:
        data["winner"] = winners[0]
        return data

    # Build next round
    next_matches = []
    for i in range(0, len(winners), 2):
        if i + 1 < len(winners):
            next_matches.append({
                "team1": winners[i],
                "team2": winners[i + 1],
                "score1": None,
                "score2": None,
                "winner": None
            })
        else:
            next_matches.append({
                "team1": winners[i],
                "team2": "BYE",
                "score1": None,
                "score2": None,
                "winner": winners[i]
            })

    rounds.append(next_matches)
    data["bracket"]["rounds"] = rounds
    save(data)
    return data


# ---------- Routes ----------

@app.route("/", methods=["GET", "POST"])
def index():
    data = load()
    teams = data.get("teams", [])
    waitlist = data.get("waitlist", [])
    max_teams = data.get("max", 8)

    if request.method == "POST":
        team_name = request.form["team"].strip()
        player1 = request.form["player1"].strip()
        player2 = request.form["player2"].strip()

        if team_name:
            new_team = {"team": team_name, "players": [player1, player2]}
            if len(teams) < max_teams:
                teams.append(new_team)
            else:
                waitlist.append(new_team)

            data["teams"] = teams
            data["waitlist"] = waitlist
            save(data)
            return redirect("/")

    return render_template(
        "index.html",
        teams=teams,
        waitlist=waitlist,
        max=max_teams
    )

# ---------- Admin Login / Logout ----------

@app.route("/login", methods=["GET", "POST"])
def login():
    """Simple admin login form using environment variable ADMIN_PASSWORD."""
    if request.method == "POST":
        password = request.form["password"]
        admin_pw = os.getenv("ADMIN_PASSWORD", "admin")

        if password == admin_pw:
            session["admin"] = True
            return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    """Logout the admin."""
    session.pop("admin", None)
    return redirect(url_for("index"))

# ---------- Admin-only actions ----------

@app.route("/set_max", methods=["POST"])
def set_max():
    if not session.get("admin"):
        return redirect("/")
    data = load()
    new_max = int(request.form["max"])
    data["max"] = new_max

    # Rebalance teams and waitlist
    data = rebalance_roster(data)

    save(data)
    return redirect("/")



@app.route("/set_mode", methods=["POST"])
def set_mode():
    """Set tournament mode (single, double, group)."""
    if not session.get("admin"):
        return redirect(url_for("index"))

    mode = request.form["mode"]
    data = load()
    data["mode"] = mode
    data["bracket"] = {"rounds": []}
    data.pop("winner", None)
    save(data)
    return redirect(url_for("index"))


@app.route("/reset_bracket", methods=["POST"])
def reset_bracket():
    """Completely reset tournament bracket and winner."""
    if not session.get("admin"):
        return redirect(url_for("index"))

    data = load()
    data["bracket"] = {"rounds": []}
    data.pop("winner", None)
    save(data)
    return redirect(url_for("index"))


@app.route("/remove/<int:i>")
def remove(i):
    if not session.get("admin"):
        return redirect("/")
    data = load()
    teams = data.get("teams", [])
    waitlist = data.get("waitlist", [])

    if 0 <= i < len(teams):
        teams.pop(i)
        data["teams"] = teams
        data["waitlist"] = waitlist
        data = rebalance_roster(data)

    save(data)
    return redirect("/")

#------------ Bracket Generation ----------

@app.route("/bracket")
def bracket():
    data = load()
    data = generate_bracket(data)
    rounds = data.get("bracket", {}).get("rounds", [])

    # If still empty, tournament not full
    if not rounds:
        return render_template(
            "bracket.html",
            not_ready=True,
            max=data["max"],
            teams=len(data["teams"]),
            data=data  # ✅ added
        )

    return render_template(
        "bracket.html",
        rounds=rounds,
        not_ready=False,
        data=data  # ✅ consistent
    )


@app.route("/update_score", methods=["POST"])
def update_score():
    data = load()
    round_idx = int(request.form["round"])
    match_idx = int(request.form["match"])

    # --- Safe parsing of input ---
    try:
        score1 = int(request.form["score1"])
        score2 = int(request.form["score2"])
    except (ValueError, TypeError):
        # Ignore invalid submissions
        return redirect("/bracket")

    # Ensure non-negative integers
    if score1 < 0 or score2 < 0:
        return redirect("/bracket")

    # --- Update scores ---
    rounds = data["bracket"]["rounds"]
    match = rounds[round_idx][match_idx]
    match["score1"] = score1
    match["score2"] = score2

    # Determine winner
    if score1 > score2:
        match["winner"] = match["team1"]
    elif score2 > score1:
        match["winner"] = match["team2"]
    else:
        match["winner"] = None  # tie not allowed

    # Save + advance
    data["bracket"]["rounds"][round_idx][match_idx] = match
    data = advance_rounds(data)
    save(data)

    return redirect("/bracket")



if __name__ == "__main__":
    app.run(debug=True)
