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
    page_icon="page_icon.png", 
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

# [函數] 抓取雲端 Lambda 環境變數 (不使用快取的版本，用於啟動重置)
def get_latest_vars_direct():
    response = lambda_client.get_function_configuration(FunctionName=LAMBDA_NAME)
    return response.get('Environment', {}).get('Variables', {})

# 🚀 【核心邏輯更新：過夜自動重置】
# 移除原本的 st.session_state.reset_done 強制歸零邏輯
# 改為比對雲端 LAST_TRIGGER_DATE 與 台北今日日期
tw_tz = pytz.timezone('Asia/Taipei')
today_tw = datetime.now(tw_tz).strftime("%Y-%m-%d")

try:
    boot_vars = get_latest_vars_direct()
    last_trigger_date = boot_vars.get("LAST_TRIGGER_DATE", "")
    
    # 如果日期不同 (代表過夜了)，則在雲端重置次數
    if last_trigger_date != today_tw:
        boot_vars["TRIGGER_COUNT"] = "0"
        boot_vars["LAST_TRIGGER_DATE"] = today_tw
        lambda_client.update_function_configuration(
            FunctionName=LAMBDA_NAME, 
            Environment={'Variables': boot_vars}
        )
        # 清除快取以確保下方讀取到最新的 0
        st.cache_data.clear()
        time.sleep(0.5) 
except:
    pass

# [函數] 抓取雲端 Lambda 環境變數 (快取 2 秒)
@st.cache_data(ttl=2)
def get_lambda_vars():
    """獲取 Lambda 目前的環境配置"""
    return get_latest_vars_direct()

try:
    current_vars = get_lambda_vars()
except Exception as e:
    st.error(f"Failed to connect to AWS Cloud: {e}")
    st.stop()

# [函數] 檢查 SES Email 驗證狀態
def check_email_verification(email_list):
    """查詢信箱驗證狀態"""
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
                st.components.v1.html("<script>window.top.scrollTo(0,0);</script>", height=0)
                st.rerun()
            else:
                st.error("Invalid credentials.")
    st.stop()

# =================================================================
# 區塊 C: 儀表板與排程管理 (整合手動功能)
# =================================================================
st.components.v1.html("<script>window.top.scrollTo(0,0);</script>", height=0)
st.title("📈 Market Oracle Dashboard")

# 顯示即時時間
col_t1, col_t2 = st.columns(2)
ie_tz = pytz.timezone('Europe/Dublin')
now_ie, now_tw = datetime.now(ie_tz), datetime.now(tw_tz)

with col_t1: st.metric("Dublin (IST/GMT)", now_ie.strftime("%H:%M"))
with col_t2: st.metric("Taipei (CST)", now_tw.strftime("%H:%M"))

st.divider()
st.subheader("📬 Next Dispatch Status")
db_schedule = current_vars.get("REPORT_SCHEDULE", "AFTERNOON")

# 處理排程時間邏輯
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

st.markdown("""
<div style="background-color: #f0f2f6; padding: 12px; border-radius: 8px; font-size: 0.88rem; color: #444; border-left: 5px solid #007bff;">
    <strong>💡 報告重點說明 (台灣時間):</strong><br>
    • <strong>MORNING (07:00):</strong> <strong>昨夜動態追蹤。</strong> 總結昨晚市場波動的核心主因。<br>
    • <strong>AFTERNOON (15:00):</strong> <strong>今日盤勢與前瞻。</strong> 解析今日市場變動主因。<br>
    • <strong>BOTH:</strong> 每天兩次，全方位追蹤標的變動。
</div>
""", unsafe_allow_html=True)

# 🚀 增加間距
st.write("")

if new_schedule != db_schedule:
    current_vars["REPORT_SCHEDULE"] = new_schedule
    lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
    st.cache_data.clear(); st.rerun()

# --- 手動觸發按鈕區 ---
today_str = now_tw.strftime("%Y-%m-%d")
last_trigger_date = current_vars.get("LAST_TRIGGER_DATE", "")
trigger_count = int(current_vars.get("TRIGGER_COUNT", "0"))

# 二重檢查日期 (雙重保障)
if last_trigger_date != today_str:
    trigger_count = 0

can_press = trigger_count < 2
stocks = [s.strip() for s in current_vars.get("STOCK_LIST", "").split(",") if s.strip()]
setup_ready = len(stocks) > 0

col_btn, col_info = st.columns([1, 2])

with col_btn:
    btn_label = "Daily Limit Reached" if not can_press else f"Manual Trigger ({trigger_count}/2)"
    
    if st.button(btn_label, use_container_width=True, type="primary", disabled=not (can_press and setup_ready)):
        # 1. 檢查忙碌狀態
        latest_vars = get_latest_vars_direct()
        if latest_vars.get("IS_PROCESSING", "false").lower() == "true":
            st.error("System Busy: An analysis is already in progress.")
        else:
            try:
                lambda_client.invoke(
                    FunctionName=LAMBDA_NAME, 
                    InvocationType='Event',
                    Payload=json.dumps({"manual": True})
                )
                
                # 更新次數與日期
                new_count = trigger_count + 1
                current_vars["TRIGGER_COUNT"] = str(new_count)
                current_vars["LAST_TRIGGER_DATE"] = today_str
                lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
                
                st.success(f"✅ Triggered! ({new_count}/2 used today). Please check your inbox in a few minutes.")
                
                time.sleep(3)
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
        st.markdown("""<div style="font-size: 0.85rem; color: #d9534f; font-weight: bold; border: 1px solid #d9534f; padding: 10px; border-radius: 6px;">💡 Reminder: Make sure to add YOUR email to "Subscribers" below first.</div>""", unsafe_allow_html=True)

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
            st.warning("Watchlist is full (Maximum 5 tickers).")
        else:
            stocks.append(new_stock)
            current_vars["STOCK_LIST"] = ",".join(stocks)
            lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
            st.success(f"Ticker '{new_stock}' added successfully!")
            st.cache_data.clear(); time.sleep(1.5); st.rerun()

# =================================================================
# 區塊 E: Subscriber Management
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
        try: ses_client.delete_identity(Identity=e)
        except: pass
        lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
        st.cache_data.clear(); st.rerun()

is_full = sub_count >= MAX_SUBS
new_email = st.text_input("Invite New Recipient", disabled=is_full, placeholder="example@mail.com").strip().lower()

if st.button("📩 Dispatch Invitation", disabled=is_full or not new_email):
    if new_email in emails:
        st.error(f"Recipient '{new_email}' is already in the list.")
    else:
        try:
            ses_client.verify_email_identity(EmailAddress=new_email)
            emails.append(new_email)
            current_vars["RECEIVER_EMAILS"] = ",".join(emails)
            lambda_client.update_function_configuration(FunctionName=LAMBDA_NAME, Environment={'Variables': current_vars})
            st.success(f"Invitation dispatched to {new_email}.")
            st.cache_data.clear(); time.sleep(2); st.rerun() 
        except Exception as err: 
            st.error(f"AWS Error: {err}")