# 📈 Market Oracle AI Agent (All-in-One)

A comprehensive, automated stock analysis ecosystem combining a **Streamlit Management Dashboard** and an **AWS Lambda Analysis Engine**.

🔗 **Live Interface:** [Market Oracle Operations Suite](https://yuwei-stock-oracle.streamlit.app/)

## 🏗️ System Architecture

This project consists of two core components working in sync:

1. **Management UI (`app.py`)**: Deployed on Streamlit Cloud, providing a visual interface to manage watchlists, subscribers, and report schedules.
2. **AI Engine (`lambda_function.py`)**: Hosted on AWS Lambda, utilizing Gemini 2.5 Flash to perform automated, search-grounded market analysis.

## 🌟 Key Features

- **Causal Analysis**: Beyond simple price tracking, the AI digs into the "Why" behind market fluctuations (e.g., earnings, macro data, or industry shifts).
- **Dual-Timezone Dashboard**: Real-time monitoring of **Dublin (IST)** and **Taipei (CST)** to track report delivery windows.
- **Dynamic Dispatch Control**: Toggle between MORNING (Post-market summary) and AFTERNOON (Pre-market outlook) analysis shifts.
- **Automated Subscriber System**: Integrated with **Amazon SES** for secure identity verification and automated email delivery to up to 5 recipients.

## 🛠️ Tech Stack

- **AI Core**: Google Gemini 2.5 Flash (via Google GenAI SDK)
- **Cloud Infrastructure**: AWS Lambda, EventBridge (Scheduler), Amazon SES (Email Service)
- **Interface**: Streamlit (Python-based Web UI)
- **SDK**: Boto3 (AWS SDK for Python)

## 🚀 Deployment Guide

### 1. Backend (AWS Lambda)

- Deploy `lambda_function.py` to an AWS Lambda function.
- Configure Environment Variables: `GEMINI_API_KEY`, `STOCK_LIST`, `RECEIVER_EMAILS`, `ADMIN_PASSWORD`, and `REPORT_SCHEDULE`.
- Set up an **EventBridge (CloudWatch Events)** trigger for your desired schedule (e.g., `0 23 * * ? *` and `0 7 * * ? *`).

### 2. Frontend (Streamlit Cloud)

- Connect this repository to Streamlit Cloud.
- **Security**: In Streamlit "Advanced Settings > Secrets", add your AWS credentials:
  ```toml
  AWS_ACCESS_KEY_ID = "YOUR_IAM_ACCESS_KEY"
  AWS_SECRET_ACCESS_KEY = "YOUR_IAM_SECRET_KEY"
  ```
