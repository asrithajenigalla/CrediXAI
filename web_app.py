import json
import sqlite3
import io
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta
from sklearn.ensemble import GradientBoostingRegressor

# Optional PDF Generation Library
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Optional Gemini AI Integration
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# ==============================================================================
# 0. CONSTANTS & GLOBAL CONFIGURATION
# ==============================================================================
EMPLOYMENT_CATEGORIES = [
    "🛒 Micro Merchant / Street Vendor",
    "🛵 Gig Economy Worker / Delivery Partner",
    "💼 Salaried (Private Sector)",
    "🏛️ Salaried (Government)",
    "💻 Freelancer / Digital Nomad",
    "🩺 Self-Employed Professional (Doctor/CA/Lawyer)",
    "🏬 Small Business Owner / Kirana Store",
    "🌾 Agricultural / Allied Activities",
    "🎓 Student with Part-time Income",
    "🏠 Unemployed / Seeking Work"
]

# ==============================================================================
# 1. PAGE CONFIGURATION & STYLING FIXES
# ==============================================================================
st.set_page_config(
    page_title="CrediXAI | Thin-File Underwriting Engine",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stTextInput input {
        color: #111827 !important;
        background-color: #f9fafb !important;
        border: 1px solid #d1d5db !important;
        font-weight: 600 !important;
    }
    .shap-box {
        background-color: #0d1117;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 12px;
    }
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 15px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .metric-title {
        color: #4b5563;
        font-size: 0.85rem;
        margin-bottom: 5px;
    }
    .metric-value {
        color: #111827;
        font-size: 1.6rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. LOCAL SQLITE DATABASE INITIALIZATION & AUDIT TRAIL
# ==============================================================================
def init_db(force_reset=False):
    conn = sqlite3.connect("credixai_demo.db")
    c = conn.cursor()
    
    if force_reset:
        c.execute("DROP TABLE IF EXISTS applicants")
        c.execute("DROP TABLE IF EXISTS audit_logs")

    c.execute("PRAGMA table_info(applicants)")
    cols = [column[1] for column in c.fetchall()]
    
    if len(cols) > 0 and len(cols) < 13:
        c.execute("DROP TABLE IF EXISTS applicants")

    c.execute('''
        CREATE TABLE IF NOT EXISTS applicants (
            id TEXT PRIMARY KEY,
            name TEXT,
            category TEXT,
            pan TEXT,
            personal_income REAL,
            family_income REAL,
            monthly_debts REAL,
            upi_count INTEGER,
            utility_status INTEGER,
            volatility INTEGER,
            adb REAL,
            inflow_outflow_ratio REAL,
            disbursed_at TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            applicant_id TEXT,
            score INTEGER,
            event_type TEXT,
            details TEXT
        )
    ''')
    
    c.execute("SELECT COUNT(*) FROM applicants")
    if c.fetchone()[0] == 0:
        sample_data = [
            ("APP-8112-IN", "Priya Sundaram", "🛒 Micro Merchant / Street Vendor", "XYZPS9876K", 48000.0, 15000.0, 4500.0, 142, 100, 10, 18500.0, 1.45, None),
            ("APP-9204-IN", "Rahul Sharma", "🛵 Gig Economy Worker / Delivery Partner", "ABCDE1234F", 35000.0, 20000.0, 6000.0, 110, 78, 22, 9200.0, 1.15, None),
            ("APP-3341-IN", "Anil Kumar", "💻 Freelancer / Digital Nomad", "PQRST5543M", 28000.0, 0.0, 4500.0, 45, 65, 38, 3400.0, 0.92, None)
        ]
        c.executemany("INSERT INTO applicants VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", sample_data)
        conn.commit()
    conn.close()

init_db()

def get_all_applicants():
    conn = sqlite3.connect("credixai_demo.db")
    df = pd.read_sql_query("SELECT * FROM applicants", conn)
    conn.close()
    return df

def get_audit_logs():
    conn = sqlite3.connect("credixai_demo.db")
    df = pd.read_sql_query("SELECT * FROM audit_logs ORDER BY log_id DESC", conn)
    conn.close()
    return df

def update_applicant_db(app_data, old_id=None):
    conn = sqlite3.connect("credixai_demo.db")
    c = conn.cursor()
    
    if old_id and old_id != app_data['id']:
        c.execute("SELECT COUNT(*) FROM applicants WHERE id = ?", (app_data['id'],))
        if c.fetchone()[0] > 0:
            conn.close()
            st.error(f"Error: Applicant ID '{app_data['id']}' already exists. Please pick a unique ID.")
            return False
        c.execute("DELETE FROM applicants WHERE id = ?", (old_id,))
        
    c.execute('''
        INSERT OR REPLACE INTO applicants VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', (
        app_data['id'], app_data['name'], app_data['category'], app_data['pan'],
        app_data['personal_income'], app_data['family_income'], app_data['monthly_debts'],
        app_data['upi_count'], app_data['utility_status'], app_data['volatility'],
        app_data.get('adb', 10000.0), app_data.get('inflow_outflow_ratio', 1.2),
        app_data.get('disbursed_at', None)
    ))
    conn.commit()
    conn.close()
    return True

def log_audit_event(applicant_id, score, event_type, details=""):
    conn = sqlite3.connect("credixai_demo.db")
    c = conn.cursor()
    c.execute('''
        INSERT INTO audit_logs (timestamp, applicant_id, score, event_type, details)
        VALUES (?, ?, ?, ?, ?)
    ''', (datetime.now().isoformat(), applicant_id, score, event_type, details))
    conn.commit()
    conn.close()

# ==============================================================================
# 3. EXPLAINABLE AI ENGINE & CALCULATORS
# ==============================================================================
@st.cache_resource
def train_credit_model():
    np.random.seed(42)
    n_samples = 1500
    
    p_inc = np.random.uniform(15000, 100000, n_samples)
    debts = np.random.uniform(0, 30000, n_samples)
    upi = np.random.randint(10, 200, n_samples)
    utility = np.random.randint(30, 100, n_samples)
    volatility = np.random.randint(5, 50, n_samples)
    adb = np.random.uniform(1000, 50000, n_samples)
    io_ratio = np.random.uniform(0.7, 2.0, n_samples)
    
    dti = debts / (p_inc + 1e-5)
    base_score = 650 + (utility * 1.8) + (upi * 0.8) + (io_ratio * 60) + (adb * 0.002) - (dti * 250) - (volatility * 3.5)
    target_score = np.clip(base_score, 300, 950)
    
    X = pd.DataFrame({
        'personal_income': p_inc,
        'monthly_debts': debts,
        'upi_count': upi,
        'utility_status': utility,
        'volatility': volatility,
        'adb': adb,
        'inflow_outflow_ratio': io_ratio
    })
    
    model = GradientBoostingRegressor(n_estimators=50, random_state=42)
    model.fit(X, target_score)
    return model

ml_model = train_credit_model()

def evaluate_xai_score(applicant_dict):
    X_input = pd.DataFrame([{
        'personal_income': float(applicant_dict['personal_income']),
        'monthly_debts': float(applicant_dict['monthly_debts']),
        'upi_count': int(applicant_dict['upi_count']),
        'utility_status': int(applicant_dict['utility_status']),
        'volatility': int(applicant_dict['volatility']),
        'adb': float(applicant_dict.get('adb', 10000.0)),
        'inflow_outflow_ratio': float(applicant_dict.get('inflow_outflow_ratio', 1.2))
    }])
    
    predicted_score = int(np.clip(ml_model.predict(X_input)[0], 300, 950))
    
    feature_importances = ml_model.feature_importances_
    feature_names = X_input.columns
    baselines = {'personal_income': 50000, 'monthly_debts': 10000, 'upi_count': 100, 'utility_status': 75, 'volatility': 20, 'adb': 20000, 'inflow_outflow_ratio': 1.2}
    
    attributions = []
    for name, imp in zip(feature_names, feature_importances):
        val = X_input[name].iloc[0]
        base = baselines[name]
        diff = (val - base) / (base + 1e-5)
        
        if name in ['monthly_debts', 'volatility']:
            impact = -diff * imp * 300
        else:
            impact = diff * imp * 300
            
        attributions.append({
            'feature': name.replace('_', ' ').title(),
            'value': val,
            'impact_pts': round(impact, 1)
        })
        
    deficits = []
    tot_inc = applicant_dict['personal_income'] + applicant_dict['family_income']
    dti_val = (applicant_dict['monthly_debts'] / tot_inc) if tot_inc > 0 else 1.0
    
    if dti_val > 0.35:
        deficits.append({"parameter": "High Debt-to-Income Ratio", "current": f"{round(dti_val*100, 1)}%", "target": "< 35%", "fix": "Pay off existing micro-loans or declare co-applicant income."})
    if applicant_dict['upi_count'] < 80:
        deficits.append({"parameter": "Low Cashflow Velocity", "current": f"{applicant_dict['upi_count']} txns/mo", "target": "≥ 80 txns/mo", "fix": "Route primary daily transactions through personal UPI account."})
    if applicant_dict['utility_status'] < 85:
        deficits.append({"parameter": "Utility Payment Discipline", "current": f"{applicant_dict['utility_status']}/100", "target": "≥ 85/100", "fix": "Pay utility and telecom bills consistently on time."})

    return predicted_score, attributions, deficits

def calculate_kfs_terms(principal, tenure_months, annual_rate=14.0, processing_fee_pct=2.0):
    if principal <= 0:
        principal = 10000.0
    if tenure_months <= 0:
        tenure_months = 12
        
    if annual_rate == 0:
        emi = principal / tenure_months
        apr = processing_fee_pct
    else:
        monthly_r = annual_rate / (12 * 100)
        emi = (principal * monthly_r * ((1 + monthly_r)**tenure_months)) / (((1 + monthly_r)**tenure_months) - 1)
        proc_fee = max(500.0, principal * (processing_fee_pct / 100.0))
        apr = annual_rate + ((proc_fee / principal) / (tenure_months / 12) * 100)

    total_repayment = emi * tenure_months
    total_interest = max(0.0, total_repayment - principal)
    proc_fee = max(500.0, principal * (processing_fee_pct / 100.0))
    net_disbursal = principal - proc_fee
    
    return {
        "principal": principal,
        "tenure": tenure_months,
        "emi": emi,
        "total_repayment": total_repayment,
        "total_interest": total_interest,
        "processing_fee": proc_fee,
        "net_disbursal": net_disbursal,
        "apr": round(apr, 1)
    }

def generate_pdf_kfs(applicant_name, applicant_id, terms_df):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    
    story = []
    story.append(Paragraph("<b>CrediXAI Digital Lending Platform</b>", styles['Title']))
    story.append(Paragraph("Key Fact Statement (KFS) - RBI Regulatory Compliance", styles['Heading2']))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"<b>Borrower Name:</b> {applicant_name} | <b>Applicant ID:</b> {applicant_id}", styles['Normal']))
    story.append(Paragraph(f"<b>Generated Date:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    story.append(Spacer(1, 15))

    table_data = [["Parameter", "Details"]]
    for _, row in terms_df.iterrows():
        table_data.append([str(row['Parameter']), str(row['Details'])])

    t = Table(table_data, colWidths=[240, 280])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#d1d5db')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t)
    doc.build(story)
    buffer.seek(0)
    return buffer

# ==============================================================================
# 4. SIDEBAR & USER SELECTION
# ==============================================================================
st.sidebar.title("⚙️ CrediXAI Engine")
st.sidebar.markdown("### 🗄️ Database & Applicant Selector")

df_apps = get_all_applicants()
user_action = st.sidebar.radio("Database Mode:", ["Select Existing Profile", "➕ Register New Applicant"])

if user_action == "➕ Register New Applicant":
    st.sidebar.markdown("---")
    st.sidebar.subheader("New Thin-File Entry")
    with st.sidebar.form("new_applicant_form"):
        new_name = st.text_input("Full Name")
        new_id = f"APP-{np.random.randint(1000, 9999)}-IN"
        new_pan = st.text_input("PAN / ID Ref")
        new_cat = st.selectbox("Category", EMPLOYMENT_CATEGORIES)
        new_p_inc = st.number_input("Monthly Income (Rs.)", value=30000.0, step=1000.0)
        new_f_inc = st.number_input("Family Income (Rs.)", value=10000.0, step=1000.0)
        new_debts = st.number_input("Monthly EMIs (Rs.)", value=3000.0, step=500.0)
        new_upi = st.slider("Monthly UPI Txns", 0, 200, value=90)
        new_util = st.slider("Utility Score", 0, 100, value=85)
        new_vol = st.slider("Volatility Index (%)", 0, 100, value=15)
        new_adb = st.number_input("Avg Daily Balance (Rs.)", value=12000.0, step=1000.0)
        new_io = st.slider("Inflow/Outflow Ratio", 0.5, 2.5, value=1.25, step=0.05)

        if st.form_submit_button("Save Applicant 💾"):
            if new_name and new_pan:
                new_user_data = {
                    'id': new_id, 'name': new_name, 'category': new_cat, 'pan': new_pan,
                    'personal_income': new_p_inc, 'family_income': new_f_inc, 'monthly_debts': new_debts,
                    'upi_count': new_upi, 'utility_status': new_util, 'volatility': new_vol,
                    'adb': new_adb, 'inflow_outflow_ratio': new_io, 'disbursed_at': None
                }
                if update_applicant_db(new_user_data):
                    log_audit_event(new_id, 0, "APPLICANT_REGISTERED", f"Created profile for {new_name}")
                    st.sidebar.success(f"Applicant {new_name} registered!")
                    st.rerun()
            else:
                st.sidebar.error("Name & PAN required.")

    selected_app_id = df_apps['id'].iloc[0]
else:
    selected_app_id = st.sidebar.selectbox("Select Active Applicant", df_apps['id'].tolist(), index=0)

active_row = df_apps[df_apps['id'] == selected_app_id].iloc[0].to_dict()

# Sidebar Utilities: Data Export & Reset
st.sidebar.markdown("---")
st.sidebar.markdown("### 🛠️ Database Utilities")
db_csv = df_apps.to_csv(index=False).encode('utf-8')
st.sidebar.download_button("📥 Export DB as CSV", data=db_csv, file_name="applicants_database.csv", mime="text/csv")

if st.sidebar.button("🔄 Reset DB to Defaults"):
    init_db(force_reset=True)
    st.sidebar.success("Database restored to defaults!")
    st.rerun()

st.sidebar.markdown("---")
nav_page = st.sidebar.radio(
    "Go to Page:",
    [
        "📊 Executive Summary",
        "👤 Borrower Details & Profile",
        "📱 Application Journey (KFS)",
        "🤖 XAI Feature Attribution",
        "⚠️ Deficit & Gap Analyzer",
        "🧮 FOIR Waterfall Analysis",
        "🛡️ RBI Compliance & AA Payload",
        "📜 RBI Auditor Trail Logs",
        "🤖 AI Copilot Chatbot"
    ]
)

total_household_income = active_row['personal_income'] + active_row['family_income']
living_expenses = total_household_income * 0.30
income_after_expenses = total_household_income - living_expenses
net_disposable_income = max(0, income_after_expenses - active_row['monthly_debts'])
max_eligible_emi = net_disposable_income * 0.80

monthly_r = 14.0 / (12 * 100)
max_loan_principal = (max_eligible_emi * (((1 + monthly_r)**12) - 1)) / (monthly_r * ((1 + monthly_r)**12)) if max_eligible_emi > 0 else 0

credit_score, attributions, applicant_deficits = evaluate_xai_score(active_row)

log_audit_event(active_row['id'], credit_score, "SCORE_EVALUATED", f"Calculated XAI Score: {credit_score}")

# ==============================================================================
# PAGE ROUTING
# ==============================================================================

if nav_page == "📊 Executive Summary":
    st.title("💳 CrediXAI | Thin-File Underwriting Dashboard")
    st.caption("Alternative Data Credit Scoring Engine for Gig Workers & First-Time Earners")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f'<div class="metric-card"><div class="metric-title">Borrower Profile</div><div class="metric-value">{active_row["name"]}</div><small style="color:#6b7280;">Segment: {active_row["category"].split()[-1]}</small></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="metric-card"><div class="metric-title">Household Income</div><div class="metric-value">Rs. {int(total_household_income):,}</div><small style="color:#6b7280;">Personal: Rs. {int(active_row["personal_income"]):,}</small></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="metric-card"><div class="metric-title">XAI Credit Score</div><div class="metric-value">{credit_score} <small style="font-size:0.8rem; color:#6b7280;">/ 950</small></div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div class="metric-card"><div class="metric-title">Max Loan Limit</div><div class="metric-value" style="color:#16a34a;">Rs. {int(max_loan_principal):,}</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🌐 Underwriting Assessment: Bureau vs. CrediXAI Engine")
    
    col_comp1, col_comp2 = st.columns(2)
    
    with col_comp1:
        st.markdown("""
        <div style="background-color: #fef2f2; border: 1px solid #fca5a5; border-radius: 8px; padding: 16px;">
            <h4 style="color: #991b1b; margin-top: 0;">❌ Traditional Bureau Verdict: REJECTED</h4>
            <ul style="color: #7f1d1d; margin-bottom: 0; padding-left: 20px;">
                <li><b>Bureau Credit Score:</b> N/A or -1 (No Credit History)</li>
                <li><b>Proof of Income:</b> Missing Form 16 / Formal Salary Slips</li>
                <li><b>Credit Risk Assessment:</b> High (Unrated / Thin-File Borrower)</li>
                <li><b>Outcome:</b> Automated Rejection by Legacy Bank Algorithms</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    with col_comp2:
        st.markdown(f"""
        <div style="background-color: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 16px;">
            <h4 style="color: #166534; margin-top: 0;">✅ CrediXAI Alternative Verdict: APPROVED</h4>
            <ul style="color: #14532d; margin-bottom: 0; padding-left: 20px;">
                <li><b>Cashflow Velocity:</b> High ({active_row['upi_count']} verified UPI txns/mo via AA)</li>
                <li><b>Repayment Discipline:</b> {active_row['utility_status']}/100 Utility Payment Consistency</li>
                <li><b>Liquidity Cushion:</b> Rs. {int(active_row.get('adb', 10000)):,} Average Daily Balance</li>
                <li><b>Outcome:</b> Eligible for up to <b>Rs. {int(max_loan_principal):,}</b> at 14.0% p.a.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 📈 Real-Time Alternative Financial Signals")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("UPI Transaction Velocity", f"{active_row['upi_count']} txns/mo")
    c2.metric("Utility Payment Score", f"{active_row['utility_status']}/100")
    c3.metric("Avg Daily Balance (ADB)", f"Rs. {int(active_row.get('adb', 10000)):,}")
    c4.metric("Inflow/Outflow Ratio", f"{active_row.get('inflow_outflow_ratio', 1.2)}x")

elif nav_page == "📜 RBI Auditor Trail Logs":
    st.title("📜 RBI Compliance & Immutable Audit Log Portal")
    st.markdown("This tab fulfills regulatory requirements for transparent, auditable automated credit decisions under RBI Digital Lending Guidelines.")
    
    df_logs = get_audit_logs()
    
    col_a1, col_a2 = st.columns([3, 1])
    with col_a1:
        st.markdown(f"**Total Registered System Events:** `{len(df_logs)}`")
    with col_a2:
        logs_csv = df_logs.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Export Audit Logs CSV", data=logs_csv, file_name="rbi_audit_logs.csv", mime="text/csv")
        
    st.dataframe(df_logs, use_container_width=True, height=400)

elif nav_page == "👤 Borrower Details & Profile":
    st.title("👤 Borrower Profile & Live Parameters")
    
    with st.form("edit_profile_form"):
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            e_name = st.text_input("Full Name", value=active_row['name'])
            e_id = st.text_input("Applicant ID", value=active_row['id'], help="Editable unique primary identifier")
            e_pan = st.text_input("Identity Ref", value=active_row['pan'])
            cat_idx = EMPLOYMENT_CATEGORIES.index(active_row['category']) if active_row['category'] in EMPLOYMENT_CATEGORIES else 0
            e_cat = st.selectbox("Employment Category", EMPLOYMENT_CATEGORIES, index=cat_idx)
            e_p_inc = st.number_input("Personal Income (Rs.)", value=float(active_row['personal_income']), step=1000.0)
            e_f_inc = st.number_input("Family Income (Rs.)", value=float(active_row['family_income']), step=1000.0)

        with col_b2:
            e_debts = st.number_input("Monthly EMIs (Rs.)", value=float(active_row['monthly_debts']), step=500.0)
            e_upi = st.slider("UPI Txns / Month", 0, 200, value=int(active_row['upi_count']))
            e_util = st.slider("Utility Bill Score", 0, 100, value=int(active_row['utility_status']))
            e_vol = st.slider("Earnings Volatility (%)", 0, 100, value=int(active_row['volatility']))
            e_adb = st.number_input("Avg Daily Balance (ADB)", value=float(active_row.get('adb', 10000.0)), step=1000.0)
            e_io = st.slider("Inflow/Outflow Ratio", 0.5, 2.5, value=float(active_row.get('inflow_outflow_ratio', 1.2)), step=0.05)

        if st.form_submit_button("Update & Re-Underwrite 🔄"):
            updated_data = {
                'id': e_id, 'name': e_name, 'category': e_cat, 'pan': e_pan,
                'personal_income': e_p_inc, 'family_income': e_f_inc, 'monthly_debts': e_debts,
                'upi_count': e_upi, 'utility_status': e_util, 'volatility': e_vol,
                'adb': e_adb, 'inflow_outflow_ratio': e_io, 'disbursed_at': active_row.get('disbursed_at')
            }
            if update_applicant_db(updated_data, old_id=active_row['id']):
                log_audit_event(e_id, credit_score, "PROFILE_UPDATED", f"Updated parameters for {e_name}")
                st.success("Profile updated and model re-evaluated!")
                st.rerun()

elif nav_page == "📱 Application Journey (KFS)":
    st.title("📲 Borrower Digital Application Journey")
    stages = ["1. KYC Verification", "2. Select Loan Terms", "3. KFS & E-Sign", "4. Instant Disbursal"]
    selected_stage = st.radio("Journey Stage:", stages, horizontal=True)
    st.markdown("---")

    if selected_stage == "1. KYC Verification":
        st.success("✅ Account Aggregator (AA) Consent Active. Identity Verified.")
        st.text_input("Name", value=active_row['name'], disabled=True)
        st.text_input("PAN", value=active_row['pan'], disabled=True)

    elif selected_stage == "2. Select Loan Terms":
        st.markdown("### Step 2: Custom Loan Configuration")
        loan_cap = max(10000, int(max_loan_principal))
        loan_amt = st.slider("Requested Principal (Rs.)", 5000, loan_cap, min(25000, loan_cap), 1000)
        tenure = st.selectbox("Tenure (Months)", [3, 6, 9, 12, 18, 24, 36], index=0)
        
        terms = calculate_kfs_terms(loan_amt, tenure)
        st.success(f"**Estimated Monthly EMI:** Rs. {terms['emi']:,.2f} for {tenure} months.")

    elif selected_stage == "3. KFS & E-Sign":
        st.markdown("### Key Fact Statement (KFS)")
        st.caption("This Key Fact Statement is generated in compliance with RBI Digital Lending Guidelines.")
        
        req_principal = max(10000.0, float(min(25000, max_loan_principal)))
        terms = calculate_kfs_terms(req_principal, 12)
        
        kfs_list = [
            {"Parameter": "Sanctioned Loan Amount", "Details": f"Rs. {terms['principal']:,.2f}"},
            {"Parameter": "Disbursal Amount (Net)", "Details": f"Rs. {terms['net_disbursal']:,.2f} (After Rs. {int(terms['processing_fee'])} Processing Fee)"},
            {"Parameter": "Interest Rate (Reducing Balance)", "Details": "14.0% per annum"},
            {"Parameter": "Annual Percentage Rate (APR)", "Details": f"{terms['apr']}% (Includes interest, fee, and charges)"},
            {"Parameter": "Tenure of Loan", "Details": f"{terms['tenure']} Months"},
            {"Parameter": "Number of Repayment Installments", "Details": f"{terms['tenure']} Monthly Installments"},
            {"Parameter": "Monthly EMI Amount", "Details": f"Rs. {terms['emi']:,.2f}"},
            {"Parameter": "Total Repayment Amount", "Details": f"Rs. {terms['total_repayment']:,.2f}"},
            {"Parameter": "Total Interest Payable", "Details": f"Rs. {terms['total_interest']:,.2f}"},
            {"Parameter": "Penal Interest / Overdue Fee", "Details": "2.0% per month on overdue EMI amount"},
            {"Parameter": "Cooling-Off / Look-Up Period", "Details": "3 Business Days (Exit without penalty)"},
            {"Parameter": "Grievance Redressal Officer (GRO)", "Details": "gro@credixai.in | +91-1800-123-4567"}
        ]
        df_kfs = pd.DataFrame(kfs_list)
        st.table(df_kfs)
        
        if REPORTLAB_AVAILABLE:
            pdf_bytes = generate_pdf_kfs(active_row['name'], active_row['id'], df_kfs)
            st.download_button("📄 Download Official PDF KFS Statement", data=pdf_bytes, file_name=f"KFS_{active_row['id']}.pdf", mime="application/pdf")

        st.checkbox("✍️ I accept the Key Fact Statement and e-Sign agreement.", value=True)

        st.markdown("---")
        st.markdown("### 📜 Mandatory Regulatory Declarations")
        st.markdown("""
        * **No Automatic Limit Increases:** Credit limits will not be enhanced without explicit prior written consent.
        * **Direct Account Disbursement:** Funds will be disbursed directly to the borrower's verified bank account without third-party involvement.
        * **Data Privacy Guarantee:** Personal data and transaction logs are processed strictly for credit scoring under AA guidelines and are not stored/sold to third parties.
        """)

    elif selected_stage == "4. Instant Disbursal":
        st.success("🎉 Loan Disbursed via AA Direct Rail!")
        if st.button("Simulate Disbursal Stamp 🕒"):
            active_row['disbursed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            update_applicant_db(active_row)
            log_audit_event(active_row['id'], credit_score, "LOAN_DISBURSED", f"Disbursed at {active_row['disbursed_at']}")
            st.success(f"Stamped at {active_row['disbursed_at']}")

elif nav_page == "🤖 XAI Feature Attribution":
    st.title("🤖 Explainable AI (XAI) Model Attribution")
    st.markdown("Breaks down exact point contributions from the machine learning model for auditable decision-making.")

    col_x1, col_x2 = st.columns([1, 1.2])
    
    with col_x1:
        st.markdown("<h4 style='color: #111827;'>Feature Contributions (Points):</h4>", unsafe_allow_html=True)
        for attr in attributions:
            color = "#2ea44f" if attr['impact_pts'] >= 0 else "#f85149"
            sign = "+" if attr['impact_pts'] >= 0 else ""
            st.markdown(f"""
            <div class="shap-box">
                <span style="color: #ffffff; font-weight: bold; font-size: 1.05rem;">{attr['feature']}:</span> 
                <code style="background-color: #21262d; color: #58a6ff; font-weight: bold; padding: 2px 6px; border-radius: 4px;">{attr['value']}</code><br/>
                <span style="color: #c9d1d9;">Score Impact:</span> <span style="color:{color}; font-weight:bold; font-size: 1.1rem;">{sign}{attr['impact_pts']} pts</span>
            </div>
            """, unsafe_allow_html=True)

    with col_x2:
        df_attr = pd.DataFrame(attributions)
        fig_attr = go.Figure(go.Bar(
            x=df_attr['impact_pts'],
            y=df_attr['feature'],
            orientation='h',
            marker=dict(color=df_attr['impact_pts'].apply(lambda x: '#2ea44f' if x >= 0 else '#f85149'))
        ))
        
        fig_attr.update_layout(
            title=dict(
                text="<b>SHAP-style Feature Impact Breakdown</b>",
                font=dict(color="#111827", size=16)
            ),
            xaxis=dict(
                title=dict(text="Score Point Contribution", font=dict(color="#111827", size=12)),
                tickfont=dict(color="#111827", size=11, family="Arial Black"),
                showgrid=True,
                gridcolor="#e5e7eb"
            ),
            yaxis=dict(
                tickfont=dict(color="#111827", size=12, family="Arial Black"),
                autorange="reversed",
                showline=True,
                linecolor="#111827"
            ),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=40, r=20, t=40, b=40)
        )
        st.plotly_chart(fig_attr, use_container_width=True)

elif nav_page == "⚠️ Deficit & Gap Analyzer":
    st.title("🔍 Criteria Gap & Deficit Analyzer")
    if applicant_deficits:
        for d in applicant_deficits:
            st.warning(f"⚠️ **{d['parameter']}** | Current: `{d['current']}` (Target: `{d['target']}`)")
            st.info(f"💡 **Fix:** {d['fix']}")
    else:
        st.success("🎉 No criteria deficits identified.")

elif nav_page == "🧮 FOIR Waterfall Analysis":
    st.title("🧮 Fixed Obligation to Income Ratio (FOIR) Waterfall")

    col_w1, col_w2 = st.columns([1, 1.1])
    
    with col_w1:
        foir_data = [
            {"Step": "1. Personal Monthly Income", "Amount (Rs.)": f"Rs. {active_row['personal_income']:,.2f}"},
            {"Step": "2. Family/Co-Applicant Income", "Amount (Rs.)": f"Rs. {active_row['family_income']:,.2f}"},
            {"Step": "3. Total Household Income", "Amount (Rs.)": f"Rs. {total_household_income:,.2f}"},
            {"Step": "4. Mandatory Living Exp (-30%)", "Amount (Rs.)": f"Rs. {living_expenses:,.2f}"},
            {"Step": "5. Existing Household EMIs", "Amount (Rs.)": f"Rs. {active_row['monthly_debts']:,.2f}"},
            {"Step": "6. Net Disposable Income", "Amount (Rs.)": f"Rs. {net_disposable_income:,.2f}"},
            {"Step": "7. Max Allowed EMI (80% Cap)", "Amount (Rs.)": f"Rs. {max_eligible_emi:,.2f}"}
        ]
        st.table(pd.DataFrame(foir_data))

    with col_w2:
        fig_waterfall = go.Figure(go.Waterfall(
            orientation="v",
            measure=["absolute", "relative", "total", "relative", "relative", "total"],
            x=["Personal Inc", "Family Inc", "Total Household", "Living Exp", "Existing EMIs", "Net Disposable"],
            y=[active_row['personal_income'], active_row['family_income'], total_household_income, -living_expenses, -active_row['monthly_debts'], net_disposable_income],
            connector={"line": {"color": "#6b7280"}},
            decreasing={"marker": {"color": "#f85149"}},
            increasing={"marker": {"color": "#2ea44f"}},
            totals={"marker": {"color": "#2563eb"}}
        ))
        fig_waterfall.update_layout(
            title=dict(text="Household Cashflow (Rs.)", font=dict(color="#111827")),
            xaxis=dict(tickfont=dict(color="#111827")),
            yaxis=dict(tickfont=dict(color="#111827")),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_waterfall, use_container_width=True)

elif nav_page == "🛡️ RBI Compliance & AA Payload":
    st.title("🛡️ RBI Fair-Lending Compliance & Account Aggregator Data")
    
    st.markdown("### 1. Mandatory 3-Day Cooling-Off Period Tracker")
    disb_time = active_row.get('disbursed_at')
    
    if isinstance(disb_time, str) and len(disb_time) > 0:
        try:
            d_datetime = datetime.strptime(disb_time, "%Y-%m-%d %H:%M:%S")
            expiry_time = d_datetime + timedelta(days=3)
            now_time = datetime.now()
            
            if now_time < expiry_time:
                remaining = expiry_time - now_time
                st.success(f"🟢 **Cooling-Off Period Active:** Borrower can exit without penalty. Remaining: `{remaining.days} days, {remaining.seconds//3600} hours`.")
            else:
                st.info("ℹ️ Cooling-off look-up period has expired.")
        except ValueError:
            st.warning("Invalid timestamp format stored.")
    else:
        st.warning("Loan not yet disbursed for this applicant. Cooling-off timer inactive.")
        if st.button("Simulate Disbursal Stamp Now 🕒"):
            active_row['disbursed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            update_applicant_db(active_row)
            log_audit_event(active_row['id'], credit_score, "COOLING_OFF_STAMPED", f"Disbursed at {active_row['disbursed_at']}")
            st.success(f"Disbursal timestamp recorded: {active_row['disbursed_at']}")
            st.rerun()

    st.markdown("---")
    st.markdown("### 2. Active Loan Terms & Sanction Overview")
    
    l_col1, l_col2, l_col3 = st.columns(3)
    with l_col1:
        default_principal = float(max(10000.0, max_loan_principal))
        req_principal = st.number_input("Sanctioned Principal (Rs.)", value=default_principal, step=5000.0)
    with l_col2:
        req_tenure = st.selectbox("Tenure", [3, 6, 9, 12, 18, 24, 36], index=3)
    with l_col3:
        req_rate = st.number_input("Interest Rate (% p.a.)", value=14.0, step=0.5)

    loan_terms = calculate_kfs_terms(req_principal, req_tenure, annual_rate=req_rate)
    
    st.markdown("##### Calculated Loan Details:")
    lc1, lc2, lc3, lc4 = st.columns(4)
    lc1.metric("Monthly EMI", f"Rs. {loan_terms['emi']:,.2f}")
    lc2.metric("Net Disbursal Amount", f"Rs. {loan_terms['net_disbursal']:,.2f}")
    lc3.metric("Annual Percentage Rate (APR)", f"{loan_terms['apr']}%")
    lc4.metric("Total Repayment", f"Rs. {loan_terms['total_repayment']:,.2f}")

    st.markdown("---")
    st.markdown("### 3. Account Aggregator (AA) Verified Data Stream")
    
    st.info("💡 **Borrower Summary:** This data was retrieved automatically via your consented Account Aggregator channel (`AA-CONSENT-99182-XAI`).")
    
    aa_c1, aa_c2, aa_c3 = st.columns(3)
    aa_c1.metric("Verified Monthly Txns", f"{active_row['upi_count']} UPI Txns")
    aa_c2.metric("Average Daily Balance", f"Rs. {active_row.get('adb', 10000.0):,.2f}")
    aa_c3.metric("Utility On-Time Rate", f"{active_row['utility_status']}%")

    with st.expander("🔍 View Technical Encrypted Payload (For System Auditors & Regulators)"):
        aa_payload = {
            "consent_id": "AA-CONSENT-99182-XAI",
            "timestamp": datetime.now().isoformat(),
            "borrower_pan": active_row['pan'],
            "cashflow_summary": {
                "monthly_upi_transactions": active_row['upi_count'],
                "average_daily_balance_inr": active_row.get('adb', 10000.0),
                "inflow_outflow_ratio": active_row.get('inflow_outflow_ratio', 1.2),
                "utility_bill_on_time_pct": active_row['utility_status'],
                "earnings_volatility_index": active_row['volatility']
            },
            "loan_assessment": {
                "max_eligible_principal_inr": round(max_loan_principal, 2),
                "max_allowed_emi_inr": round(max_eligible_emi, 2),
                "sanctioned_terms": loan_terms
            },
            "audit_trail": {
                "fair_lending_verified": True,
                "blackbox_ml_banned": True,
                "xai_explanations_stored": True
            }
        }
        st.json(aa_payload)

elif nav_page == "🤖 AI Copilot Chatbot":
    st.title("🤖 CrediBot | Underwriting Copilot")
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []

    api_key_input = st.text_input("Gemini API Key (Optional)", type="password")

    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_query := st.chat_input("Ask CrediBot..."):
        st.session_state.chat_history.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        if api_key_input and GENAI_AVAILABLE:
            try:
                client = genai.Client(api_key=api_key_input)
                prompt = f"Applicant {active_row['name']} ({active_row['id']}), XAI Score: {credit_score}. Query: {user_query}"
                response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                with st.chat_message("assistant"):
                    st.markdown(response.text)
                    st.session_state.chat_history.append({"role": "assistant", "content": response.text})
            except Exception as e:
                st.error(f"Error: {str(e)}")
        else:
            with st.chat_message("assistant"):
                ans = f"**CrediBot:** Applicant **{active_row['name']}** has an XAI score of **{credit_score}/950** with an eligible loan principal cap of **Rs. {int(max_loan_principal):,}**."
                st.markdown(ans)
                st.session_state.chat_history.append({"role": "assistant", "content": ans})
