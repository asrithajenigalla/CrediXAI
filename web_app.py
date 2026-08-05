import json
import sqlite3
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from io import BytesIO
from xhtml2pdf import pisa

# Optional Gemini AI Integration
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# ==============================================================================
# HELPER: STYLED PDF GENERATOR USING XHTML2PDF
# ==============================================================================
def create_styled_pdf_bytes(html_content: str) -> bytes:
    """Converts HTML and CSS into a styled PDF binary byte stream."""
    result = BytesIO()
    pisa_status = pisa.CreatePDF(BytesIO(html_content.encode("utf-8")), dest=result)
    if pisa_status.err:
        raise Exception("Error rendering HTML to PDF")
    return result.getvalue()

# ==============================================================================
# 1. PAGE CONFIGURATION & HIGH-CONTRAST DARK THEME CSS
# ==============================================================================
st.set_page_config(
    page_title="CrediXAI | End-to-End Lending Engine",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* 1. Fix Disabled Input Text (Verified Full Name & Identity Number) */
    .stTextInput input:disabled, 
    div[data-baseweb="input"] input[disabled] {
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        background-color: #161b22 !important;
        opacity: 1 !important;
        border: 1px solid #484f58 !important;
    }

    /* 2. Fix Executive Summary Card Subtext & Metric Values */
    [data-testid="stMetricValue"], 
    [data-testid="stMetricLabel"],
    [data-testid="stMetricDelta"],
    [data-testid="stMarkdownContainer"] small,
    [data-testid="stMarkdownContainer"] caption,
    div[data-testid="stMetric"] * {
        color: #ffffff !important;
        opacity: 1 !important;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. LOCAL SQLITE DATABASE INITIALIZATION
# ==============================================================================
def init_db():
    conn = sqlite3.connect("credixai_demo.db")
    c = conn.cursor()
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
            volatility INTEGER
        )
    ''')
    
    c.execute("SELECT COUNT(*) FROM applicants")
    if c.fetchone()[0] == 0:
        sample_data = [
            ("APP-8112-IN", "Priya Sundaram", "🛒 Micro Merchant / Street Vendor", "XYZPS9876K", 48000.0, 15000.0, 4500.0, 142, 100, 10),
            ("APP-9204-IN", "Rahul Sharma", "Gig Economy Worker", "ABCDE1234F", 35000.0, 20000.0, 6000.0, 110, 78, 22),
            ("APP-3341-IN", "Anil Kumar", "Freelancer", "PQRST5543M", 28000.0, 0.0, 4500.0, 45, 65, 38)
        ]
        c.executemany("INSERT INTO applicants VALUES (?,?,?,?,?,?,?,?,?,?)", sample_data)
        conn.commit()
    conn.close()

init_db()

def get_all_applicants():
    conn = sqlite3.connect("credixai_demo.db")
    df = pd.read_sql_query("SELECT * FROM applicants", conn)
    conn.close()
    return df

def update_applicant_db(app_data):
    conn = sqlite3.connect("credixai_demo.db")
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO applicants VALUES (?,?,?,?,?,?,?,?,?,?)
    ''', (
        app_data['id'], app_data['name'], app_data['category'], app_data['pan'],
        app_data['personal_income'], app_data['family_income'], app_data['monthly_debts'],
        app_data['upi_count'], app_data['utility_status'], app_data['volatility']
    ))
    conn.commit()
    conn.close()

# ==============================================================================
# 3. SIDEBAR NAVIGATION & DEMO APPLICANT SELECTOR / REGISTER FORM
# ==============================================================================
st.sidebar.title("⚙️ CrediXAI Engine")

st.sidebar.markdown("### 🗄️ Demo Database Switcher")
df_apps = get_all_applicants()

# Toggle between selecting an existing applicant or creating a new memory space
user_action = st.sidebar.radio("Database Mode:", ["Select Existing Profile", "➕ Register New Applicant"])

if user_action == "➕ Register New Applicant":
    st.sidebar.markdown("---")
    st.sidebar.subheader("New Applicant Entry")
    with st.sidebar.form("new_applicant_registration_form"):
        new_name = st.text_input("Full Name")
        new_id = f"APP-{np.random.randint(1000, 9999)}-IN"
        new_pan = st.text_input("PAN / ID Ref")
        cat_options = ["🛒 Micro Merchant / Street Vendor", "Gig Economy Worker", "Salaried", "Self-Employed", "Freelancer"]
        new_cat = st.selectbox("Category", cat_options)
        new_p_inc = st.number_input("Monthly Income (Rs.)", value=25000.0, step=1000.0)
        new_f_inc = st.number_input("Family Income (Rs.)", value=0.0, step=1000.0)
        new_debts = st.number_input("Monthly EMIs (Rs.)", value=2000.0, step=500.0)
        new_upi = st.slider("Monthly UPI Txns", 0, 200, value=50)
        new_util = st.slider("Utility Score", 0, 100, value=80)
        new_vol = st.slider("Volatility Index (%)", 0, 100, value=15)

        if st.form_submit_button("Save Applicant to Database 💾"):
            if new_name and new_pan:
                new_user_data = {
                    'id': new_id, 'name': new_name, 'category': new_cat, 'pan': new_pan,
                    'personal_income': new_p_inc, 'family_income': new_f_inc, 'monthly_debts': new_debts,
                    'upi_count': new_upi, 'utility_status': new_util, 'volatility': new_vol
                }
                update_applicant_db(new_user_data)
                st.sidebar.success(f"Applicant {new_name} created!")
                st.rerun()
            else:
                st.sidebar.error("Full Name and PAN are required.")

    selected_app_id = df_apps['id'].iloc[0]
else:
    selected_app_id = st.sidebar.selectbox("Select Active Applicant", df_apps['id'].tolist(), index=0)

active_row = df_apps[df_apps['id'] == selected_app_id].iloc[0].to_dict()

st.sidebar.markdown("---")
st.sidebar.markdown("### 📍 Navigation Menu")
nav_page = st.sidebar.radio(
    "Go to Page:",
    [
        "📊 Executive Summary",
        "👤 Borrower Details & Profile",
        "📱 Application Journey",
        "⚠️ Deficit & Gap Analyzer",
        "🧮 FOIR Waterfall Analysis",
        "📊 Active Loans & Repayments",
        "🤖 AI Copilot Chatbot"
    ]
)

# ==============================================================================
# 4. UNDERWRITING CALCULATIONS
# ==============================================================================
total_household_income = active_row['personal_income'] + active_row['family_income']
living_expenses = total_household_income * 0.30
income_after_expenses = total_household_income - living_expenses
net_disposable_income = max(0, income_after_expenses - active_row['monthly_debts'])
max_eligible_emi = net_disposable_income * 0.80

monthly_r = 14.0 / (12 * 100)
if max_eligible_emi > 0:
    max_loan_principal = (max_eligible_emi * (((1 + monthly_r)**12) - 1)) / (monthly_r * ((1 + monthly_r)**12))
else:
    max_loan_principal = 0

def calculate_score_and_deficits(b_data):
    base = 600
    deficits = []
    
    tot_inc = b_data['personal_income'] + b_data['family_income']
    dti_val = (b_data['monthly_debts'] / tot_inc) if tot_inc > 0 else 1.0
    
    if dti_val > 0.4:
        deficits.append({
            "parameter": "High Existing Debt-to-Income (DTI)",
            "current": f"{round(dti_val * 100, 1)}%",
            "target": "< 30%",
            "fix": "Pay off smaller existing loans or declare secondary family co-applicant income."
        })
    if b_data['upi_count'] < 60:
        deficits.append({
            "parameter": "Low UPI Cashflow Velocity",
            "current": f"{b_data['upi_count']} txns/mo",
            "target": "> 80 txns/mo",
            "fix": "Route regular daily digital transactions through primary UPI handle to increase velocity."
        })
    if b_data['utility_status'] < 80:
        deficits.append({
            "parameter": "Utility Payment Discipline",
            "current": f"{b_data['utility_status']}/100",
            "target": "≥ 85/100",
            "fix": "Ensure prompt payment of utility bills to claim +40 score points."
        })
    if b_data['volatility'] > 25:
        deficits.append({
            "parameter": "High Earnings Volatility",
            "current": f"{b_data['volatility']}%",
            "target": "< 20%",
            "fix": "Link verified bank statements covering 6 continuous months to prove consistent income."
        })

    score = int(np.clip(base + (40 if b_data['utility_status']>=80 else -40) + (30 if b_data['upi_count']>=60 else -30), 300, 900))
    return score, deficits

credit_score, applicant_deficits = calculate_score_and_deficits(active_row)

# ==============================================================================
# 5. PAGE CONTENT ROUTING
# ==============================================================================

# ------------------------------------------------------------------------------
# PAGE 1: EXECUTIVE SUMMARY
# ------------------------------------------------------------------------------
if nav_page == "📊 Executive Summary":
    st.title("💳 CrediXAI | Underwriting Executive Summary")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f'<div class="metric-card"><div class="metric-title">Applicant</div><div class="metric-value">{active_row["name"]}</div><small style="color:#8b949e !important;">ID: {active_row["id"]}</small></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="metric-card"><div class="metric-title">Household Income</div><div class="metric-value">Rs. {int(total_household_income):,}</div><small style="color:#8b949e !important;">Personal: Rs. {int(active_row["personal_income"]):,}</small></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="metric-card"><div class="metric-title">CrediXAI Score</div><div class="metric-value">{credit_score} <small style="font-size:0.8rem; color:#8b949e !important;">/ 900</small></div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div class="metric-card"><div class="metric-title">Max Eligible Loan</div><div class="metric-value" style="color:#3fb950 !important;">Rs. {int(max_loan_principal):,}</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 📈 Live Performance Metrics Overview")
    st.info("Use the sidebar menu to navigate to specific modules like the Deficit & Gap Analyzer, FOIR Waterfall, or Active Loans.")

# ------------------------------------------------------------------------------
# PAGE 2: BORROWER DETAILS & PROFILE
# ------------------------------------------------------------------------------
elif nav_page == "👤 Borrower Details & Profile":
    st.title("👤 Borrower Profile & Live Settings")
    st.markdown("Edit or inspect full profile attributes for the current applicant. Changes update the database in real time.")

    with st.form("edit_borrower_form"):
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            e_name = st.text_input("Applicant Full Name", value=active_row['name'])
            e_id = st.text_input("Applicant ID", value=active_row['id'])
            e_pan = st.text_input("Identity / Document Ref", value=active_row['pan'])
            
            cat_options = ["🛒 Micro Merchant / Street Vendor", "Gig Economy Worker", "Salaried", "Self-Employed", "Freelancer"]
            cat_idx = cat_options.index(active_row['category']) if active_row['category'] in cat_options else 0
            e_cat = st.selectbox("Employment Category", cat_options, index=cat_idx)
            
            e_p_inc = st.number_input("Personal Monthly Income (Rs.)", value=float(active_row['personal_income']), step=1000.0)

        with col_b2:
            e_f_inc = st.number_input("Family / Co-Applicant Income (Rs.)", value=float(active_row['family_income']), step=1000.0)
            e_debts = st.number_input("Existing Monthly EMIs (Rs.)", value=float(active_row['monthly_debts']), step=500.0)
            e_upi = st.slider("Monthly UPI Transaction Count", 0, 200, value=int(active_row['upi_count']))
            e_util = st.slider("Utility Bill Payment Score", 0, 100, value=int(active_row['utility_status']))
            e_vol = st.slider("Earnings Volatility Index (%)", 0, 100, value=int(active_row['volatility']))

        submit_btn = st.form_submit_button("Save & Update Applicant Profile 💾")
        if submit_btn:
            updated_data = {
                'id': e_id, 'name': e_name, 'category': e_cat, 'pan': e_pan,
                'personal_income': e_p_inc, 'family_income': e_f_inc, 'monthly_debts': e_debts,
                'upi_count': e_upi, 'utility_status': e_util, 'volatility': e_vol
            }
            update_applicant_db(updated_data)
            st.success(f"Profile updated successfully for {e_name} in live database!")
            st.rerun()

# ------------------------------------------------------------------------------
# PAGE 3: APPLICATION JOURNEY
# ------------------------------------------------------------------------------
elif nav_page == "📱 Application Journey":
    st.title("📲 Borrower Digital Application Journey")
    stages = ["1. KYC Verification", "2. Select Loan Terms", "3. KFS & E-Sign", "4. Instant Disbursal"]
    selected_stage = st.radio("Journey Stage:", stages, horizontal=True)

    st.markdown("---")
    if selected_stage == "1. KYC Verification":
        st.markdown("### Step 1: Digital Identity Verification")
        st.text_input("Verified Full Name", value=str(active_row['name']), disabled=True)
        st.text_input("Identity Number / Document Ref", value=str(active_row['pan']), disabled=True)
        st.checkbox("Account Aggregator (AA) Consent Verified & Active", value=True, disabled=True)

    elif selected_stage == "2. Select Loan Terms":
        st.markdown("### Step 2: Custom Loan Configuration")
        if max_loan_principal > 5000:
            loan_amt = st.slider("Requested Principal (Rs.)", 5000, int(max_loan_principal), int(min(25000, max_loan_principal)), 1000)
            tenure = st.selectbox("Tenure (Months)", [3, 6, 9, 12])
            calc_emi = (loan_amt * monthly_r * ((1 + monthly_r)**tenure)) / (((1 + monthly_r)**tenure) - 1)
            st.success(f"Estimated Monthly EMI: **Rs. {calc_emi:,.2f}** for {tenure} months.")
        else:
            st.warning("Credit capacity is insufficient for new loans.")

    elif selected_stage == "3. KFS & E-Sign":
        st.markdown("### Step 3: Key Fact Statement (KFS) & RBI Regulatory Norms")
        st.markdown("This Key Fact Statement is generated in compliance with **RBI Digital Lending Guidelines (2022/2026)**.")
        
        kfs_data = [
            {"Parameter": "Sanctioned Loan Amount", "Details": "Rs. 25,000.00"},
            {"Parameter": "Disbursal Amount (Net)", "Details": "Rs. 24,500.00 (After Rs. 500 Processing Fee)"},
            {"Parameter": "Interest Rate (Reducing Balance)", "Details": "14.0% per annum"},
            {"Parameter": "Annual Percentage Rate (APR)", "Details": "15.8% (Includes interest, fee, and charges)"},
            {"Parameter": "Tenure of Loan", "Details": "12 Months"},
            {"Parameter": "Number of Repayment Installments", "Details": "12 Monthly Installments"},
            {"Parameter": "Monthly EMI Amount", "Details": "Rs. 2,244.60"},
            {"Parameter": "Total Repayment Amount", "Details": "Rs. 26,935.20"},
            {"Parameter": "Total Interest Payable", "Details": "Rs. 1,935.20"},
            {"Parameter": "Penal Interest / Overdue Fee", "Details": "2.0% per month on overdue EMI amount"},
            {"Parameter": "Cooling-Off / Look-Up Period", "Details": "3 Business Days (Exit without penalty)"},
            {"Parameter": "Grievance Redressal Officer (GRO)", "Details": "gro@credixai.in | +91-1800-123-4567"}
        ]
        st.table(pd.DataFrame(kfs_data))

        st.markdown("#### 📜 Mandatory Regulatory Declarations")
        st.markdown("""
        * **No Automatic Limit Increases:** Credit limits will not be enhanced without explicit prior written consent.
        * **Direct Account Disbursement:** Funds will be disbursed directly to the borrower's verified bank account without third-party involvement.
        * **Data Privacy Guarantee:** Personal data and transaction logs are processed strictly for credit assessment under AA guidelines and are not stored/sold to third parties.
        """)

        st.markdown("---")
        esign_agreed = st.checkbox("✍️ I have read, understood, and digitally sign the Key Fact Statement (KFS) and e-Mandate agreement.", value=True)
        if esign_agreed:
            st.success("✅ E-Signature Captured. Token ID: `ESG-99201-XAI`")

    elif selected_stage == "4. Instant Disbursal":
        st.success("🎉 Disbursement Complete! Loan credited to registered bank account.")

# ------------------------------------------------------------------------------
# PAGE 4: DEFICIT & GAP ANALYZER
# ------------------------------------------------------------------------------
elif nav_page == "⚠️ Deficit & Gap Analyzer":
    st.title("🔍 Deficit & Criteria Gap Analyzer")
    st.markdown("Identifies exact criteria holding the applicant back and provides specific solutions to fix them.")

    if applicant_deficits:
        st.markdown(f'<div class="deficit-box"><h4>⚠️ Found {len(applicant_deficits)} Areas Needing Attention</h4>Below is the exact breakdown of parameters where the applicant missed the optimal benchmark.</div>', unsafe_allow_html=True)

        for d in applicant_deficits:
            st.markdown(f"❌ **{d['parameter']}** *(Current: {d['current']} | Target: {d['target']})*")
            st.markdown(f"""
            <div class="recommendation-box">
                💡 <b>Strategic Recommendation to Maximize Limit:</b><br/>
                {d['fix']}
            </div>
            """, unsafe_allow_html=True)
            st.markdown("<br/>", unsafe_allow_html=True)
    else:
        st.success("🎉 Excellent! No criteria gaps detected for this profile.")

# ------------------------------------------------------------------------------
# PAGE 5: FOIR WATERFALL ANALYSIS
# ------------------------------------------------------------------------------
elif nav_page == "🧮 FOIR Waterfall Analysis":
    st.title("🧮 Fixed Obligation to Income Ratio (FOIR) Waterfall")
    
    col_w1, col_w2 = st.columns(2)
    with col_w1:
        waterfall_df = [
            {"Step": "1. Personal Monthly Income", "Amount (Rs.)": f"Rs. {active_row['personal_income']:,.2f}"},
            {"Step": "2. Family/Co-Applicant Income", "Amount (Rs.)": f"+ Rs. {active_row['family_income']:,.2f}"},
            {"Step": "3. Total Household Income", "Amount (Rs.)": f"Rs. {total_household_income:,.2f}"},
            {"Step": "4. Mandatory Living Exp (-30%)", "Amount (Rs.)": f"- Rs. {living_expenses:,.2f}"},
            {"Step": "5. Existing Household EMIs", "Amount (Rs.)": f"- Rs. {active_row['monthly_debts']:,.2f}"},
            {"Step": "6. Net Disposable Income", "Amount (Rs.)": f"Rs. {net_disposable_income:,.2f}"},
            {"Step": "7. Max Allowed EMI (80% Cap)", "Amount (Rs.)": f"Rs. {max_eligible_emi:,.2f}"}
        ]
        st.table(pd.DataFrame(waterfall_df))

    with col_w2:
        fig_waterfall = go.Figure(go.Waterfall(
            orientation="v",
            measure=["absolute", "relative", "total", "relative", "relative", "total"],
            x=["Personal Inc", "Family Inc", "Total Household", "Living Exp", "Existing EMIs", "Net Disposable"],
            y=[active_row['personal_income'], active_row['family_income'], total_household_income, -living_expenses, -active_row['monthly_debts'], net_disposable_income],
            connector={"line": {"color": "#8b949e"}},
            decreasing={"marker": {"color": "#f85149"}},
            increasing={"marker": {"color": "#2ea44f"}},
            totals={"marker": {"color": "#388bfd"}}
        ))
        fig_waterfall.update_layout(title="Household Cashflow (Rs.)", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#ffffff'))
        st.plotly_chart(fig_waterfall, use_container_width=True)

# ------------------------------------------------------------------------------
# PAGE 6: ACTIVE LOANS & REPAYMENTS (ENCODING FIXES APPLIED)
# ------------------------------------------------------------------------------
elif nav_page == "📊 Active Loans & Repayments":
    st.title("📊 Active Loan Management & Repayments")
    st.markdown("Track active loans, upcoming EMI schedules, and direct one-click payments.")

    loans_data = [
        {"Loan ID": "LN-2025-88", "Lender": "FinServe Digital", "Sanctioned": "Rs. 30,000", "Outstanding": "Rs. 12,400", "Next EMI Due": "05 Aug 2026", "EMI Amount": "Rs. 2,650", "Status": "Active"},
        {"Loan ID": "LN-2024-12", "Lender": "FlexiCredit", "Sanctioned": "Rs. 15,000", "Outstanding": "Rs. 0", "Next EMI Due": "N/A", "EMI Amount": "Rs. 0", "Status": "Closed"}
    ]
    st.table(pd.DataFrame(loans_data))

    st.markdown("---")
    col_p1, col_p2 = st.columns(2)

    with col_p1:
        st.markdown("### Pay Upcoming EMI")
        pay_amt = st.number_input("Payment Amount (Rs.)", value=2650)
        pay_method = st.selectbox("Payment Method", ["UPI (Google Pay / PhonePe)", "Net Banking", "Debit Card"])
        if st.button("Pay EMI Now 💳"):
            st.success(f"✅ Payment of Rs. {pay_amt} successful via {pay_method}!")

    with col_p2:
        st.markdown("### Download Documents")
        
        # HTML Template with UTF-8 Meta Tag & Standard Rupee Notation
        assessment_report_html = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 30px; color: #111; }}
                .header {{ text-align: center; border-bottom: 2px solid #2ea44f; padding-bottom: 10px; }}
                .section {{ margin-top: 20px; background: #f8f9fa; padding: 15px; border-radius: 8px; }}
                .metric {{ font-size: 20px; font-weight: bold; color: #0d4429; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #2ea44f; color: white; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>CREDIXAI UNDERWRITING ASSESSMENT REPORT</h2>
                <p>Official Institutional Record • Generated on 2026-08-04 22:30:00 IST</p>
            </div>
            <div class="section">
                <h3>Applicant Details</h3>
                <p><b>Name:</b> {active_row['name']} | <b>ID:</b> {active_row['id']} | <b>Category:</b> {active_row['category']}</p>
                <p><b>AA Consent Verification:</b> VERIFIED ACTIVE</p>
            </div>
            <div class="section">
                <h3>Underwriting Decision</h3>
                <p class="metric">Credit Score: {credit_score}/900</p>
                <p><b>Recommendation:</b> Approved for Instant Credit Line up to Rs. {int(max_loan_principal):,} at 14% APR</p>
            </div>
            <div class="section">
                <h3>Financial Signals Overview</h3>
                <table>
                    <tr><th>Financial Attribute</th><th>Evaluated Value</th></tr>
                    <tr><td>Monthly Income</td><td>Rs. {int(active_row['personal_income']):,}</td></tr>
                    <tr><td>UPI Transactions</td><td>{active_row['upi_count']} / month</td></tr>
                    <tr><td>Utility Status</td><td>{active_row['utility_status']}% On-Time</td></tr>
                    <tr><td>Average Balance</td><td>Rs. {int(net_disposable_income):,}</td></tr>
                    <tr><td>Debt Obligations</td><td>Rs. {int(active_row['monthly_debts']):,}</td></tr>
                </table>
            </div>
        </body>
        </html>
        """
        
        pdf_bytes = create_styled_pdf_bytes(assessment_report_html)
        
        st.download_button(
            label="📄 Download Assessment Report (PDF)",
            data=pdf_bytes,
            file_name=f"CrediXAI_Assessment_{active_row['id']}.pdf",
            mime="application/pdf"
        )

# ------------------------------------------------------------------------------
# PAGE 7: AI COPILOT CHATBOT
# ------------------------------------------------------------------------------
elif nav_page == "🤖 AI Copilot Chatbot":
    st.title("🤖 CrediBot | Underwriting Copilot")
    st.markdown("Ask CrediBot policy, eligibility, or risk management queries.")

    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []

    api_key_input = st.text_input("Gemini API Key (Optional)", type="password")

    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_query := st.chat_input("Ask CrediBot a question..."):
        st.session_state.chat_history.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        if api_key_input and GENAI_AVAILABLE:
            try:
                client = genai.Client(api_key=api_key_input)
                prompt = f"Applicant {active_row['name']} ({active_row['id']}), Score: {credit_score}. User question: {user_query}"
                response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                with st.chat_message("assistant"):
                    st.markdown(response.text)
                    st.session_state.chat_history.append({"role": "assistant", "content": response.text})
            except Exception as e:
                st.error(f"Error: {str(e)}")
        else:
            with st.chat_message("assistant"):
                ans = f"**CrediBot:** Applicant **{active_row['name']}** currently has a credit score of **{credit_score}/900** with an eligible loan principal cap of **Rs. {int(max_loan_principal):,}**."
                st.markdown(ans)
                st.session_state.chat_history.append({"role": "assistant", "content": ans})
