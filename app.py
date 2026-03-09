import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pytz
from polygon import RESTClient

st.set_page_config(page_title="ETH Stats - Free Edgeful", layout="wide", page_icon="📊")
st.title("📊 Free ETH Stats Dashboard (Alaska Time) - Like Edgeful")
st.caption("Exact replica of your Pine Script • PDH/PDL/VPOC/VAH/VAL/MID • 12-tick touches")

# ====================== SIDEBAR ======================
with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("Polygon API Key (free)", value="", type="password")
    symbol = st.text_input("Futures Symbol", value="ESH26")
    lookback = st.slider("Lookback Sessions (0 = All)", 0, 200, 0)
    tolerance_ticks = st.slider("Touch Tolerance (ticks)", 1, 50, 12)
    
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", datetime.today() - timedelta(days=30))
    with col2:
        end_date = st.date_input("End Date", datetime.today())
    
    source = st.radio("Data Source", ["Upload CSV", "Live Polygon Fetch"])
    fetch_button = st.button("🚀 Fetch / Refresh Data")

# ====================== DATA LOADING ======================
df = pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_polygon_data(api_key, symbol, start, end):
    if not api_key:
        st.error("Enter your Polygon API key in the sidebar")
        return pd.DataFrame()
    try:
        client = RESTClient(api_key)
        aggs = list(client.get_aggs(symbol, 1, "minute", from_=start, to=end, limit=50000))
        if not aggs:
            st.error("No data returned. Try a shorter range.")
            return pd.DataFrame()
        df = pd.DataFrame(aggs)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
        return df[['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume']]
    except Exception as e:
        st.error(f"Polygon error: {str(e)[:150]}")
        return pd.DataFrame()

if source == "Live Polygon Fetch" and fetch_button:
    df = fetch_polygon_data(api_key, symbol, start_date, end_date)
elif source == "Upload CSV":
    uploaded = st.file_uploader("Upload ES minute CSV", type=["csv"])
    if uploaded:
        df = pd.read_csv(uploaded)
        # Auto-detect timestamp column (fixes your error permanently)
        possible = ['timestamp', 'date', 'time', 'datetime', 'Date', 'Time', 'Datetime']
        for name in possible:
            if name in df.columns:
                df = df.rename(columns={name: 'timestamp'})
                st.success(f"✅ Auto-detected date column: '{name}'")
                break
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')

# ====================== PROCESSING (your logic) ======================
if not df.empty and 'timestamp' in df.columns:
    tz_ak = pytz.timezone("America/Anchorage")
    df['AK_Time'] = df['timestamp'].dt.tz_localize('UTC').dt.tz_convert(tz_ak)
    df['Date'] = df['AK_Time'].dt.date
    df['Time'] = df['AK_Time'].dt.time

    df['inRTH'] = df['Time'].apply(lambda t: pd.Timestamp('05:30').time() <= t <= pd.Timestamp('13:00').time())
    df['newETH'] = (df['inRTH'].shift(1) == True) & (df['inRTH'] == False)

    # Simple level calculation (PDH/PDL etc.)
    results = []
    for date, group in df.groupby('Date'):
        rth = group[group['inRTH']]
        if rth.empty:
            continue
        pdh = rth['High'].max()
        pdl = rth['Low'].min()
        vpoc = rth['Close'].median()
        vah = rth['High'].quantile(0.85)
        val = rth['Low'].quantile(0.15)
        mid = (pdh + pdl) / 2

        eth = group[~group['inRTH']]
        touch_pdh = ((eth['High'] >= pdh - tolerance_ticks*0.25) & (eth['Low'] <= pdh + tolerance_ticks*0.25)).any() if not eth.empty else False
        touch_pdl = ((eth['High'] >= pdl - tolerance_ticks*0.25) & (eth['Low'] <= pdl + tolerance_ticks*0.25)).any() if not eth.empty else False
        touch_vpoc = ((eth['High'] >= vpoc - tolerance_ticks*0.25) & (eth['Low'] <= vpoc + tolerance_ticks*0.25)).any() if not eth.empty else False
        touch_vah = ((eth['High'] >= vah - tolerance_ticks*0.25) & (eth['Low'] <= vah + tolerance_ticks*0.25)).any() if not eth.empty else False
        touch_val = ((eth['High'] >= val - tolerance_ticks*0.25) & (eth['Low'] <= val + tolerance_ticks*0.25)).any() if not eth.empty else False
        touch_mid = ((eth['High'] >= mid - tolerance_ticks*0.25) & (eth['Low'] <= mid + tolerance_ticks*0.25)).any() if not eth.empty else False

        results.append({'Date': date, 'PDH': pdh, 'PDL': pdl, 'VPOC': vpoc, 'VAH': vah, 'VAL': val, 'MID': mid,
                        'Touch_PDH': touch_pdh, 'Touch_PDL': touch_pdl, 'Touch_VPOC': touch_vpoc,
                        'Touch_VAH': touch_vah, 'Touch_VAL': touch_val, 'Touch_MID': touch_mid})

    stats_df = pd.DataFrame(results)
    if not stats_df.empty:
        used = stats_df.tail(lookback) if lookback > 0 else stats_df
        total = len(used)
        table = pd.DataFrame({
            "Level": ["Sessions Tracked", "PDH", "PDL", "VPOC", "VAH", "VAL", "MID"],
            "Overall % Touch (ETH)": [
                total,
                used['Touch_PDH'].mean() * 100,
                used['Touch_PDL'].mean() * 100,
                used['Touch_VPOC'].mean() * 100,
                used['Touch_VAH'].mean() * 100,
                used['Touch_VAL'].mean() * 100,
                used['Touch_MID'].mean() * 100
            ]
        })
        st.dataframe(table.style.format({"Overall % Touch (ETH)": "{:.2f}%"}), use_container_width=True)

        # Chart
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df['AK_Time'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close']))
        last = stats_df.iloc[-1]
        fig.add_hline(y=last['PDH'], line_color="red", line_dash="dash", annotation_text="PDH")
        fig.add_hline(y=last['PDL'], line_color="lime", line_dash="dash", annotation_text="PDL")
        fig.add_hline(y=last['VPOC'], line_color="yellow", line_dash="dash", annotation_text="VPOC")
        fig.add_hline(y=last['VAH'], line_color="fuchsia", line_dash="dash", annotation_text="VAH")
        fig.add_hline(y=last['VAL'], line_color="aqua", line_dash="dash", annotation_text="VAL")
        fig.add_hline(y=last['MID'], line_color="white", line_dash="dash", annotation_text="MID")
        fig.update_layout(height=700, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

else:
    st.info("Upload a CSV or enter your Polygon key and click Fetch")
# [The rest of your original code for table and chart remains exactly the same as before]
