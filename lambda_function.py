import os
import boto3
import json
import dbtest_function  # 🚀 匯入你的測試檔
from datetime import datetime, timedelta, timezone
from google import genai
from google.genai import types

def send_email(subject, html_body, recipients):
    """透過 AWS SES 發送 HTML 格式郵件"""
    ses = boto3.client('ses', region_name='eu-west-1') 
    sender = "yuwei.lin610@gmail.com" 
    
    try:
        ses.send_email(
            Source=sender,
            Destination={'ToAddresses': recipients},
            Message={
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {
                    'Html': {'Data': html_body, 'Charset': 'UTF-8'}
                }
            }
        )
        print(f"成功寄送至: {recipients}")
    except Exception as e:
        print(f"SES 錯誤: {str(e)}")

def lambda_handler(event, context):
    # 🚀 --- 分流邏輯開始 ---
    if event.get("action") == "test_db":
        print(">>> 偵測到測試指令，執行資料庫測試 (dbtest_function)...")
        return dbtest_function.lambda_handler(event, context)
    # 🚀 --- 分流邏輯結束 ---

    # 讀取環境變數
    api_key = os.getenv("GEMINI_API_KEY")
    stock_list_env = os.getenv("STOCK_LIST", "NVDA")
    emails_env = os.getenv("RECEIVER_EMAILS", "roserain610@gmail.com")
    schedule_config = os.getenv("REPORT_SCHEDULE", "AFTERNOON") 
    
    is_manual = event.get('manual', False)
    tz_tw = timezone(timedelta(hours=8))
    now_tw = datetime.now(tz_tw)
    current_hour = now_tw.hour
    
    # 排程過濾邏輯 (維持原樣)
    if not is_manual:
        if schedule_config == "MORNING" and current_hour >= 12: return {"status": "skipped"}
        if schedule_config == "AFTERNOON" and current_hour < 12: return {"status": "skipped"}

    stocks = [s.strip() for s in stock_list_env.split(",") if s.strip()]
    recipients = [e.strip() for e in emails_env.split(",") if e.strip()]
    current_date = now_tw.strftime('%Y年%m月%d日')

    # 🚀 --- 方案 B：動態標題定義 ---
    report_label = "早盤動態掃描" if current_hour < 12 else "午盤交叉分析"
    subject = f"【Market Oracle】{report_label} ({current_date})"
    
    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})
    
    # 🚀 Day 1 終極版 + 24H 標籤 (排版精修 + 連結防禦強化版)
    prompt = (
        f"今天是 {current_date}。請針對股票：{', '.join(stocks)} 進行 24 小時內的深度市場掃描。請嚴格依照 HTML 格式輸出，禁止使用 Markdown（如 ** 或 #）。<br><br>\n\n"
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
        "     * 情況 B (真的完全找不到新聞)：標題後方加 <span style='color: #888; font-size: 11px;'>(今日無重大影響新聞，故直接給予經貿數據平台)</span>。\n"
        "   - **數量與一致性**：每支股票僅限 1 則影響最大新聞，標題必須與內容吻合。\n\n"
        "4. **格式要求**：禁止輸出 ```html 字樣、禁止 Markdown 粗體、禁止贅字。"
    )
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", # 🚀 確保為 2.5
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.0, 
                max_output_tokens=8192 
            )
        )
        
        raw_text = response.text
        clean_html = raw_text.replace("```html", "").replace("```HTML", "").replace("```", "")
        for marker in ["Sources:", "References:", "Footnotes:", "Grounding:", "參考資料:"]:
            clean_html = clean_html.split(marker)[0]
        
        clean_html = clean_html.strip()
        
        if len(clean_html) > 50:
            send_email(subject, clean_html, recipients)
            return {"status": "success"}
        else:
            return {"status": "error", "message": "Content generated too short"}
            
    except Exception as e:
        print(f"Gemini 錯誤: {str(e)}")
        return {"status": "error"}