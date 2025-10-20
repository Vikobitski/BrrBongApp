from flask import Flask, render_template, request, redirect, session
import os, json, random, math

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_secret")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

DATA = os.path.join("data", "data.json")

# ---------- Helpers ----------
def load():
    if not os.path.exists(DATA):
        os.makedirs(os.path.dirname(DATA), exist_ok=True)
        with open(DATA, "w") as f:
            json.dump({
                "teams": [],
                "waitlist": [],
                "max": 8,
                "results": {},
                "mode": "single",
                "brackets": {}
            }, f, indent=2)
    with open(DATA) as f:
        return json.load(f)


def save(d):
    with open(DATA, "w") as f:
        json.dump(d, f, indent=2)


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
                # Add to active teams
                teams.append(new_team)
            else:
                # Add to waiting list
                waitlist.append(new_team)

            # Always reset bracket when teams change
            data["teams"] = teams
            data["waitlist"] = waitlist
            data["bracket"] = {"rounds": []}
            data.pop("winner", None)
            data["team_signature"] = ",".join(sorted([t["team"] for t in teams]))
            save(data)
            return redirect("/")

    return render_template(
        "index.html",
        teams=teams,
        waitlist=waitlist,
        admin=session.get("admin"),
        max=max_teams,
        full=(len(teams) >= max_teams),
        mode=data.get("mode", "single")
    )



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

@app.route("/remove/<int:i>")
def remove(i):
    if not session.get("admin"):
        return redirect("/")
    data = load()
    teams = data.get("teams", [])
    waitlist = data.get("waitlist", [])

    if 0 <= i < len(teams):
        teams.pop(i)
        # promote from waiting list
        if waitlist:
            promoted = waitlist.pop(0)
            teams.append(promoted)

    data["teams"] = teams
    data["waitlist"] = waitlist
    # reset bracket & winner when team list changes
    data["bracket"] = {"rounds": []}
    data.pop("winner", None)
    data["team_signature"] = ",".join(sorted([t["team"] for t in teams]))
    save(data)
    return redirect("/")


@app.route("/set_limit", methods=["POST"])
def set_limit():
    if not session.get("admin"):
        return redirect("/")
    d = load()
    d["max"] = max(2, int(request.form["max"]))
    save(d)
    return redirect("/")


@app.route("/set_mode", methods=["POST"])
def set_mode():
    if not session.get("admin"):
        return redirect("/")
    d = load()
    d["mode"] = request.form["mode"]
    save(d)
    return redirect("/")


# ---------- Bracket ----------
@app.route("/bracket", methods=["GET", "POST"])
def bracket():
    data = load()
    teams = data["teams"]
    max_teams = data["max"]
    mode = data.get("mode", "single")
    bracket = data.get("bracket", {"rounds": []})
    team_signature = ",".join(sorted([t["team"] for t in teams]))

    # 🟡 Detect if bracket should be reset
    if data.get("team_signature") != team_signature:
        # Reset bracket and winner if teams changed
        data["bracket"] = {"rounds": []}
        data.pop("winner", None)
        data["team_signature"] = team_signature
        bracket = data["bracket"]
        save(data)

    # Require full registration before showing bracket
    if len(teams) < max_teams:
        return render_template(
            "bracket.html",
            not_ready=True,
            mode=mode,
            teams=teams,
            max=max_teams,
            rounds=[]
        )


    # 2️⃣ Initialize bracket once
    if not bracket["rounds"]:
        shuffled = teams.copy()
        random.shuffle(shuffled)

        first_round = []
        for i in range(0, len(shuffled), 2):
            t1 = shuffled[i]["team"]
            t2 = shuffled[i + 1]["team"] if i + 1 < len(shuffled) else "BYE"
            first_round.append({
                "id": f"R1M{i//2+1}",
                "team1": t1,
                "team2": t2,
                "score1": "",
                "score2": ""
            })

        total_rounds = math.ceil(math.log2(max_teams))
        rounds = [first_round]

        # create empty next rounds
        for r in range(1, total_rounds):
            matches_in_round = max_teams // (2 ** (r + 1))
            rounds.append([
                {"id": f"R{r+1}M{m+1}", "team1": "", "team2": "", "score1": "", "score2": ""}
                for m in range(matches_in_round)
            ])

        bracket["rounds"] = rounds
        data["bracket"] = bracket
        save(data)

    # 3️⃣ Handle score updates and auto-advance
    if request.method == "POST":
        match_id = request.form["match_id"]
        score1 = request.form["score1"].strip()
        score2 = request.form["score2"].strip()

        # iterate over rounds
        for rnd_index, rnd in enumerate(bracket["rounds"]):
            for match_idx, match in enumerate(rnd):
                if match["id"] == match_id:
                    match["score1"] = score1
                    match["score2"] = score2

                    # only advance if both scores valid numbers
                    if score1.isdigit() and score2.isdigit():
                        s1, s2 = int(score1), int(score2)
                        if s1 == s2:
                            continue  # no tie handling for now

                        winner = match["team1"] if s1 > s2 else match["team2"]

                        # advance to next round if possible
                        if rnd_index + 1 < len(bracket["rounds"]):
                            next_round = bracket["rounds"][rnd_index + 1]
                            next_slot = match_idx // 2

                            # clear old data and assign winner properly
                            if next_round[next_slot]["team1"] == "":
                                next_round[next_slot]["team1"] = winner
                            elif next_round[next_slot]["team2"] == "":
                                next_round[next_slot]["team2"] = winner
                            else:
                                # overwrite slot completely (in case of resave)
                                next_round[next_slot]["team1"] = winner
                                next_round[next_slot]["team2"] = ""
                        else:
                            # final round → winner of tournament
                            data["winner"] = winner

                    break

        data["bracket"] = bracket
        save(data)
        return redirect("/bracket")

    return render_template(
        "bracket.html",
        not_ready=False,
        mode=mode,
        rounds=bracket["rounds"],
        teams=teams,
        max=max_teams,
        winner=data.get("winner")
    )


if __name__ == "__main__":
    app.run(debug=True)
