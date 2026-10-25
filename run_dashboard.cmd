@echo off
rem Dynamic Pricing Engine V2 - dashboard MVP (read-only). Opens on http://localhost:8501
cd /d "%~dp0app\dashboard"
"%~dp0.venv\Scripts\python.exe" -m streamlit run Home.py
