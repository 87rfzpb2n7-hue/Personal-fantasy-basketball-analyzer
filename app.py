import html
import os
import secrets

import requests
from dotenv import load_dotenv
from flask import Flask, redirect, request, session


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

CLIENT_ID = os.getenv("YAHOO_CLIENT_ID")
CLIENT_SECRET = os.getenv("YAHOO_CLIENT_SECRET")
REDIRECT_URI = os.getenv(
    "YAHOO_REDIRECT_URI",
    "https://localhost:8080/callback",
)

AUTHORIZATION_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"

FANTASY_TEST_URL = (
    "https://fantasysports.yahooapis.com/"
    "fantasy/v2/users;use_login=1/games?format=json"
)


def configuration_error():
    missing = []

    if not CLIENT_ID:
        missing.append("YAHOO_CLIENT_ID")

    if not CLIENT_SECRET:
        missing.append("YAHOO_CLIENT_SECRET")

    if missing:
        names = ", ".join(missing)

        return f"""
        <h1>Nedostaju postavke</h1>
        <p>U datoteci <code>.env</code> nedostaje:</p>
        <p><strong>{html.escape(names)}</strong></p>
        """

    return None


@app.route("/")
def home():
    error = configuration_error()

    if error:
        return error, 500

    return """
    <h1>Yahoo Fantasy API test</h1>

    <p>
        Ova aplikacija provjerava rade li Yahoo OAuth
        i Fantasy Sports API pristup.
    </p>

    <p>
        <a href="/login">Pokreni Yahoo prijavu i test</a>
    </p>
    """


@app.route("/login")
def login():
    error = configuration_error()

    if error:
        return error, 500

    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    authorization_request = requests.Request(
        method="GET",
        url=AUTHORIZATION_URL,
        params={
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "state": state,
        },
    ).prepare()

    return redirect(authorization_request.url)


@app.route("/callback")
def callback():
    yahoo_error = request.args.get("error")

    if yahoo_error:
        description = request.args.get(
            "error_description",
            "Yahoo nije odobrio autorizaciju.",
        )

        return f"""
        <h1>Yahoo autorizacija nije uspjela</h1>
        <p><strong>Greška:</strong> {html.escape(yahoo_error)}</p>
        <p>{html.escape(description)}</p>
        """, 400

    returned_state = request.args.get("state")
    expected_state = session.pop("oauth_state", None)

    if not returned_state or returned_state != expected_state:
        return """
        <h1>OAuth sigurnosna provjera nije uspjela</h1>
        <p>Vrijednost state nije ispravna.</p>
        <p>Vrati se na početnu stranicu i pokušaj ponovno.</p>
        """, 400

    authorization_code = request.args.get("code")

    if not authorization_code:
        return """
        <h1>Nedostaje authorization code</h1>
        <p>Yahoo nije vratio potreban autorizacijski kod.</p>
        """, 400

    try:
        token_response = requests.post(
            TOKEN_URL,
            auth=(CLIENT_ID, CLIENT_SECRET),
            data={
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
                "code": authorization_code,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        return f"""
        <h1>Nije moguće kontaktirati Yahoo token servis</h1>
        <pre>{html.escape(str(exc))}</pre>
        """, 500

    if not token_response.ok:
        return f"""
        <h1>OAuth token nije dobiven</h1>
        <p><strong>HTTP status:</strong> {token_response.status_code}</p>
        <pre>{html.escape(token_response.text)}</pre>
        """, token_response.status_code

    try:
        token_data = token_response.json()
        access_token = token_data["access_token"]
    except (ValueError, KeyError):
        return f"""
        <h1>Yahoo nije vratio ispravan token</h1>
        <pre>{html.escape(token_response.text)}</pre>
        """, 500

    try:
        fantasy_response = requests.get(
            FANTASY_TEST_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        return f"""
        <h1>Nije moguće kontaktirati Fantasy API</h1>
        <pre>{html.escape(str(exc))}</pre>
        """, 500

    response_preview = html.escape(fantasy_response.text[:4000])

    if fantasy_response.status_code == 200:
        return f"""
        <h1 style="color: green;">
            Yahoo OAuth i Fantasy API rade
        </h1>

        <p><strong>Fantasy API status:</strong> 200 OK</p>

        <p>
            Yahoo aplikacija je aktivna i može čitati
            podatke tvojeg Fantasy računa.
        </p>

        <details>
            <summary>Prikaži dio odgovora Yahoo API-ja</summary>
            <pre>{response_preview}</pre>
        </details>
        """

    if fantasy_response.status_code == 403:
        return f"""
        <h1 style="color: orange;">
            OAuth radi, ali Fantasy API pristup još nije dopušten
        </h1>

        <p><strong>Fantasy API status:</strong> 403 Forbidden</p>

        <p>
            To najčešće znači da Yahoo još nije dovršio
            provisioning Fantasy Sports pristupa.
        </p>

        <pre>{response_preview}</pre>
        """, 403

    if fantasy_response.status_code == 401:
        return f"""
        <h1 style="color: red;">
            Fantasy API nije prihvatio token
        </h1>

        <p><strong>Fantasy API status:</strong> 401 Unauthorized</p>

        <pre>{response_preview}</pre>
        """, 401

    return f"""
    <h1>Yahoo API vratio je neočekivan odgovor</h1>

    <p>
        <strong>HTTP status:</strong>
        {fantasy_response.status_code}
    </p>

    <pre>{response_preview}</pre>
    """, fantasy_response.status_code


if __name__ == "__main__":
    app.run(
        host="localhost",
        port=8080,
        debug=False,
        ssl_context="adhoc",
    )
