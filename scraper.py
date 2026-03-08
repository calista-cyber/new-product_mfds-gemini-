name: Weekly Drug Approval & AI Analysis

on:
  schedule:
    - cron: '0 12 * * 5' # 매주 금요일 오후 9시 (KST)
  workflow_dispatch: # 수동 실행 버튼

jobs:
  scrape-and-analyze:
    runs-on: ubuntu-latest
    steps:
      - name: 1. 코드 체크아웃
        uses: actions/checkout@v3

      - name: 2. 파이썬 설정 (3.11 사용)
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: 3. 필수 라이브러리 설치
        run: |
          pip install requests beautifulsoup4 gspread google-auth selenium webdriver-manager

      - name: 4. 데이터 수집 (Scraper - 식약처 & 구글 시트)
        env:
          GCP_SERVICE_ACCOUNT: ${{ secrets.GCP_SERVICE_ACCOUNT }}
          GOOGLE_SHEET_ID: ${{ secrets.GOOGLE_SHEET_ID }}
          MFDS_API_KEY: ${{ secrets.MFDS_API_KEY }}
        run: python scraper.py

      - name: 5. AI 데이터 분석 (ChatGPT - 구글 시트 업데이트)
        env:
          GCP_SERVICE_ACCOUNT: ${{ secrets.GCP_SERVICE_ACCOUNT }}
          GOOGLE_SHEET_ID: ${{ secrets.GOOGLE_SHEET_ID }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }} # 🌟 다시 OpenAI로 복구!
        run: python ai_analyst.py
