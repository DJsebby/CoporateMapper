import pandas as pd
import numpy as np

# 1. Sample Dataset with OSINT & Web-Scraped Data Points
# Replace this dictionary with pd.read_csv('your_osint_phishing_data.csv')
data = {
    'employee_id': ['EMP101', 'EMP102', 'EMP103', 'EMP104', 'EMP105'],

    # --- OSINT & Web Scraping Data Points ---
    'pwned_breach_count': [4, 0, 8, 1, 0],               # Scraped from HIBP / Dark Web breach dumps
    'cleartext_passwords_leaked': [1, 0, 2, 0, 0],       # Found in combo lists / paste sites (0/1+)
    'github_email_exposure': [1, 0, 1, 0, 0],            # Public commit history exposes work email (0/1)
    'linkedin_role_visibility': [1, 1, 1, 0, 0],         # Clear org chart / tech stack info publicly listed (0/1)
    'executive_impersonation_risk': [1, 0, 0, 0, 0],     # Appears on company "Leadership" team web page (0/1)
    'active_typosquat_domains': [2, 0, 5, 0, 0],         # Lookalike domains registered in WHOIS/DNS (count)
    'domain_in_whois_records': [1, 0, 0, 0, 0],          # Work email listed publicly as technical contact in WHOIS (0/1)

    # --- Internal Behavioral & Technical Data Points ---
    'pcr_last_12m': [0.25, 0.00, 0.50, 0.10, 0.00],        # Phishing Click Rate (0.0 - 1.0)
    'cred_submission_rate': [0.10, 0.00, 0.25, 0.00, 0.00], # Credential Submission Rate (0.0 - 1.0)
    'trr_last_12m': [0.10, 0.80, 0.00, 0.50, 0.90],        # Threat Report Rate (0.0 - 1.0)
    'training_gap_days': [120, 30, 210, 45, 15],           # Days since last training
    'has_phishing_resistant_mfa': [0, 1, 0, 1, 1]          # 1 = Hardware Key/FIDO2, 0 = SMS/OTP/None
}

df = pd.DataFrame(data)

# 2. Advanced Risk Scoring Function
def calculate_osint_phishing_risk(df):
    """
    Calculates Phishing Victim Risk Score (1 to 10) combining:
    - OSINT / Dark Web Exposure (35%)
    - Internal Behavioral History (40%)
    - Technical Security Controls (25%)
    """

    # --- A. OSINT Exposure Metrics (Scaled 0.0 - 1.0) ---
    # Breaches: Scaled, capping high risk at 5+ breaches
    breach_score = np.clip(df['pwned_breach_count'] / 5.0, 0, 1)

    # Cleartext Leak: Direct critical threat multiplier
    cleartext_score = np.clip(df['cleartext_passwords_leaked'], 0, 1)

    # Social Engineering Footprint (LinkedIn, GitHub, WHOIS, Executive Page)
    public_footprint = (
        (df['github_email_exposure'] * 0.3) +
        (df['linkedin_role_visibility'] * 0.2) +
        (df['executive_impersonation_risk'] * 0.3) +
        (df['domain_in_whois_records'] * 0.2)
    )

    # Lookalike Domain Threat: Capped at 3+ active lookalike domains targeting user/org
    typosquat_score = np.clip(df['active_typosquat_domains'] / 3.0, 0, 1)

    # Aggregated OSINT Sub-score (Weight = 35%)
    osint_subscore = (
        (cleartext_score * 0.35) +
        (breach_score * 0.25) +
        (typosquat_score * 0.20) +
        (public_footprint * 0.20)
    )

    # --- B. Behavioral Metrics (Weight = 40%) ---
    click_score = df['pcr_last_12m'].clip(0, 1)
    cred_score = df['cred_submission_rate'].clip(0, 1)
    report_risk_score = 1.0 - df['trr_last_12m'].clip(0, 1)

    behavior_subscore = (
        (cred_score * 0.45) +
        (click_score * 0.35) +
        (report_risk_score * 0.20)
    )

    # --- C. Controls & Recency Metrics (Weight = 25%) ---
    mfa_risk_score = 1.0 - df['has_phishing_resistant_mfa'].astype(float)
    training_risk_score = np.clip((df['training_gap_days'] - 30) / 150, 0, 1)

    controls_subscore = (
        (mfa_risk_score * 0.60) +
        (training_risk_score * 0.40)
    )

    # --- Composite Score Calculation ---
    composite_risk_0_to_1 = (
        (osint_subscore * 0.35) +
        (behavior_subscore * 0.40) +
        (controls_subscore * 0.25)
    )

    # Map to 1 - 10 Scale
    risk_score_1_to_10 = (composite_risk_0_to_1 * 9) + 1

    return np.round(risk_score_1_to_10, 1)

# 3. Process Data and Assign Tiers
df['phishing_risk_score'] = calculate_osint_phishing_risk(df)

# Assign Risk Categories
conditions = [
    (df['phishing_risk_score'] >= 7.5),
    (df['phishing_risk_score'] >= 4.5) & (df['phishing_risk_score'] < 7.5),
    (df['phishing_risk_score'] < 4.5)
]
tier_labels = ['Critical Risk', 'Moderate Risk', 'Low Risk']
df['risk_tier'] = np.select(conditions, tier_labels, default='Unknown')

# 4. Display Results
display_cols = [
    'employee_id',
    'pwned_breach_count',
    'active_typosquat_domains',
    'pcr_last_12m',
    'phishing_risk_score',
    'risk_tier'
]
print(df[display_cols].to_string(index=False))

# Export to CSV
df.to_csv('osint_phishing_risk_scores.csv', index=False)
