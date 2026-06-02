import yfinance as yf
import pandas as pd
from datetime import datetime


# ✅ ===== 股票分組 =====
stock_groups = {
    "權值股": [
        "2330.TW", "00981A.TW", "2449.TW",
        "2317.TW", "3711.TW"
    ],
    "自選股": [
        "3008.TW", "3035.TW", "4566.TW"
    ],
    "測試股": [
        "2303.TW", "2454.TW"
    ]
}


def scan_once():

    result = []

    for group_name, stocks in stock_groups.items():

        for symbol in stocks:

            try:
                # ✅ 抓資料
                df = yf.download(
                    symbol,
                    period="3mo",
                    interval="1d",
                    progress=False
                )

                if df is None or df.empty or len(df) < 20:
                    continue

                # ✅ ===== 修正 MultiIndex 問題（核心）=====
                close = df["Close"]
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]

                low = df["Low"]
                if isinstance(low, pd.DataFrame):
                    low = low.iloc[:, 0]

                high = df["High"]
                if isinstance(high, pd.DataFrame):
                    high = high.iloc[:, 0]

                # ✅ 用收盤價當價格（最穩）
                price = float(close.iloc[-1])

                if len(close) < 2:
                    continue

                change_pct = (price / close.iloc[-2] - 1) * 100

                # ===== MA =====
                ma5 = close.tail(5).mean()
                ma10 = close.tail(10).mean()
                ma20 = close.tail(20).mean()

                if price > ma5:
                    ma_range = ">MA5"
                elif ma5 >= price > ma10:
                    ma_range = "MA5~10"
                elif ma10 >= price > ma20:
                    ma_range = "MA10~20"
                else:
                    ma_range = "<MA20"

                ma_trend = (
                    "多頭" if ma5 > ma10 > ma20
                    else "空頭" if ma5 < ma10 < ma20
                    else "糾結"
                )

                # ===== KD（防除0）=====
                lowest_low = low.rolling(9).min()
                highest_high = high.rolling(9).max()

                denominator = (highest_high - lowest_low).replace(0, pd.NA)
                rsv = (close - lowest_low) / denominator * 100

                k = rsv.ewm(alpha=1/3, adjust=False).mean()
                d = k.ewm(alpha=1/3, adjust=False).mean()

                k_t, k_y = k.iloc[-1], k.iloc[-2]
                d_t, d_y = d.iloc[-1], d.iloc[-2]

                # ✅ 防 NaN
                if pd.isna(k_t) or pd.isna(d_t):
                    continue

                # ===== 訊號 =====
                kd_signal = ""
                gap_signal = ""

                if low.iloc[-1] > high.iloc[-2]:
                    gap_signal = "跳空"

                if k_y <= d_y and k_t > d_t:
                    kd_signal = "黃金交叉"
                elif k_t > k_y and k_t <= d_t and (d_t - k_t) < 3:
                    kd_signal = "即將黃金交叉"

                # ✅ 一定輸出（測試用）
                result.append({
                    "分組": group_name,
                    "時間": datetime.now().strftime("%H:%M:%S"),
                    "代碼": symbol,
                    "價格": round(price, 2),
                    "漲跌%": round(change_pct, 2),
                    "MA位置": ma_range,
                    "MA排列": ma_trend,
                    "K值": round(float(k_t), 1),
                    "D值": round(float(d_t), 1),
                    "KD訊號": kd_signal,
                    "跳空訊號": gap_signal
                })

            except Exception as e:
                print(f"[ERROR] {symbol}: {e}")
                continue

    # ✅ debug（確認有資料）
    print(f"✅ 本次回傳資料數量: {len(result)}")

    return result
