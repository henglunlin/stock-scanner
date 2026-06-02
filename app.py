from flask import Flask, jsonify, render_template, request
import yfinance as yf
import pandas as pd
import os
import json
import time
import threading
from datetime import datetime

app = Flask(__name__)

# ===== 設定 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCAN_LIST_FILE = os.path.join(BASE_DIR, "TWstocklist.txt")

# 🌟 改用任務字典管理：不再有全域 scan_lock！
# 結構會是：{ "task_123456": { status, progress, ... }, "task_123457": { ... } }
scan_tasks = {}

def load_scan_list(filepath):
    stocks = []
    if not os.path.exists(filepath):
        return stocks
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            stocks.append(line)
    return stocks


def run_scan(task_id, symbols, enable_kd=True, enable_gap=True):
    """在背景執行緒執行獨立掃描（無鎖設計）"""
    # 🌟 每個任務只改自己 task_id 底下的資料，各走各的路
    scan_tasks[task_id] = {
        "status": "scanning",
        "progress": 0,
        "total": len(symbols),
        "current_symbol": "",
        "results": [],
        "last_scan": None,
        "error": None
    }

    rows = []
    for i, symbol in enumerate(symbols):
        # 🌟 直接更新，不需搶鎖
        scan_tasks[task_id]["progress"] = i + 1
        scan_tasks[task_id]["current_symbol"] = symbol

        try:
            ticker = yf.Ticker(symbol)
            price = ticker.fast_info["last_price"]

            df = yf.download(
                symbol,
                period="3mo",
                auto_adjust=True,
                progress=False,
                group_by="ticker"
            )

            if df.empty or symbol not in df.columns.get_level_values(0):
                continue

            close = df[symbol]["Close"]
            low   = df[symbol]["Low"]
            high  = df[symbol]["High"]

            if len(close) < 20:
                continue

            # 漲跌%
            change_pct = (price / float(close.iloc[-2]) - 1) * 100

            # MA
            ma5  = float(close.tail(5).mean())
            ma10 = float(close.tail(10).mean())
            ma20 = float(close.tail(20).mean())

            if price > ma5:
                ma_range = ">MA5"
            elif ma5 >= price > ma10:
                ma_range = "MA5~10"
            elif ma10 >= price > ma20:
                ma_range = "MA10~20"
            else:
                ma_range = "<MA20"

            if ma5 > ma10 > ma20:
                ma_trend = "多頭"
            elif ma5 < ma10 < ma20:
                ma_trend = "空頭"
            else:
                ma_trend = "糾結"

            # KD
            rsv = (close - low.rolling(9).min()) / (high.rolling(9).max() - low.rolling(9).min()) * 100
            k = rsv.ewm(alpha=1/3, adjust=False).mean()
            d = k.ewm(alpha=1/3, adjust=False).mean()

            k_t, k_y = float(k.iloc[-1]), float(k.iloc[-2])
            d_t, d_y = float(d.iloc[-1]), float(d.iloc[-2])

            # 訊號
            kd_signal  = ""
            gap_signal = ""

            today_low      = float(low.iloc[-1])
            yesterday_high = float(high.iloc[-2])

            if enable_gap and today_low > yesterday_high:
                gap_signal = "跳空"

            if enable_kd:
                if k_y <= d_y and k_t > d_t:
                    kd_signal = "黃金交叉"
                elif k_t > k_y and k_t <= d_t and (d_t - k_t) < 3:
                    kd_signal = "即將黃金交叉"

            if not kd_signal and not gap_signal:
                continue

            rows.append({
                "時間":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "代碼":    symbol,
                "價格":    round(price, 2),
                "漲跌%":   round(change_pct, 2),
                "MA位置":  ma_range,
                "MA排列":  ma_trend,
                "K值":     round(k_t, 1),
                "D值":     round(d_t, 1),
                "KD訊號":  kd_signal,
                "跳空訊號": gap_signal,
            })

        except Exception as e:
            pass  # 忽略單支股票錯誤

    # 🌟 掃描完成，直接寫入對應的 task_id 中
    scan_tasks[task_id]["status"]    = "done"
    scan_tasks[task_id]["results"]   = rows
    scan_tasks[task_id]["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ==================== 路由 ====================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/scan/start", methods=["POST"])
def start_scan():
    # 🌟 每次按下按鈕，都利用當前時間（含毫秒）產生一個全域唯一的任務 ID
    task_id = "task_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    data = request.get_json(silent=True) or {}
    enable_kd  = data.get("enable_kd",  True)
    enable_gap = data.get("enable_gap", True)

    symbols = load_scan_list(SCAN_LIST_FILE)
    if not symbols:
        return jsonify({"ok": False, "msg": "找不到股票清單"}), 400

    # 🌟 將 task_id 傳入執行緒
    t = threading.Thread(
        target=run_scan,
        args=(task_id, symbols, enable_kd, enable_gap),
        daemon=True
    )
    t.start()
    
    # 🌟 回傳 task_id 給網頁，讓網頁知道接下來要查哪一個任務的進度
    return jsonify({"ok": True, "task_id": task_id, "total": len(symbols)})


@app.route("/api/scan/status")
def scan_status():
    # 🌟 前端網頁需改為傳遞 query 參數，例如：/api/scan/status?task_id=task_2024...
    task_id = request.args.get("task_id")
    
    if not task_id or task_id not in scan_tasks:
        return jsonify({"status": "idle", "msg": "找不到該任務或尚未開始"}), 200

    task = scan_tasks[task_id]
    return jsonify({
        "status":         task["status"],
        "progress":       task["progress"],
        "total":          task["total"],
        "current_symbol": task["current_symbol"],
        "result_count":   len(task["results"]),
        "last_scan":      task["last_scan"],
    })


@app.route("/api/scan/results")
def scan_results():
    # 🌟 同樣依據任務 ID 獲取結果
    task_id = request.args.get("task_id")
    
    if not task_id or task_id not in scan_tasks:
        return jsonify({"results": [], "msg": "找不到該任務結果"}), 404

    return jsonify({
        "results":   scan_tasks[task_id]["results"],
        "last_scan": scan_tasks[task_id]["last_scan"],
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
