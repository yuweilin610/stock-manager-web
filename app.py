import streamlit as st
import boto3
import pytz
import time
from datetime import datetime, timedelta

# =================================================================
# SECTION A: Configurations & UI Setup (Keep Unchanged)
# =================================================================
AWS_REGION = "eu-west-1"
LAMBDA_NAME = "GeminiStockOracle"

st.set_page_config(
    page_title="Market Oracle Operations Suite", 
    page_icon="📈", 
    layout="centered"
)

def get_session():
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

@st.cache_data(ttl=2)
def get_lambda_vars():
    response = lambda_client.get_function_configuration(FunctionName=LAMBDA_NAME)
    return response.get('Environment', {}).get('Variables', {})

try:
    current_vars = get_lambda_vars()
except Exception as e:
    st.error(f"Failed to connect to AWS Cloud: {e}")
    st.stop()

def check_email_verification(email_list):
    if not email_list: return {}
    response = ses_client.get_identity_verification_attributes(Identities=email_list)
    attrs = response.get('VerificationAttributes', {})
    return {email: attrs.get(email, {}).get('VerificationStatus', 'NotFound') for email in email_list}

# =================================================================
# SECTION B: Security & Login (Keep Unchanged)
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
# SECTION C: Dashboard & Scheduling
# =================================================================
st.title("📈 Market Oracle Dashboard")

col_t1, col_t2 = st.columns(2)
ie_tz, tw_tz = pytz.timezone('Europe/Dublin'), pytz.timezone('Asia/Taipei')
now_ie, now_tw = datetime.now(ie_tz), datetime.now(tw_tz)
with col_t1: st.metric("Dublin (IST/GMT)", now_ie.strftime("%H:%M"))
with col_t2: st.metric("Taipei (CST)", now_tw.strftime("%H:%M"))

st.divider()
st.subheader("📬 Next Dispatch Status")
db_schedule = current_vars.get("REPORT_SCHEDULE", "AFTERNOON")

def get_next_delivery_str(now_tw_obj, schedule):
    tw_hour = now_tw_obj.hour
    target_tw_h = 7 if schedule == "MORNING" else (15 if schedule == "AFTERNOON" else (7 if tw_hour < 7 else (15 if tw_hour < 15 else 7)))
    target_date = now_tw_obj.date()
    if tw_hour >= target_tw_h: target_date += timedelta(days=1)
    while target_date.weekday() >= 5: target_date += timedelta(days=1)
    target_dt_tw = tw_tz.localize(datetime.combine(target_date, datetime.min.time().replace(hour=target_tw_h)))
    target_dt_ie = target_dt_tw.astimezone(ie_tz)
    day_tw = "Today" if target_date == now_tw_obj.date() else "Tomorrow" if target_date == now_tw_obj.date() + timedelta(days=1) else "Next Monday"
    day_ie = ("Yesterday" if day_tw == "Today" else "Today" if day_tw == "Tomorrow" else "Next Sunday") if target_dt_ie.date() < target_date else day_tw
    return f"**{day_ie}** at **{target_dt_ie.strftime('%H:%M')} IST** / **{day_tw}** at **{target_dt_tw.strftime('%H:%M')} CST**"

st.info(f"Current setting: **{db_schedule}**. Next dispatch: {get_next_delivery_str(now_tw, db_schedule)}")

st.subheader("⏰ Delivery Schedule")
schedule_options = ["AFTERNOON", "MORNING", "BOTH"]
new_schedule = st.selectbox("Adjust Delivery Shift", schedule_options, index=schedule_options.index(db_schedule) if db_schedule in schedule_options else 0)

# (ADDED: Schedule Explanation in Chinese)
st.markdown("""
<div style="background-color: #f0f2f6; padding: 12px; border-radius: 8px; font-size: 0.88rem; color: #444; border-left: 5px solid #007bff;">
    <strong>💡 報告重點說明 (台灣時間):</strong><br>
    • <strong>MORNING (07:00):</strong> <strong>昨夜動態追蹤。</strong> 總結昨晚市場波動的核心主因，解析觀察標的的重大消息與趨勢。<br>
    • <strong>AFTERNOON (15:00):</strong> <strong>今日盤勢與前瞻。</strong> 解析今日市場變動主因，並捕捉即時新聞以利開盤前的策略佈局。
</div>
""", unsafe_allow_html=True)

if new_schedule != db_schedule:
    current_vars["REPORT_SCHEDULE"] = new_schedule
    lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
    st.cache_data.clear(); st.rerun()

# --- (ADDED: SECTION C-1: Operational Controls with Daily Limit) ---
st.divider()
st.subheader("🚀 Operational Controls")

today_str = now_tw.strftime("%Y-%m-%d")
last_trigger_date = current_vars.get("LAST_TRIGGER_DATE", "")
trigger_count = int(current_vars.get("TRIGGER_COUNT", "0"))

# Reset count if it's a new day
if last_trigger_date != today_str:
    trigger_count = 0

can_press = trigger_count < 2
stocks = [s.strip() for s in current_vars.get("STOCK_LIST", "").split(",") if s.strip()]
setup_ready = len(stocks) > 0

col_btn, col_info = st.columns([1, 2])

with col_btn:
    if trigger_count >= 2:
        btn_label = "Daily Limit Reached"
    else:
        btn_label = f"Manual Trigger ({trigger_count}/2)"
    
    if st.button(btn_label, use_container_width=True, type="primary", disabled=not (can_press and setup_ready)):
        try:
            new_count = trigger_count + 1
            current_vars["TRIGGER_COUNT"] = str(new_count)
            current_vars["LAST_TRIGGER_DATE"] = today_str
            lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
            
            lambda_client.invoke(FunctionName=LAMBDA_NAME, InvocationType='Event')
            st.success(f"✅ Triggered! ({new_count}/2 used today)")
            time.sleep(2)
            st.cache_data.clear(); st.rerun()
        except Exception as e:
            st.error(f"Trigger failed: {e}")

with col_info:
    if not setup_ready:
        st.error("⚠️ Setup required: Please add at least 1 stock below.")
    elif not can_press:
        st.warning("⚠️ Daily manual limit reached. Please wait for the scheduled dispatch.")
    else:
        st.caption(f"Remaining: {2 - trigger_count} triggers today.")
        st.markdown("""
        <div style="font-size: 0.85rem; color: #d9534f; font-weight: bold; border: 1px solid #d9534f; padding: 10px; border-radius: 6px;">
            💡 Reminder: Make sure to add YOUR email to "Subscribers" below first, or the report will only be sent to the default admin.
        </div>
        """, unsafe_allow_html=True)

# =================================================================
# SECTION D: Portfolio Watchlist (Keep Unchanged)
# =================================================================
st.divider()
st.subheader("📝 Portfolio Watchlist")
st.caption(f"{len(stocks)} / 5 Tickers Selected")
for idx, s in enumerate(stocks):
    c1, c2, c3, c4 = st.columns([3, 0.5, 0.5, 1])
    c1.write(f"{idx+1}. **{s}**")
    if idx > 0 and c2.button("↑", key=f"up_{s}"):
        stocks[idx], stocks[idx-1] = stocks[idx-1], stocks[idx]; current_vars["STOCK_LIST"] = ",".join(stocks)
        lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars}); st.cache_data.clear(); st.rerun()
    if idx < len(stocks) - 1 and c3.button("↓", key=f"down_{s}"):
        stocks[idx], stocks[idx+1] = stocks[idx+1], stocks[idx]; current_vars["STOCK_LIST"] = ",".join(stocks)
        lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars}); st.cache_data.clear(); st.rerun()
    if c4.button("🗑️", key=f"del_{s}"):
        stocks.remove(s); current_vars["STOCK_LIST"] = ",".join(stocks)
        lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars}); st.cache_data.clear(); st.rerun()

new_stock = st.text_input("Enter Ticker", placeholder="e.g. NVDA").upper().strip()
if st.button("➕ Add Ticker"):
    if new_stock and new_stock not in stocks and len(stocks) < 5:
        stocks.append(new_stock); current_vars["STOCK_LIST"] = ",".join(stocks)
        lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
        st.cache_data.clear(); st.rerun()

# =================================================================
# SECTION E: Subscriber Management (Keep Unchanged)
# =================================================================
st.divider()
st.subheader("📧 Intelligence Subscribers")
emails = [e.strip() for e in current_vars.get("RECEIVER_EMAILS", "").split(",") if e.strip()]
DEFAULT_EMAIL = "roserain610@gmail.com"
status_map = check_email_verification(emails)
for e in emails:
    ec1, ec2 = st.columns([4, 1.2])
    status_label = "" if status_map.get(e) == 'Success' else " (Pending)"
    ec1.write(f"{e}{status_label}")
    if e == DEFAULT_EMAIL: ec2.write("🔒")
    elif ec2.button("🗑️", key=f"del_e_{e}"):
        emails.remove(e); current_vars["RECEIVER_EMAILS"] = ",".join(emails)
        try: ses_client.delete_identity(Identity=e)
        except: pass
        lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars}); st.cache_data.clear(); st.rerun()

new_email = st.text_input("Invite New Recipient", placeholder="example@mail.com").strip().lower()
if st.button("📩 Dispatch Invitation"):
    if new_email and new_email not in emails and len(emails) < 5:
        try:
            ses_client.verify_email_identity(EmailAddress=new_email)
            emails.append(new_email); current_vars["RECEIVER_EMAILS"] = ",".join(emails)
            lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
            st.cache_data.clear(); st.rerun()
        except Exception as err: st.error(f"Error: {err}")