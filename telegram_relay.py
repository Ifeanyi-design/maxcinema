import os

import requests
from flask import Flask, jsonify, request


app = Flask(__name__)


@app.post("/telegram/send")
def send_telegram():
    relay_secret = os.getenv("TELEGRAM_RELAY_SECRET", "").strip()
    if relay_secret:
        expected_auth = f"Bearer {relay_secret}"
        if request.headers.get("Authorization") != expected_auth:
            return jsonify({"ok": False, "error": "unauthorized"}), 401

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        return jsonify({"ok": False, "error": "TELEGRAM_BOT_TOKEN is missing"}), 500

    data = request.get_json(silent=True) or {}
    chat_id = str(data.get("chat_id") or "").strip()
    text = str(data.get("text") or "").strip()
    disable_preview = bool(data.get("disable_web_page_preview", False))

    if not chat_id or not text:
        return jsonify({"ok": False, "error": "chat_id and text are required"}), 400

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": disable_preview,
            },
            timeout=(10, 45),
        )
    except requests.exceptions.RequestException as e:
        return jsonify({"ok": False, "error": str(e)}), 502

    if not resp.ok:
        return jsonify({"ok": False, "error": resp.text[:500]}), resp.status_code

    return jsonify({"ok": True})


@app.get("/health")
def health():
    return jsonify({"ok": True})

