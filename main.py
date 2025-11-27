"""
E-ラーニングシステム - Streamlit メインアプリケーション

このアプリケーションは、Teams チャネル内で利用可能なオンライン学習システムを提供します。
- 複数テーマの教本閲覧
- オンラインテスト実施
- 自動採点と結果保存
- メール通知機能
"""

import streamlit as st
import pandas as pd
import yaml
import json
import time
from datetime import datetime
import os
from pathlib import Path
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import gspread
from google.oauth2.service_account import Credentials

# ==================================================
# ページ設定
# ==================================================
st.set_page_config(
    page_title="E-ラーニングシステム",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================================================
# スタイル設定
# ==================================================
st.markdown("""
<style>
    .main-title {
        color: #1f77b4;
        text-align: center;
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 1rem;
    }
    .question-box {
        background-color: #f0f2f6;
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .result-box {
        background-color: #d4edda;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border-left: 5px solid #28a745;
    }
    .retake-box {
        background-color: #f8d7da;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border-left: 5px solid #dc3545;
    }
</style>
""", unsafe_allow_html=True)

# ==================================================
# 設定ファイル読み込み
# ==================================================

@st.cache_resource
def load_config():
    """config.yaml を読み込む"""
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        st.error("❌ config.yaml が見つかりません")
        st.stop()

config = load_config()

# ==================================================
# ユーティリティ関数
# ==================================================

def load_employees():
    """employees.csv を読み込む"""
    try:
        df = pd.read_csv(
            config['authentication']['employee_csv_path'],
            encoding='utf-8-sig'
        )
        return df
    except FileNotFoundError:
        st.error(f"❌ {config['authentication']['employee_csv_path']} が見つかりません")
        return None

def load_questions(theme_key):
    """テーマの問題ファイルを読み込む"""
    try:
        questions_path = config['themes'][theme_key]['questions_path']
        with open(questions_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('questions', [])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        st.error(f"❌ 問題ファイルの読み込みに失敗しました: {str(e)}")
        return None

def authenticate_user(email):
    """ユーザーを認証（employees.csv に登録されているか確認）"""
    employees_df = load_employees()
    if employees_df is None:
        return None
    
    user = employees_df[employees_df['メールアドレス'] == email]
    if len(user) > 0:
        return user.iloc[0]
    return None

def send_email_notification(recipient, subject, body):
    """メール通知を送信"""
    try:
        # 注：実際の運用では secrets.toml で GMAIL_USER, GMAIL_PASSWORD を設定
        gmail_user = st.secrets.get("GMAIL_USER")
        gmail_password = st.secrets.get("GMAIL_PASSWORD")
        
        if not gmail_user or not gmail_password:
            st.warning("⚠️ メール送信の設定がありません")
            return False
        
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = recipient
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP(config['email_settings']['smtp_server'], 
                              config['email_settings']['smtp_port'])
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        st.error(f"❌ メール送信エラー: {str(e)}")
        return False

def save_to_google_sheets(user_email, user_name, theme_title, score, time_spent, answers):
    """Google Sheets に結果を保存"""
    try:
        # 注：実際の運用では secrets.toml で google_service_account を設定
        credentials_dict = st.secrets.get("google_service_account")
        if not credentials_dict:
            st.warning("⚠️ Google Sheets の設定がありません")
            return False
        
        credentials = Credentials.from_service_account_info(credentials_dict)
        gc = gspread.authorize(credentials)
        
        spreadsheet = gc.open(config['google_sheets']['spreadsheet_name'])
        worksheet = spreadsheet.worksheet(config['google_sheets']['sheet_name'])
        
        # 新しい行を追加
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 答えを ○/✕ で表現
        answers_display = [('○' if ans else '✕') for ans in answers]
        
        row = [
            now,
            user_email,
            user_name,
            theme_title,
            score,
            time_spent,
            *answers_display,
            '-'  # メモ欄
        ]
        
        worksheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"❌ Google Sheets 保存エラー: {str(e)}")
        return False

def get_enabled_themes():
    """有効なテーマのリストを取得"""
    enabled_themes = {}
    for theme_key, theme_config in config['themes'].items():
        if theme_config.get('enabled', False):
            enabled_themes[theme_key] = theme_config
    return enabled_themes

# ==================================================
# セッション状態の初期化
# ==================================================

def init_session_state():
    """セッション状態を初期化"""
    if 'user_email' not in st.session_state:
        st.session_state.user_email = None
    if 'user_name' not in st.session_state:
        st.session_state.user_name = None
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 'login'
    if 'selected_theme' not in st.session_state:
        st.session_state.selected_theme = None
    if 'start_time' not in st.session_state:
        st.session_state.start_time = None
    if 'quiz_answers' not in st.session_state:
        st.session_state.quiz_answers = {}
    if 'quiz_score' not in st.session_state:
        st.session_state.quiz_score = None

init_session_state()

# ==================================================
# ページ: ログイン
# ==================================================

def show_login_page():
    """ログインページを表示"""
    st.markdown('<div class="main-title">📚 E-ラーニングシステム</div>', 
                unsafe_allow_html=True)
    
    st.markdown("""
    ---
    Teams を通じたオンライン学習プラットフォームへようこそ。
    
    メールアドレスを入力してログインしてください。
    """)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.info("📌 会社のメールアドレス（@company.onmicrosoft.com）を入力してください")
        
        email = st.text_input(
            "メールアドレス",
            placeholder="user@company.onmicrosoft.com",
            key="login_email"
        )
        
        st.markdown("---")
        
        if st.button("ログイン", use_container_width=True, type="primary"):
            if not email:
                st.error("❌ メールアドレスを入力してください")
            else:
                user = authenticate_user(email)
                if user is not None:
                    st.session_state.user_email = email
                    st.session_state.user_name = user['フルネーム']
                    st.session_state.current_page = 'dashboard'
                    st.success(f"✅ ログインしました！{user['フルネーム']}さん")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ このメールアドレスは登録されていません。\n\n管理者に確認してください。")

# ==================================================
# ページ: ダッシュボード
# ==================================================

def show_dashboard():
    """ダッシュボードを表示"""
    st.markdown('<div class="main-title">📊 ダッシュボード</div>', 
                unsafe_allow_html=True)
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown(f"### ようこそ、{st.session_state.user_name}さん！")
    
    with col2:
        if st.button("ログアウト", key="logout_btn"):
            st.session_state.user_email = None
            st.session_state.user_name = None
            st.session_state.current_page = 'login'
            st.rerun()
    
    st.markdown("---")
    
    # 利用可能なテーマを表示
    enabled_themes = get_enabled_themes()
    
    if len(enabled_themes) == 0:
        st.warning("⚠️ 現在利用可能なテーマはありません")
        return
    
    st.subheader("📖 利用可能なテーマ")
    
    for theme_key, theme_config in enabled_themes.items():
        col1, col2, col3 = st.columns([2, 2, 1])
        
        with col1:
            st.markdown(f"#### {theme_config['title']}")
            st.write(theme_config['description'])
        
        with col2:
            st.markdown(f"**制限時間:** {theme_config['time_limit_minutes']}分")
            st.markdown(f"**合格点:** {theme_config['passing_score']}点")
        
        with col3:
            if st.button("学習を開始", key=f"start_{theme_key}", use_container_width=True):
                st.session_state.selected_theme = theme_key
                st.session_state.current_page = 'learning'
                st.session_state.start_time = datetime.now()
                st.rerun()
    
    st.markdown("---")
    
    # メール通知の案内
    st.info("""
    📧 **メール通知について**
    
    学習を開始すると、管理者に以下の通知が送信されます：
    - ✉️ 受講開始通知
    - ✉️ 解答完了通知（スコア付き）
    - ✉️ 再受講案内（基準点未満の場合）
    """)

# ==================================================
# ページ: 学習（教本表示）
# ==================================================

def show_learning_page():
    """学習ページ（教本表示）を表示"""
    theme_key = st.session_state.selected_theme
    theme_config = config['themes'][theme_key]
    
    st.markdown(f'<div class="main-title">{theme_config["title"]}</div>', 
                unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 3, 1])
    
    with col1:
        if st.button("← ダッシュボードに戻る"):
            st.session_state.current_page = 'dashboard'
            st.session_state.selected_theme = None
            st.rerun()
    
    with col3:
        if st.button("クイズへ進む →"):
            st.session_state.current_page = 'quiz'
            st.rerun()
    
    st.markdown("---")
    
    # PDF を表示
    st.subheader("📖 教本")
    
    pdf_path = theme_config['pdf_path']
    
    if os.path.exists(pdf_path):
        with open(pdf_path, 'rb') as pdf_file:
            st.download_button(
                label="PDF をダウンロード",
                data=pdf_file.read(),
                file_name=os.path.basename(pdf_path),
                mime="application/pdf"
            )
        
        # PDF をブラウザで表示
        with open(pdf_path, 'rb') as pdf_file:
            st.pdfviewer(pdf_file)
    else:
        st.warning(f"⚠️ PDF が見つかりません: {pdf_path}")

# ==================================================
# ページ: クイズ
# ==================================================

def show_quiz_page():
    """クイズページを表示"""
    theme_key = st.session_state.selected_theme
    theme_config = config['themes'][theme_key]
    
    st.markdown(f'<div class="main-title">❓ {theme_config["title"]} - クイズ</div>', 
                unsafe_allow_html=True)
    
    time_limit = theme_config['time_limit_minutes']
    passing_score = theme_config['passing_score']
    
    # 制限時間の計算
    elapsed_time = (datetime.now() - st.session_state.start_time).total_seconds() / 60
    remaining_time = time_limit - elapsed_time
    
    # タイマー表示
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.markdown(f"**テーマ:** {theme_config['title']}")
    
    with col2:
        if remaining_time > 0:
            st.markdown(f"⏱️ **残り時間:** {int(remaining_time)}分 {int((remaining_time % 1) * 60)}秒")
        else:
            st.error(f"⏱️ **時間超過！自動提出します...**")
            # 自動提出
            show_result_page()
            return
    
    with col3:
        if st.button("← 教本に戻る"):
            st.session_state.current_page = 'learning'
            st.rerun()
    
    st.markdown("---")
    
    # 問題を読み込む
    questions = load_questions(theme_key)
    
    if questions is None:
        st.error("❌ 問題の読み込みに失敗しました")
        return
    
    # 問題を表示
    for i, question in enumerate(questions, 1):
        with st.container():
            st.markdown(f'<div class="question-box">', unsafe_allow_html=True)
            
            st.markdown(f"### 問題 {i} / {len(questions)}")
            st.markdown(f"**{question['question']}**")
            
            # ラジオボタンで選択肢を表示
            answer = st.radio(
                "選択肢を選んでください",
                question['options'],
                key=f"q_{i}",
                label_visibility="collapsed"
            )
            
            # ユーザーの回答を記録
            selected_index = question['options'].index(answer)
            st.session_state.quiz_answers[i] = (selected_index == question['correct_answer'])
            
            st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 提出ボタン
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("← 教本に戻る", use_container_width=True):
            st.session_state.current_page = 'learning'
            st.rerun()
    
    with col2:
        if st.button("答案を提出 →", use_container_width=True, type="primary"):
            # スコア計算
            correct_count = sum(st.session_state.quiz_answers.values())
            score = int((correct_count / len(questions)) * 100)
            time_spent = int(elapsed_time)
            
            st.session_state.quiz_score = score
            st.session_state.quiz_time_spent = time_spent
            st.session_state.current_page = 'result'
            
            # Google Sheets に保存
            answers_list = [st.session_state.quiz_answers.get(i + 1, False) 
                           for i in range(len(questions))]
            save_to_google_sheets(
                st.session_state.user_email,
                st.session_state.user_name,
                theme_config['title'],
                score,
                f"{time_spent}分",
                answers_list
            )
            
            # メール通知
            if config['email_settings']['send_on_completion']:
                for admin in config['admins']:
                    send_email_notification(
                        admin,
                        f"[E-ラーニング] {st.session_state.user_name}さんが完了しました",
                        f"""
{st.session_state.user_name}さん（{st.session_state.user_email}）が
「{theme_config['title']}」の学習を完了しました。

【結果】
- スコア: {score}点
- 所要時間: {time_spent}分
- 合否: {'合格 ✅' if score >= passing_score else '不合格 ❌'}
                        """
                    )
            
            st.rerun()

# ==================================================
# ページ: 結果
# ==================================================

def show_result_page():
    """結果ページを表示"""
    theme_key = st.session_state.selected_theme
    theme_config = config['themes'][theme_key]
    passing_score = theme_config['passing_score']
    
    score = st.session_state.quiz_score
    time_spent = st.session_state.quiz_time_spent
    
    st.markdown(f'<div class="main-title">📈 クイズ結果</div>', 
                unsafe_allow_html=True)
    
    # 成績表示
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("スコア", f"{score}点", f"{'+' if score >= passing_score else '-'}")
    
    with col2:
        st.metric("所要時間", f"{time_spent}分")
    
    with col3:
        pass_status = "合格 ✅" if score >= passing_score else "不合格 ❌"
        st.markdown(f"### {pass_status}")
    
    st.markdown("---")
    
    # 合否判定
    if score >= passing_score:
        st.markdown("""
        <div class="result-box">
            <h3>🎉 合格です！</h3>
            <p>おめでとうございます。このテーマの学習を修了しました。</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="retake-box">
            <h3>📚 再受講をお勧めします</h3>
            <p>合格点（{passing_score}点）に達していません。</p>
            <p>教本を再度確認してから、再度受講することをお勧めします。</p>
        </div>
        """, unsafe_allow_html=True)
        
        # 再受講案内メール
        if config['email_settings']['send_on_retake_needed']:
            for admin in config['admins']:
                send_email_notification(
                    admin,
                    f"[E-ラーニング] {st.session_state.user_name}さんが再受講対象になりました",
                    f"""
{st.session_state.user_name}さん（{st.session_state.user_email}）は
「{theme_config['title']}」の再受講対象になりました。

【結果】
- スコア: {score}点
- 合格点: {passing_score}点
- 所要時間: {time_spent}分

管理者より、フォローアップをお願いします。
                    """
                )
    
    st.markdown("---")
    
    # ナビゲーションボタン
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("← ダッシュボードに戻る", use_container_width=True):
            st.session_state.current_page = 'dashboard'
            st.session_state.selected_theme = None
            st.session_state.quiz_answers = {}
            st.session_state.quiz_score = None
            st.rerun()
    
    with col2:
        if st.button("別のテーマを学習 →", use_container_width=True):
            st.session_state.current_page = 'dashboard'
            st.session_state.selected_theme = None
            st.session_state.quiz_answers = {}
            st.session_state.quiz_score = None
            st.rerun()

# ==================================================
# メインロジック
# ==================================================

def main():
    """メイン処理"""
    
    # ページ遷移
    if st.session_state.current_page == 'login' or st.session_state.user_email is None:
        show_login_page()
    elif st.session_state.current_page == 'dashboard':
        show_dashboard()
    elif st.session_state.current_page == 'learning':
        show_learning_page()
    elif st.session_state.current_page == 'quiz':
        show_quiz_page()
    elif st.session_state.current_page == 'result':
        show_result_page()

if __name__ == "__main__":
    main()
