import threading, logging, os, sys
sys.path.insert(0, os.path.dirname(__file__))

from flask import (Flask, render_template, jsonify,
                   request, redirect, url_for, flash)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)

from modules.data_fetcher    import (init_db, seed_demo_data, run_fetcher_loop,
                                      get_latest_prices, get_historical,
                                      get_all_historical, COINS)
from modules.anomaly_detector import run_full_analysis, get_anomaly_summary, analyse_coin
from modules.graph_miner      import run_graph_analysis
from modules.alert_system     import generate_alerts, get_alerts, get_alert_stats
from modules.auth             import (init_user_tables, get_user_by_id,
                                      get_user_by_username, get_user_by_email,
                                      register_user, update_profile,
                                      get_all_users, delete_user, get_user_stats)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "cryptopulse-secret-key-change-in-production-2025"

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access CryptoPulse."
login_manager.login_message_category = "info"

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(int(user_id))

TRACKED_COINS = [
    ("bitcoin","BTC"),("ethereum","ETH"),("binancecoin","BNB"),
    ("solana","SOL"),("ripple","XRP"),("dogecoin","DOGE"),
    ("cardano","ADA"),("avalanche-2","AVAX"),("chainlink","LINK"),
    ("polkadot","DOT"),
]

def _start_background_fetcher():
    t = threading.Thread(target=run_fetcher_loop, args=(45,), daemon=True)
    t.start()

# ── Auth routes ────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        identifier = request.form.get("identifier","").strip()
        password   = request.form.get("password","")
        remember   = bool(request.form.get("remember"))
        user = get_user_by_username(identifier) or get_user_by_email(identifier)
        if user and user.check_password(password):
            login_user(user, remember=remember)
            return redirect(request.args.get("next") or url_for("index"))
        error = "Invalid username / email or password."
    return render_template("auth/login.html", error=error)

@app.route("/signup", methods=["GET","POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username  = request.form.get("username","").strip()
        email     = request.form.get("email","").strip()
        password  = request.form.get("password","")
        password2 = request.form.get("password2","")
        if password != password2:
            error = "Passwords do not match."
        elif len(username) < 3:
            error = "Username must be at least 3 characters."
        else:
            user, err = register_user(username, email, password)
            if err:
                error = err
            else:
                login_user(user)
                return redirect(url_for("index"))
    return render_template("auth/signup.html", error=error)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/profile", methods=["GET","POST"])
@login_required
def profile():
    message = None; msg_type = "success"
    if request.method == "POST":
        action = request.form.get("action","")
        if action == "update_profile":
            ok, msg = update_profile(
                current_user.id,
                display_name = request.form.get("username","").strip() or None,
                email        = request.form.get("email","").strip() or None,
                watchlist    = request.form.get("watchlist",""),
                alert_email  = bool(request.form.get("alert_email")),
            )
            message, msg_type = msg, "success" if ok else "error"
        elif action == "change_password":
            ok, msg = update_profile(
                current_user.id,
                current_password = request.form.get("current_password",""),
                new_password     = request.form.get("new_password",""),
            )
            message, msg_type = msg, "success" if ok else "error"
    user = get_user_by_id(current_user.id)
    return render_template("auth/profile.html", user=user, tracked=TRACKED_COINS,
                           message=message, msg_type=msg_type)

@app.route("/admin")
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash("Access denied.", "error"); return redirect(url_for("index"))
    return render_template("auth/admin.html",
        users=get_all_users(), user_stats=get_user_stats(),
        alert_stats=get_alert_stats(), latest=get_latest_prices(),
        tracked=TRACKED_COINS)

@app.route("/admin/delete_user/<int:uid>", methods=["POST"])
@login_required
def admin_delete_user(uid):
    if not current_user.is_admin: return jsonify({"error":"Forbidden"}),403
    if uid == current_user.id:    return jsonify({"error":"Cannot delete yourself"}),400
    delete_user(uid); return jsonify({"ok":True})

# ── Dashboard routes (protected) ───────────────────────────────────────────────
@app.route("/")
@login_required
def index():
    return render_template("index.html",
        latest=get_latest_prices(), stats=get_alert_stats(),
        top_alerts=get_alerts(limit=5), tracked=TRACKED_COINS)

@app.route("/live")
@login_required
def live():
    return render_template("live.html", tracked=TRACKED_COINS)

@app.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html", tracked=TRACKED_COINS,
                           selected_coin=request.args.get("coin","bitcoin"))

@app.route("/alerts")
@login_required
def alerts_page():
    severity = request.args.get("severity")
    return render_template("alerts.html", alerts=get_alerts(200, severity),
                           stats=get_alert_stats(), severity=severity)

# ── JSON API (protected) ────────────────────────────────────────────────────────

@app.route("/api/live")
@login_required
def api_live(): return jsonify(get_latest_prices())

@app.route("/api/historical/<coin_id>")
@login_required
def api_historical(coin_id):
    return jsonify(get_historical(coin_id, int(request.args.get("limit",60))))

@app.route("/api/anomalies")
@login_required
def api_anomalies():
    r = run_full_analysis(TRACKED_COINS); generate_alerts(r); return jsonify(r)

@app.route("/api/anomalies/<coin_id>")
@login_required
def api_anomalies_coin(coin_id):
    sym = next((s for cid,s in TRACKED_COINS if cid==coin_id), coin_id.upper())
    return jsonify(analyse_coin(coin_id, sym))

@app.route("/api/graph")
@login_required
def api_graph(): return jsonify(run_graph_analysis(TRACKED_COINS))

@app.route("/api/alerts")
@login_required
def api_alerts():
    return jsonify({"alerts": get_alerts(int(request.args.get("limit",50)),
                                         request.args.get("severity")),
                    "stats":  get_alert_stats()})

@app.route("/api/summary")
@login_required
def api_summary():
    return jsonify({"latest_prices": get_latest_prices(),
                    "alert_stats":   get_alert_stats(),
                    "anomaly_summary": get_anomaly_summary(TRACKED_COINS)})

@app.route("/api/watchlist", methods=["GET","POST"])
@login_required
def api_watchlist():
    if request.method == "POST":
        d = request.get_json(force=True)
        update_profile(current_user.id, watchlist=",".join(d.get("coins",[])))
        return jsonify({"ok":True})
    return jsonify({"watchlist": current_user.watchlist_list})

if __name__ == "__main__":
    init_db(); init_user_tables(); seed_demo_data()
    try:
        generate_alerts(run_full_analysis(TRACKED_COINS))
    except Exception as e:
        logger.warning("Initial analysis: %s", e)
    _start_background_fetcher()
    app.run(debug=False, host="0.0.0.0", port=5000, use_reloader=False)
