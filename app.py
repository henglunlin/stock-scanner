from flask import Flask, render_template, jsonify
from scanner_web import scan_once

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/scan")
def scan():
    return jsonify(scan_once())


if __name__ == "__main__":
    # ✅ ✅ ✅ 關鍵修改在這裡
    app.run(
        host="0.0.0.0",  # 允許外部裝置（手機）連線
        port=5000,
        debug=True
    )