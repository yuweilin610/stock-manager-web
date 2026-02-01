import streamlit as st
import boto3
import pytz
import time
import json
from datetime import datetime, timedelta

# =================================================================
# 區塊 A: 環境配置與 UI 設定
# =================================================================
AWS_REGION = "eu-west-1"
LAMBDA_NAME = "GeminiStockOracle"

st.set_page_config(
    page_title="Market Oracle Operations Suite", 
    page_icon="📈", 
    layout="centered"
)

# [函數] 初始化 AWS 連線服務
def get_session():
    """使用 Streamlit Secrets 建立 AWS Session"""
    return boto3.Session(
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
        region_name=AWS_REGION
    )

try:
    session = get_session()
    lambda_client = session.client("lambda")
    ses_client = session.client("ses")
except Exception as e:
    st.error("AWS Authentication failed. Please check Streamlit Secrets.")
    st.stop()

# [函數] 抓取雲端 Lambda 環境變數 (不使用快取，用於同步)
def get_latest_vars_direct():
    response = lambda_client.get_function_configuration(FunctionName=LAMBDA_NAME)
    return response.get('Environment', {}).get('Variables', {})

# [函數] 抓取雲端 Lambda 環境變數 (快取 2 秒用於 UI)
@st.cache_data(ttl=2)
def get_lambda_vars():
    return get_latest_vars_direct()

# 🚀 【核心邏輯：過夜重置檢查】
# 每次跑 App 都會檢查雲端日期與台北今天日期是否一致
tw_tz = pytz.timezone('Asia/Taipei')
today_tw = datetime.now(tw_tz).strftime("%Y-%m-%d")

try:
    # 這裡使用 direct 不使用快取，確保同步最準確
    current_vars = get_latest_vars_direct()
    last_trigger_date = current_vars.get("LAST_TRIGGER_DATE", "")
    
    if last_trigger_date != today_tw:
        # 日期不符（過夜了），直接在雲端重置
        current_vars["TRIGGER_COUNT"] = "0"
        current_vars["LAST_TRIGGER_DATE"] = today_tw
        lambda_client.update_function_configuration(
            FunctionName=LAMBDA_NAME, 
            Environment={'Variables': current_vars}
        )
        st.cache_data.clear() # 強制刷新快取
        st.toast("📅 日期更迭，手動額度已自動重置為 0/2")
except Exception as e:
    st.warning(f"Note: Cloud sync in progress... ({e})")

# [函數] 檢查 SES Email 驗證狀態
def check_email_verification(email_list):
    if not email_list: return {}
    response = ses_client.get_identity_verification_attributes(Identities=email_list)
    attrs = response.get('VerificationAttributes', {})
    return {email: attrs.get(email, {}).get('VerificationStatus', 'NotFound') for email in email_list}

# =================================================================
# 區塊 B: 安全登入邏輯
# =================================================================
correct_password = st.secrets.get("ADMIN_PASSWORD")
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Secure Access")
    with st.form("login_form"):
        pwd = st.text_input("Administrator Password", type="password")
        if st.form_submit_button("Login"):
            if correct_password and pwd == correct_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Invalid credentials.")
    st.stop()

# =================================================================
# 區塊 C: 儀表板與排程管理
# =================================================================
st.title("📈 Market Oracle Dashboard")

# 顯示即時時間
col_t1, col_t2 = st.columns(2)
ie_tz = pytz.timezone('Europe/Dublin')
now_ie, now_tw = datetime.now(ie_tz), datetime.now(tw_tz)

with col_t1: st.metric("Dublin (IST/GMT)", now_ie.strftime("%H:%M"))
with col_t2: st.metric("Taipei (CST)", now_tw.strftime("%H:%M"))

st.divider()
st.subheader("📬 Next Dispatch Status")

# 重新抓取變數供顯示
current_vars = get_lambda_vars()
db_schedule = current_vars.get("REPORT_SCHEDULE", "AFTERNOON")
trigger_count = int(current_vars.get("TRIGGER_COUNT", "0"))

def get_next_delivery_str(now_tw_obj, schedule):
    tw_hour = now_tw_obj.hour
    if schedule == "MORNING": target_tw_h = 7
    elif schedule == "AFTERNOON": target_tw_h = 15
    else: target_tw_h = 7 if tw_hour < 7 else (15 if tw_hour < 15 else 7)
    
    target_date = now_tw_obj.date()
    if tw_hour >= target_tw_h: target_date += timedelta(days=1)
    while target_date.weekday() >= 5: target_date += timedelta(days=1)
        
    target_dt_tw = tw_tz.localize(datetime.combine(target_date, datetime.min.time().replace(hour=target_tw_h)))
    target_dt_ie = target_dt_tw.astimezone(ie_tz)
    
    today_date = now_tw_obj.date()
    day_tw = "Today" if target_date == today_date else "Tomorrow" if target_date == today_date + timedelta(days=1) else "Next Monday"
    day_ie = ("Yesterday" if day_tw == "Today" else "Today" if day_tw == "Tomorrow" else "Next Sunday") if target_dt_ie.date() < target_date else day_tw
    return f"**{day_ie}** at **{target_dt_ie.strftime('%H:%M')} IST** / **{day_tw}** at **{target_dt_tw.strftime('%H:%M')} CST**"

delivery_msg = get_next_delivery_str(now_tw, db_schedule)
st.info(f"Current setting: **{db_schedule}**. Next dispatch: {delivery_msg}")

st.subheader("⏰ Delivery Schedule")
schedule_options = ["AFTERNOON", "MORNING", "BOTH"]
new_schedule = st.selectbox("Adjust Delivery Shift", schedule_options, 
                            index=schedule_options.index(db_schedule) if db_schedule in schedule_options else 0)

if new_schedule != db_schedule:
    current_vars["REPORT_SCHEDULE"] = new_schedule
    lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
    st.cache_data.clear(); st.rerun()

# --- 手動觸發按鈕區 ---
can_press = trigger_count < 2
stocks = [s.strip() for s in current_vars.get("STOCK_LIST", "").split(",") if s.strip()]
setup_ready = len(stocks) > 0

col_btn, col_info = st.columns([1, 2])

with col_btn:
    btn_label = "Daily Limit Reached" if not can_press else f"Manual Trigger ({trigger_count}/2)"
    
    if st.button(btn_label, use_container_width=True, type="primary", disabled=not (can_press and setup_ready)):
        try:
            # 觸發 Lambda
            lambda_client.invoke(
                FunctionName=LAMBDA_NAME, 
                InvocationType='Event',
                Payload=json.dumps({"manual": True})
            )
            
            # 更新雲端次數與日期
            new_count = trigger_count + 1
            current_vars["TRIGGER_COUNT"] = str(new_count)
            current_vars["LAST_TRIGGER_DATE"] = today_tw
            lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
            
            st.success(f"✅ Triggered! ({new_count}/2 used today).")
            time.sleep(2)
            st.cache_data.clear(); st.rerun()
        except Exception as e:
            st.error(f"Trigger failed: {e}")

with col_info:
    if not setup_ready:
        st.error("⚠️ Setup required: Please add at least 1 stock.")
    elif not can_press:
        st.warning("⚠️ Daily manual limit reached. Reset at Taipei Midnight.")
    else:
        st.caption(f"Remaining: {2 - trigger_count} triggers today.")

# =================================================================
# 區塊 D: Portfolio Watchlist
# =================================================================
st.divider()
st.subheader("📝 Portfolio Watchlist")
st.caption(f"{len(stocks)} / 5 Tickers Selected")

for idx, s in enumerate(stocks):
    c1, c2, c3, c4 = st.columns([3, 0.5, 0.5, 1])
    c1.write(f"{idx+1}. **{s}**")
    
    if idx > 0 and c2.button("↑", key=f"up_{s}"):
        stocks[idx], stocks[idx-1] = stocks[idx-1], stocks[idx]
        current_vars["STOCK_LIST"] = ",".join(stocks)
        lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
        st.cache_data.clear(); st.rerun()

    if idx < len(stocks) - 1 and c3.button("↓", key=f"down_{s}"):
        stocks[idx], stocks[idx+1] = stocks[idx+1], stocks[idx]
        current_vars["STOCK_LIST"] = ",".join(stocks)
        lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
        st.cache_data.clear(); st.rerun()

    if c4.button("🗑️", key=f"del_{s}"):
        stocks.remove(s)
        current_vars["STOCK_LIST"] = ",".join(stocks)
        lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
        st.cache_data.clear(); st.rerun()

new_stock = st.text_input("Enter Ticker Symbol", placeholder="e.g. nvda").upper().strip()
if st.button("➕ Add to Watchlist"):
    if new_stock:
        if new_stock in stocks:
            st.error(f"Ticker '{new_stock}' is already in your watchlist.")
        elif len(stocks) >= 5:
            st.warning("Watchlist is full.")
        else:
            stocks.append(new_stock)
            current_vars["STOCK_LIST"] = ",".join(stocks)
            lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
            st.cache_data.clear(); time.sleep(1); st.rerun()

# =================================================================
# 區塊 E: Subscriber Management
# =================================================================
st.divider()
st.subheader("📧 Intelligence Subscribers")
emails = [e.strip() for e in current_vars.get("RECEIVER_EMAILS", "").split(",") if e.strip()]
status_map = check_email_verification(emails)

for e in emails:
    ec1, ec2 = st.columns([4, 1.2])
    status = status_map.get(e, 'Pending')
    status_label = "" if status == 'Success' else " (Pending Verification)"
    ec1.write(f"{e}{status_label}")
    
    if e == "roserain610@gmail.com": 
        ec2.write("🔒")
    elif ec2.button("🗑️", key=f"del_e_{e}"):
        emails.remove(e)
        current_vars["RECEIVER_EMAILS"] = ",".join(emails)
        lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
        st.cache_data.clear(); st.rerun()

new_email = st.text_input("Invite New Recipient", placeholder="example@mail.com").strip().lower()
if st.button("📩 Dispatch Invitation"):
    if new_email and new_email not in emails:
        try:
            ses_client.verify_email_identity(EmailAddress=new_email)
            emails.append(new_email)
            current_vars["RECEIVER_EMAILS"] = ",".join(emails)
            lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
            st.success(f"Verification sent to {new_email}.")
            st.cache_data.clear(); time.sleep(2); st.rerun()
        except Exception as err: st.error(f"AWS Error: {err}")