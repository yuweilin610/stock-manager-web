import os
import boto3
from datetime import datetime, timedelta, timezone
from google import genai
from google.genai import types

def send_email(subject, html_body, recipients):
    ses = boto3.client('ses', region_name='eu-west-1') 
    sender = "yuwei.lin610@gmail.com" 
    
    try:
        ses.send_email(
            Source=sender,
            Destination={'ToAddresses': recipients},
            Message={
                'Subject': {'Data': subject},
                'Body': {
                    'Html': {'Data': html_body}
                }
            }
        )
        print(f"成功寄送至: {recipients}")
    except Exception as e:
        print(f"SES 錯誤: {str(e)}")

def lambda_handler(event, context):
    # 1. 取得環境變數
    api_key = os.getenv("GEMINI_API_KEY")
    stock_list_env = os.getenv("STOCK_LIST", "NVDA")
    emails_env = os.getenv("RECEIVER_EMAILS", "roserain610@gmail.com")
    schedule_config = os.getenv("REPORT_SCHEDULE", "AFTERNOON") 
    
    # --- 使用內建方式取得台灣時間 (UTC+8) ---
    tz_tw = timezone(timedelta(hours=8))
    now_tw = datetime.now(tz_tw)
    current_hour = now_tw.hour
    
    # --- 時段過濾邏輯 ---
    if schedule_config == "MORNING" and current_hour >= 12:
        print(f"目前台灣時間 {current_hour} 點，設定為僅早報，跳過。")
        return {"status": "skipped"}
    if schedule_config == "AFTERNOON" and current_hour < 12:
        print(f"目前台灣時間 {current_hour} 點，設定為僅下午報，跳過。")
        return {"status": "skipped"}

    stocks = [s.strip() for s in stock_list_env.split(",") if s.strip()]
    recipients = [e.strip() for e in emails_env.split(",") if e.strip()]
    
    if not stocks:
        return {"status": "skipped", "message": "股票清單為空"}

    current_date = now_tw.strftime('%Y年%m月%d日')
    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})
    
    # 2. 建立「變動導向」的分析指令 (這是這次改動的核心)
    prompt = (
        f"今天是 {current_date}。請作為資深市場分析師，針對以下股票清單進行『變動主因分析』：{', '.join(stocks)}。\n\n"
        "分析任務：\n"
        "1. 深入剖析該標的在最近一個交易時段內出現波動的『核心原因』(如：財報公佈、產業消息、宏觀經濟數據、技術面突破等)。\n"
        "2. 如果標的波動不明顯，請總結其目前面臨的市場觀望重點或潛在風險。\n"
        "3. 搜尋並提供具有時效性的重大事件摘要。\n\n"
        "格式要求：\n"
        "1. 使用繁體中文，內容精煉、直擊痛點。\n"
        "2. 輸出格式必須是純 HTML 碼（直接從 <h3> 開始）。\n"
        "3. 嚴禁使用 Markdown 符號（如 ** 或 #）。\n"
        "4. 新聞連結請直接嵌入標題中，範例：<a href='網址'>新聞標題</a>。\n"
        "5. 股票之間用 <hr> 分隔。"
    )
    
    try:
        # 3. 呼叫 Gemini 2.5
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        
        # 清除 Markdown 標籤
        clean_html = response.text.replace("```html", "").replace("```", "").strip()
        
        # 4. 寄送 HTML 郵件
        send_email(f"【Market Oracle】變動分析報告 ({current_date})", clean_html, recipients)
        return {"status": "success", "message": f"分析完成：{len(stocks)} 支股票"}
        
    except Exception as e:
        print(f"Gemini 錯誤: {str(e)}")
        return {"status": "error", "message": str(e)}