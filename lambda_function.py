import os
import boto3
import json
import dbtest_function  # 🚀 匯入你的資料庫測試函式
from datetime import datetime, timedelta, timezone
from google import genai
from google.genai import types

# --- 1. 初始化 AWS 資源 ---
dynamodb = boto3.resource('dynamodb')
ses = boto3.client('ses', region_name='eu-west-1')
table = dynamodb.Table('MarketOracle_Users')

def send_email(subject, html_body, recipients):
    """
    【函式：發送郵件】
    使用 AWS SES 服務，將 Gemini 生成的 HTML 內容寄送給指定的收件人。
    """
    sender = "yuwei.lin610@gmail.com" 
    try:
        ses.send_email(
            Source=sender,
            Destination={'ToAddresses': recipients},
            Message={
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {'Html': {'Data': html_body, 'Charset': 'UTF-8'}}
            }
        )
    except Exception as e:
        print(f"SES 寄信錯誤: {str(e)}")

def run_gemini_analysis(stocks, recipients, current_hour):
    """
    【函式：AI 分析核心】
    調用 Gemini 2.5-flash 模型，根據用戶設定的股票進行聯網分析，並回傳 HTML 格式報告。
    """
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})
    
    # 設定台灣時區
    tz_tw = timezone(timedelta(hours=8))
    current_date = datetime.now(tz_tw).strftime('%Y年%m月%d日')
    
    # 根據小時判斷主旨標籤
    report_label = "早盤動態掃描" if current_hour < 12 else "午盤交叉分析"
    subject = f"【Market Oracle】{report_label} ({current_date})"
    
    # --- 你的核心 Prompt (鎖死 HTML 格式與邏輯) ---
    prompt = (
        f"今天是 {current_date}。請針對股票：{', '.join(stocks)} 進行 24 小時內的深度市場掃描。"
        f"**【最高核心指令：時間邏輯與連結鎖定】**\n"
        f"1. **強制時間校對**：禁止僅憑標題判斷。必須深度解析網頁 Metadata (datePublished)、Meta 標籤或網址中的日期路徑。絕對禁止引用任何實際發佈於 {current_date} 之前的新聞，僅限 24 小時內動態。\n"
        f"2. **Forbes 連結過濾**：若引用 Forbes，路徑必須使用官方頻道（如 sites/greatspeculations/），絕對禁止使用 sites/trefis/ 等協力廠商路徑。\n"
        f"3. **Economic Times 修正**：若引用 indiatimes.com，網址後方必須包含 '?from=mdr' 參數以確保存取正常。\n"
        f"請嚴格依照 HTML 格式輸出，禁止使用 Markdown（如 ** 或 #）。<br><br>\n\n"
        "【內容規範與格式】：\n"
        "1. **今日亮點導讀**：置頂開頭，使用以下樣式。用 **一行字** 總結這些標的今日的集體走勢核心原因：\n"
        "   <div style='background: #f8f9fa; padding: 15px; border-left: 5px solid #1a73e8; margin-bottom: 25px; font-weight: bold;'>今日亮點導讀：{一行字總結}</div>\n\n"
        "2. **極簡分析 (每支股票)**：\n"
        "   - **標題行 (絕對禁止換行)**：<div style='font-size: 18px; color: #1a73e8; font-weight: bold; white-space: nowrap;'>{標準代號} ▸ <span style='font-size: 14px; color: #333;'>[{日期} {價格狀態}] {最新價格} {單位}</span> {漲跌幅樣式}</div>\n"
        "     * **漲跌顏色鎖死指令**：請勿讓漲跌幅文字變成超連結藍色。必須嚴格執行：\n"
        "       - 美股(英文代號)：漲用 <span style='color: #00ad2f;'>(+X%)</span>，跌用 <span style='color: #d12e2e;'>(-X%)</span>。\n"
        "       - 台股(數字代號)：漲用 <span style='color: #d12e2e;'>(+X%)</span>，跌用 <span style='color: #00ad2f;'>(-X%)</span>。\n"
        "   - **修正提示 (強制檢查點)**：如果輸入代號非標準，此行「必須」出現在標題正下方。格式：<div style='font-size: 12px; color: #666; margin: 2px 0 8px 0;'>(您輸入的是 {輸入字串}，但我想您指的應該是 {標準代號})</div>\n"
        "     * **禁止省略規則**：即便你認為標準代號已在標題顯示，只要 {輸入字串} 與 {標準代號} 不同，就必須顯示此備註，不得私自優化掉。"
        "   - **核心動態**：<li style='margin-top: 8px; list-style: none;'><b style='color: #e67e22; font-size: 12px;'>[24H 關鍵影響]</b> <a href='{新聞原始網址}' style='color: #1a73e8; text-decoration: none;'>{新聞標題內容}</a>{動態保底備註}</li>\n"
        "   - **AI 辣評 (必須另起一行)**：<div style='margin: 8px 0 10px 25px; color: #555; font-size: 14px;'>AI 辣評：限 40 字內。基於上述新聞，直接分析對「短期股價」的具體衝擊。</div>\n"
        "   - <hr style='border: 0; border-top: 1px solid #eee; margin: 20px 0;'>\n\n"
        "3. **連結與數量限制 (最高警戒規則)**：\n"
        "   - **嚴禁無效連結 (核心禁令)**：提供的網址必須直達文章「具體內容頁」。【絕對禁止】連結至媒體首頁、分類頁、Google 搜尋轉址，以及 google.com/grounding 形式的加密轉址。\n"
        "   - **動態保底備註邏輯 (看情況說話)**：\n"
        "     * 情況 A (網址有轉址/加密風險而導向 Yahoo Finance)：標題後方加 <span style='color: #888; font-size: 11px;'>(為確保連結有效性，已優先提供經貿數據平台之深度報導)</span>。\n"
        "     * 情況 B (真的完全找不到 24 小時內之新聞)：標題後方加 <span style='color: #888; font-size: 11px;'>(今日無重大影響新聞，故直接給予經貿數據平台)</span>。\n"
        "   - **數量與一致性**：每支股票僅限 1 則影響最大新聞，標題必須與內容吻合。\n\n"
        "4. **格式要求**：禁止輸出 ```html 字樣、禁止 Markdown 粗體、禁止贅字。"
    )

    try:
        # 執行 Gemini 生成
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.0, 
                max_output_tokens=8192 
            )
        )
        # 清理輸出內容，移除 Markdown 標籤
        raw_text = response.text
        clean_html = raw_text.replace("```html", "").replace("```HTML", "").replace("```", "").strip()
        
        # 移除 Gemini 可能附加的參考資料區塊
        for marker in ["Sources:", "References:", "Footnotes:", "Grounding:", "參考資料:"]:
            clean_html = clean_html.split(marker)[0]
        
        # 驗證內容長度並發送
        if len(clean_html) > 50:
            send_email(subject, clean_html.strip(), recipients)
            return True
        return False
    except Exception as e:
        print(f"Gemini 生成錯誤: {str(e)}")
        return False

def lambda_handler(event, context):
    """
    【主程式：Lambda 入口】
    負責分流處理：DB 測試、手動測試、定時排程、API 訂閱請求。
    """
    # 設定回傳 Header（支援前端跨域請求）
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "OPTIONS,GET,POST"
    }
    tz_tw = timezone(timedelta(hours=8))
    now = datetime.now(tz_tw)
    current_hour = now.hour

    # --- 分流 1：執行資料庫連線測試 (action == "test_db") ---
    if event.get("action") == "test_db":
        return dbtest_function.lambda_handler(event, context)

    # --- 分流 2：AWS 控制台手動測試 (manual == True) ---
    # 強制發送到你的開發者信箱，不影響真實用戶
    if event.get("manual") == True:
        stocks = [s.strip() for s in os.getenv("STOCK_LIST", "NVDA").split(",") if s.strip()]
        developer_email = ["roserain610@gmail.com"]
        run_gemini_analysis(stocks, developer_email, current_hour)
        return {"statusCode": 200, "body": "Manual Test Success - Sent to Developer"}

    # --- 分流 3：定時排程觸發 (action == "scheduled_dispatch") ---
    # 由 EventBridge 根據 Cron 設定觸發，會掃描 DB 中狀態為 active 的用戶
    if event.get("action") == "scheduled_dispatch":
        shift = event.get("shift") # 'MORNING' 或 'AFTERNOON'
        users = table.scan(
            FilterExpression="(#s = :shift OR #s = :both) AND #st = :active",
            ExpressionAttributeNames={"#s": "schedule", "#st": "status"},
            ExpressionAttributeValues={":shift": shift, ":both": "BOTH", ":active": "active"}
        )['Items']
        for user in users:
            run_gemini_analysis(user['stocks'], [user['email']], current_hour)
        return {"statusCode": 200, "body": "Scheduled Dispatch OK"}

    # --- 分流 4：API Gateway 入口 (處理網頁請求) ---
    method = event.get('httpMethod')

    # 【POST：Subscribe, Update, Unsubscribe】
    if method == 'POST':
        body = json.loads(event.get('body', '{}'))
        email = body.get('email', '').strip()
        action = body.get('action') 

        # 1. Basic Email Validation
        if not email or "@" not in email:
            return {"statusCode": 400, "headers": headers, "body": json.dumps({"message": "Please enter a valid email address."})}

        # 2. [Core] Pre-fetch DB record
        res = table.get_item(Key={'email': email})
        existing_item = res.get('Item')
        is_existing = existing_item is not None

        # 3. [Core] Quota Guard (Blocks new users if active/pending >= 10)
        # We don't block existing users who are just updating or unsubscribing
        if not is_existing and action != "unsubscribe":
            count_res = table.scan(
                FilterExpression="#st = :active OR #st = :pending",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={":active": "active", ":pending": "pending"},
                Select='COUNT'
            )
            if count_res.get('Count', 0) >= 10:
                return {
                    "statusCode": 403, 
                    "headers": headers, 
                    "body": json.dumps({"message": "quota_limit_reached"})
                }

        # 4. Handle Unsubscribe Action
        if action == "unsubscribe":
            table.update_item(
                Key={'email': email},
                UpdateExpression="set #st = :inactive, updated_at = :now",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={":inactive": "inactive", ":now": str(now)}
            )
            return {"statusCode": 200, "headers": headers, "body": json.dumps({"status": "inactive", "message": "Unsubscribed successfully."})}

        # 5. Handle normal subscription/update logic
        stocks = body.get('stocks', [])
        schedule = body.get('schedule', 'AFTERNOON')
        trigger_now = body.get('trigger_now', False)

        if not stocks:
            return {"statusCode": 400, "headers": headers, "body": json.dumps({"message": "Watchlist cannot be empty."})}

        # 6. Check SES verification status
        v_res = ses.get_identity_verification_attributes(Identities=[email])
        ses_status = v_res['VerificationAttributes'].get(email, {}).get('VerificationStatus', 'None')
        
        if ses_status == "Success":
            # CASE: Already verified (includes returning inactive users)
            old_status = existing_item.get('status', 'none') if is_existing else 'none'
            table.put_item(Item={'email': email, 'stocks': stocks, 'schedule': schedule, 'status': 'active', 'updated_at': str(now)})
            
            msg = "Settings updated."
            if old_status == "inactive": 
                msg = "Welcome back! Your subscription has been reactivated."
            elif old_status == "none": 
                msg = "Subscribed! Welcome to Market Oracle."

            if trigger_now:
                run_gemini_analysis(stocks, [email], current_hour)
                msg = "Report has been sent successfully."

            return {"statusCode": 200, "headers": headers, "body": json.dumps({"status": "active", "message": msg})}
        else:
            # CASE: Not verified or Pending (New users or Resending verification)
            ses.verify_email_identity(EmailAddress=email)
            table.put_item(Item={'email': email, 'stocks': stocks, 'schedule': schedule, 'status': 'pending', 'updated_at': str(now)})
            return {"statusCode": 200, "headers": headers, "body": json.dumps({"status": "pending", "message": "Verification email sent. Please check your inbox."})}

    # 【GET：查詢用戶目前的訂閱狀態與歷史設定】
    if method == 'GET':
        email = event.get('queryStringParameters', {}).get('email')
        if not email:
            return {"statusCode": 400, "headers": headers, "body": json.dumps({"message": "Missing email"})}

        res = table.get_item(Key={'email': email})
        if 'Item' in res:
            item = res['Item']
            status = item.get('status')
            status_map = {"active": "訂閱中", "pending": "待驗證", "inactive": "已取消訂閱"}

            return {"statusCode": 200, "headers": headers, "body": json.dumps({
                "is_existing": True, 
                "status": status,
                "status_text": status_map.get(status, "未知狀態"),
                "stocks": item.get('stocks'),     # 歷史股票清單
                "schedule": item.get('schedule')   # 歷史排程設定
            })}
        return {"statusCode": 404, "headers": headers, "body": json.dumps({"is_existing": False})}

    return {"statusCode": 200, "headers": headers}