import streamlit as st
import boto3
import pytz
import time
from datetime import datetime

# =================================================================
# SECTION A: Configurations & UI Setup (AWS 與介面設定)
# =================================================================
AWS_REGION = "eu-west-1"
LAMBDA_NAME = "GeminiStockOracle"

st.set_page_config(
    page_title="Market Oracle Operations Suite", 
    page_icon="page_icon.png", 
    layout="centered"
)

# [函數] 初始化 AWS 連線服務
def get_session():
    """Builds AWS Session using credentials from Streamlit Secrets"""
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

# [函數] 抓取雲端 Lambda 環境變數 (快取設定為 2 秒)
@st.cache_data(ttl=2)
def get_lambda_vars():
    """Retrieves current configuration from Lambda"""
    response = lambda_client.get_function_configuration(FunctionName=LAMBDA_NAME)
    return response.get('Environment', {}).get('Variables', {})

try:
    current_vars = get_lambda_vars()
except Exception as e:
    st.error(f"Failed to connect to AWS Cloud: {e}")
    st.stop()

# [函數] 檢查 SES Email 驗證狀態
def check_email_verification(email_list):
    """Queries AWS SES for verification status of given emails"""
    if not email_list: return {}
    response = ses_client.get_identity_verification_attributes(Identities=email_list)
    attrs = response.get('VerificationAttributes', {})
    return {email: attrs.get(email, {}).get('VerificationStatus', 'NotFound') for email in email_list}

# =================================================================
# SECTION B: Security & Login Logic (安全檢查)
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
                st.components.v1.html("<script>window.top.scrollTo(0,0);</script>", height=0)
                st.rerun()
            else:
                st.error("Invalid credentials.")
    st.stop()

# =================================================================
# SECTION C: Dashboard & Scheduling (儀表板與排程)
# =================================================================
st.components.v1.html("<script>window.top.scrollTo(0,0);</script>", height=0)
st.title("📈 Market Oracle Dashboard")

# 顯示兩地時間
col_t1, col_t2 = st.columns(2)
ie_tz, tw_tz = pytz.timezone('Europe/Dublin'), pytz.timezone('Asia/Taipei')
now_ie, now_tw = datetime.now(ie_tz), datetime.now(tw_tz)

with col_t1: st.metric("Dublin (IST)", now_ie.strftime("%H:%M"))
with col_t2: st.metric("Taipei (CST)", now_tw.strftime("%H:%M"))

st.divider()
st.subheader("📬 Next Dispatch Status")
db_schedule = current_vars.get("REPORT_SCHEDULE", "AFTERNOON")

# 計算下一次發送時間的邏輯函數
def get_next_delivery_str(tw_hour, schedule):
    if schedule == "MORNING": target_tw = 7
    elif schedule == "AFTERNOON": target_tw = 15
    else: target_tw = 7 if tw_hour < 7 else (15 if tw_hour < 15 else 7)
    
    day_tw = "Today"
    if (schedule == "MORNING" and tw_hour >= 7) or \
       (schedule == "AFTERNOON" and tw_hour >= 15) or \
       (schedule == "BOTH" and tw_hour >= 15):
        day_tw = "Tomorrow"

    if target_tw == 7:
        ist_time = "23:00"; day_ist = "Today" if day_tw == "Tomorrow" else "Yesterday"
        return f"**{day_ist}** at **{ist_time} IST** / **{day_tw}** at **07:00 CST**"
    else:
        ist_time = "07:00"
        return f"**{day_tw}** at **{ist_time} IST** / **{day_tw}** at **15:00 CST**"

delivery_msg = get_next_delivery_str(now_tw.hour, db_schedule)
st.info(f"Current setting: **{db_schedule}**. Next dispatch: {delivery_msg}")

st.subheader("⏰ Delivery Schedule")
schedule_options = ["AFTERNOON", "MORNING", "BOTH"]
new_schedule = st.selectbox("Adjust Delivery Shift", schedule_options, 
                            index=schedule_options.index(db_schedule) if db_schedule in schedule_options else 0)

# 💡 報告重點說明 HTML 區塊 (中文)
st.markdown("""
<div style="background-color: #f0f2f6; padding: 12px; border-radius: 8px; font-size: 0.88rem; color: #444; border-left: 5px solid #007bff;">
    <strong>💡 報告重點說明 (台灣時間):</strong><br>
    • <strong>MORNING (07:00):</strong> 
        <strong>昨夜動態追蹤。</strong> 總結昨晚市場波動的核心主因，解析觀察標的的重大消息與趨勢。<br>
    • <strong>AFTERNOON (15:00):</strong> 
        <strong>今日盤勢與前瞻。</strong> 解析今日市場變動主因，並捕捉即時新聞以利開盤前的策略佈局。<br>
    • <strong>BOTH:</strong> 每天兩次，全方位追蹤標的變動脈絡。
</div>
""", unsafe_allow_html=True)

if new_schedule != db_schedule:
    current_vars["REPORT_SCHEDULE"] = new_schedule
    lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
    st.cache_data.clear() 
    st.rerun()

# =================================================================
# SECTION D: Portfolio Watchlist (股票觀察清單 - 強制大寫與重複檢查)
# =================================================================
st.divider()
st.subheader("📝 Portfolio Watchlist")
stocks = [s.strip() for s in current_vars.get("STOCK_LIST", "").split(",") if s.strip()]
st.caption(f"{len(stocks)} / 10 Tickers Selected")

for idx, s in enumerate(stocks):
    c1, c2, c3, c4 = st.columns([3, 0.5, 0.5, 1])
    c1.write(f"{idx+1}. **{s}**")
    
    if idx > 0 and c2.button("↑", key=f"up_{s}"):
        stocks[idx], stocks[idx-1] = stocks[idx-1], stocks[idx]
        current_vars["STOCK_LIST"] = ",".join(stocks)
        lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
        st.cache_data.clear()
        st.rerun()

    if idx < len(stocks) - 1 and c3.button("↓", key=f"down_{s}"):
        stocks[idx], stocks[idx+1] = stocks[idx+1], stocks[idx]
        current_vars["STOCK_LIST"] = ",".join(stocks)
        lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
        st.cache_data.clear()
        st.rerun()

    if c4.button("🗑️", key=f"del_{s}"):
        stocks.remove(s)
        current_vars["STOCK_LIST"] = ",".join(stocks)
        lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
        st.cache_data.clear()
        st.rerun()

# 股票輸入：強制轉大寫與檢查重複
new_stock = st.text_input("Enter Ticker Symbol", placeholder="e.g. nvda").upper().strip()
if st.button("➕ Add to Watchlist"):
    if new_stock:
        if new_stock in stocks:
            st.error(f"Ticker '{new_stock}' is already in your watchlist.")
        elif len(stocks) >= 10:
            st.warning("Watchlist is full (Maximum 10 tickers).")
        else:
            stocks.append(new_stock)
            current_vars["STOCK_LIST"] = ",".join(stocks)
            lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
            
            # --- 顯示股票新增成功與警示 ---
            st.success(f"Ticker '{new_stock}' added successfully!")
            st.info("Notice: This ticker will be analyzed in the next report.")
            
            st.cache_data.clear()
            time.sleep(1.5)
            st.rerun()

# =================================================================
# SECTION E: Subscriber Management (訂閱管理 - 刪除重驗與 Pending 標籤)
# =================================================================
st.divider()
st.subheader("📧 Intelligence Subscribers")
emails = [e.strip() for e in current_vars.get("RECEIVER_EMAILS", "").split(",") if e.strip()]
DEFAULT_EMAIL = "roserain610@gmail.com"
MAX_SUBS = 5

sub_count = len(emails)
if sub_count >= MAX_SUBS:
    st.warning(f"Limit Reached: {sub_count}/{MAX_SUBS} Recipients.")
else:
    st.success(f"Capacity: {sub_count}/{MAX_SUBS} Slots Available.")

# 檢查 SES 驗證狀態
status_map = check_email_verification(emails)

for e in emails:
    ec1, ec2 = st.columns([4, 1.2])
    status = status_map.get(e, 'Pending')
    status_label = "" if status == 'Success' else " (Pending)"
    ec1.write(f"{e}{status_label}")
    
    if e == DEFAULT_EMAIL: 
        ec2.write("🔒")
    elif ec2.button("🗑️", key=f"del_e_{e}"):
        emails.remove(e)
        current_vars["RECEIVER_EMAILS"] = ",".join(emails)
        # 同步刪除 SES Identity 確保下次加回必須重新驗證
        try:
            ses_client.delete_identity(Identity=e)
        except:
            pass
        lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
        st.cache_data.clear()
        st.rerun()

# 新增 Email：自動小寫、重複檢查、三重警示
is_full = sub_count >= MAX_SUBS
new_email = st.text_input("Invite New Recipient", disabled=is_full, placeholder="example@mail.com").strip().lower()

if st.button("📩 Dispatch Invitation", disabled=is_full or not new_email):
    if new_email in emails:
        st.error(f"Recipient '{new_email}' is already in the list.")
    else:
        try:
            # 向 SES 請求驗證
            ses_client.verify_email_identity(EmailAddress=new_email)
            emails.append(new_email)
            current_vars["RECEIVER_EMAILS"] = ",".join(emails)
            lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
            
            # --- 顯示 Email 新增成功與三重警示 ---
            st.success(f"Invitation dispatched to {new_email}.")
            st.info("Notice: Changes will take effect in the next dispatch cycle.")
            st.warning("New subscribers must click the verification link in their inbox.")
            
            st.cache_data.clear()
            time.sleep(2) 
            st.rerun() 
        except Exception as err: 
            st.error(f"AWS Error: {err}")