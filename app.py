import os
import time
import requests
import pandas as pd
from threading import Thread
from flask import Flask, jsonify, render_template_string

# إعدادات الأصول والتوكنات المباشرة لصفقاتك
TELEGRAM_TOKEN = '8594136697:AAHpI6a_5TKqUSld3k4bZy8-uvkXiPhy8r4'
TELEGRAM_CHAT_ID = '8475946070'
symbols_binance = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'AVAXUSDT', 'LINKUSDT', 'ZENUSDT', 'ICPUSDT', 'BNBUSDT', 'LTCUSDT', 'DOGEUSDT']

market_store = {s: {"price": 0.0, "status": "🟡 [سوق عرضي]", "signal": "NONE"} for s in symbols_binance}
active_trades = {s: None for s in symbols_binance}
trade_open_times = {s: 0 for s in symbols_binance}
confirmed_trades = {s: False for s in symbols_binance}

app = Flask('')

HTML_PAGE = """
<!DOCTYPE html>
<html lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>CryptoPro Suite</title>
    
    <!-- ميزات تحويل الرابط إلى تطبيق آيفون مستقل ومخفي شريط البحث كلياً -->
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="CryptoPro">
    <link rel="apple-touch-icon" href="https://flaticon.com">
    
    <style>
        body { background: #0b0f17; color: #c9d1d9; font-family: -apple-system, system-ui, sans-serif; padding: env(safe-area-inset-top) 15px 20px 15px; direction: rtl; user-select: none; }
        h2 { text-align: center; color: #58a6ff; font-size: 20px; margin-top: 15px; }
        .grid { display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 15px; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 15px; display: flex; justify-content: space-between; align-items: center; }
        .name { font-size: 18px; font-weight: bold; color: #fff; }
        .price { font-size: 14px; color: #8b949e; margin-top: 3px; }
        .status { font-size: 13px; font-weight: bold; padding: 6px 12px; border-radius: 8px; }
        .green { background: rgba(46,160,67,0.15); color: #3fb950; border: 1px solid #2ea043; }
        .red { background: rgba(248,81,73,0.15); color: #f85149; border: 1px solid #f85143; }
        .yellow { background: rgba(210,153,34,0.15); color: #d29922; border: 1px solid #d29922; }
    </style>
</head>
<body>
    <h2>🏛️ تطبيق الآيفون السحابي الخاص 🏛️</h2>
    <div class="grid" id="main-grid"></div>
    <script>
        async function updateData() {
            try {
                const res = await fetch('/api/data');
                const data = await res.json();
                const container = document.getElementById('main-grid');
                container.innerHTML = '';
                for (const [symbol, info] of Object.entries(data)) {
                    let c = 'yellow';
                    if (info.status.includes('صعود')) c = 'green';
                    if (info.status.includes('هبوط')) c = 'red';
                    container.innerHTML += `
                        <div class="card">
                            <div>
                                <div class="name">${symbol.replace('USDT', '/USDT')}</div>
                                <div class="price">السعر: $${parseFloat(info.price).toLocaleString(undefined, {minimumFractionDigits: 2})}</div>
                            </div>
                            <div class="status ${c}">${info.status}</div>
                        </div>
                    `;
                }
            } catch(e){}
        }
        setInterval(updateData, 3000);
        updateData();
    </script>
</body>
</html>
"""

@app.route('/')
def home(): return render_template_string(HTML_PAGE)

@app.route('/api/data')
def data(): return jsonify(market_store)

def send_telegram_alert(message):
    url = f"https://telegram.org{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try: requests.post(url, json=payload, timeout=10)
    except: pass

def fetch_ohlcv(symbol, tf):
    url = f"https://binance.com{symbol}&interval={tf}&limit=100"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return [[int(x), float(x), float(x), float(x), float(x), float(x)] for x in res.json()]
    except: pass
    return None

def analyze(bars):
    df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'close', 'v'])
    df['EMA_8'] = df['close'].ewm(span=8, adjust=False).mean()
    df['MA_7'] = df['close'].rolling(window=7).mean()
    df['MA_8'] = df['close'].rolling(window=8).mean()
    df['MA_21'] = df['close'].rolling(window=21).mean()
    df['MA_50'] = df['close'].rolling(window=50).mean()
    df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['MA_20'] = df['close'].rolling(window=20).mean()
    df['STD'] = df['close'].rolling(window=20).std()
    df['BU'] = df['MA_20'] + (df['STD'] * 2)
    df['BL'] = df['MA_20'] - (df['STD'] * 2)
    return df

def core_loop():
    global active_trades, confirmed_trades, trade_open_times, market_store
    last_broadcast_time = 0
    while True:
        try:
            for s in symbols_binance:
                b1 = fetch_ohlcv(s, '1m')
                b3 = fetch_ohlcv(s, '3m')
                b5 = fetch_ohlcv(s, '5m')
                b10 = fetch_ohlcv(s, '10m')
                b15 = fetch_ohlcv(s, '15m')
                if not b5 or not b15: continue

                d1, d3, d5, d10, d15 = analyze(b1), analyze(b3), analyze(b5), analyze(b10), analyze(b15)
                l1, l3, l5, l10, l15 = d1.iloc[-1], d3.iloc[-1], d5.iloc[-1], d10.iloc[-1], d15.iloc[-1]
                price = l5['close']
                t_now = time.time()
                display_name = s.replace('USDT', '/USDT')

                cond1 = (l15['EMA_8'] > l15['MA_8']) and (l15['MA_21'] > l15['MA_50'])
                cond3 = (l15['EMA_8'] > l15['MA_50'])
                if cond1 or cond3: status = "🟢 [صعود مؤكد]"
                elif (l15['EMA_8'] < l15['MA_8']) or (l15['MA_7'] < l15['MA_21']): status = "🔴 [هبوط مؤكد]"
                else: status = "🟡 [سوق عرضي]"

                market_store[s]["price"] = price
                market_store[s]["status"] = status

                # 🟢 سيناريوهات قنص الشراء المتقدمة جداً مالتك (أ وب) مع البولنجر والسيولة
                bb_width_5m = (l5['BU'] - l5['BL']) / l5['MA_20']
                squeeze_ok = bb_width_5m < 0.005
                above_21_all = (l1['EMA_8'] > l1['MA_21']) and (l3['EMA_8'] > l3['MA_21']) and (l5['EMA_8'] > l5['MA_21'])
                approach_ok = (l3['EMA_8'] > l3['MA_8']) and (l5['EMA_8'] > l5['MA_8']) and (l10['EMA_8'] > l10['MA_8'])
                
                if (above_21_all and squeeze_ok) or (l1['EMA_8'] > l1['MA_21'] and approach_ok):
                    if active_trades[s] != 'BUY':
                        target1 = price * 1.015
                        target2 = price * 1.030
                        msg = f"🟢 **إشارة دخول شراء وقنص قاع متكامل (تطبيقك الخاص)** 🟢\n\n• **العملة:** {display_name}\n• **السعر الحالي:** ${price:,.4f}\n\n📊 **الوضع الفني:** تفعيل استراتيجية البولنجر والسيولة التتابعية للفريمات الخمسة بنجاح ✅\n\n🎯 **الأهداف صعوداً للأعلى:**\n- الأول (+1.5%): ${target1:,.4f}\n- الثاني (+3.0%): ${target2:,.4f}"
                        send_telegram_alert(msg)
                        active_trades[s] = 'BUY'
                        market_store[s]["signal"] = "BUY"
                        trade_open_times[s] = t_now
                        confirmed_trades[s] = False

                # 🔴 مصفوفة الهبوط والكسر التتابعي الهابط لخطوط الـ EMA 200 للفريمات الستة
                short_trigger = (l10['EMA_8'] < l10['MA_21']) and (l15['EMA_8'] < l15['MA_21'])
                if short_trigger and active_trades[s] != 'SHORT':
                    msg = f"🔴 **إشارة دخول صفقة بيع (SHORT - مصفوفة الهبوط)** 🔴\n\n• **العملة:** {display_name}\n• **سعر الدخول:** ${price:,.4f}\n\n🔥 **الأهداف التتابعية للـ EMA 200 هبوطاً للأسفل:**\n" \
                          f"- الهدف 1 (EMA 200 فريم 3m): ${l3['EMA_200']:,.4f}\n" \
                          f"- الهدف 2 (EMA 200 فريم 5m): ${l5['EMA_200']:,.4f}\n" \
                          f"- الهدف 3 (EMA 200 فريم 10m): ${l10['EMA_200']:,.4f}\n" \
                          f"- الهدف 4 (EMA 200 فريم 15m): ${l15['EMA_200']:,.4f}"
                    send_telegram_alert(msg)
                    active_trades[s] = 'SHORT'
                    market_store[s]["signal"] = "SHORT"
                    trade_open_times[s] = t_now
                    confirmed_trades[s] = False

                # نظام مراقبة وتأكيد الساعتين اللاحق للفريمات الكبرى
                if active_trades[s] == 'BUY' and not confirmed_trades[s] and (t_now - trade_open_times[s] >= 7200):
                    b30 = fetch_ohlcv(s, '30m')
                    b1h = fetch_ohlcv(s, '1h')
                    if b30 and b1h:
                        d30, d1h = analyze(b30), analyze(b1h)
                        if (d30.iloc[-1]['EMA_8'] > d30.iloc[-1]['MA_21']) and (d1h.iloc[-1]['EMA_8'] > d1h.iloc[-1]['MA_21']):
                            send_telegram_alert(f"🐳 **[تقرير الساعتين - الفريمات الكبرى تؤكد استمرارية الصعود]** 🐳\n\n• **العملة:** {display_name}\n✅ المتوسطات قاطعت خط الـ 21 بنجاح على فريم النصف ساعة والساعة، الصعود مكمل وثابت!")
                        else:
                            send_telegram_alert(f"⚠️ **[تقرير الساعتين - تحذير وضع سلبي]** ⚠️\n\n• **العملة:** {display_name}\n❌ مرت ساعتين ولم تخترق المتوسطات خط الـ 21 على الفريمات الكبرى، الاتجاه ضعيف فاحذر.")
                        confirmed_trades[s] = True
                time.sleep(0.1)

            # البث الدوري لتليجرام كل 15 دقيقة
            if t_now - last_broadcast_time >= 900:
                app = app

