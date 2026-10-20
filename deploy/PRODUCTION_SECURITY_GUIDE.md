# Credit.IQ - Production Deployment & Bank-Grade Security Guide

---

## 1. The Brutal Truth: Netlify vs. Hostinger vs. Dedicated VPS

### ❌ Netlify: 100% Incompatible
- **Why**: Netlify is a static CDN hosting platform for JAMstack frontend sites (React/HTML/Vue) with short-lived serverless functions (10–26 second timeout).
- **The Technical Blocker**: Credit.IQ is built on **Python Streamlit**, PyMuPDF (C-bindings), Tesseract OCR, openpyxl, python-docx, and long-running PDF parsing threads. Netlify has **no persistent Python runtime** and cannot run background daemons or WebSocket servers. Any attempt to deploy this directly to Netlify is technically impossible.

### ❌ Hostinger Shared Web Hosting (cPanel / hPanel): Incompatible
- **Why**: Shared hosting accounts only run Apache/LiteSpeed with PHP and MySQL. You do not have root access, cannot open custom ports (8501), cannot install system libraries (`libgl1`, `tesseract-ocr`), and persistent Python background daemons are terminated by process-killers.

### ✅ Hostinger KVM VPS (Ubuntu 22.04 or 24.04): Fully Compatible & Recommended
- **Why**: A Hostinger KVM VPS (e.g., VPS 2 or VPS 4) is a dedicated virtual Linux machine. You get full root access, dedicated RAM, CPU cores, and can run Docker, Nginx, Let's Encrypt SSL, and custom firewalls.
- **Cost**: ~$6 to $12/month.
- **Performance**: 2 to 4 vCPUs + 4GB to 8GB RAM can easily process 50-page annual reports and serve multiple concurrent bank loan officers.

---

## 2. API Key Security & Bank Compliance (RBI Regulations)

### Where do API keys live?
- All API keys (`GROQ_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`) reside exclusively in the server-side `.env` file.
- **Streamlit runs 100% on the server**. The client browser only receives HTML/CSS/DOM updates over a secure WebSocket. **API keys are NEVER sent to the client browser**.
- Server permissions must be locked down:
  ```bash
  chmod 600 .env
  chown appuser:appuser .env
  ```

### ⚠️ The Critical Regulatory Warning for Indian Banks (RBI Compliance)
If a bank or NBFC runs this system for live borrower appraisal:
1. **RBI Data Localization & Outsourcing Guidelines**:
   - Transmitting unredacted corporate financial statements, promoter PANs, DINs, and banking limits to multi-tenant foreign LLM endpoints (e.g., Groq US, OpenAI US, Anthropic US) without an enterprise Data Processing Agreement (DPA) violates RBI cybersecurity directives.
2. **The 3 Institutional Tiers of Credit.IQ**:
   - **Tier 1: 100% Air-Gapped / Offline Local Pipeline (Zero Data Leakage)**:
     - Credit.IQ's core extraction engine, tabular parser, ratio formulas, Beneish M-score, Piotroski F-score, Altman Z'', and **ICAI UDIN verification** run **entirely locally with ZERO external API calls**. It works even with no internet connection.
   - **Tier 2: Sovereign Indian Cloud AI (RBI Compliant)**:
     - If AI narrative drafting is required, route the LLM calls to **Azure OpenAI in Central India (Pune)** or **AWS Bedrock in Mumbai (ap-south-1)**, where data never leaves Indian jurisdiction.
   - **Tier 3: On-Premises Local LLM**:
     - Host an internal instance of **Ollama** or **vLLM** (`llama-3.3-70b-instruct` or `qwen2.5-32b`) inside the bank's internal network or dedicated GPU VPS.

---

## 3. Step-by-Step Production Deployment on Hostinger VPS

### Step 1: Provision your Hostinger KVM VPS
1. Select **Ubuntu 22.04 LTS** or **Ubuntu 24.04 LTS**.
2. Connect via SSH:
   ```bash
   ssh root@your_vps_ip
   ```

### Step 2: Install Docker & Docker Compose
```bash
# Update packages
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Verify Docker installation
docker --version
docker compose version
```

### Step 3: Clone Code & Configure Environment
```bash
# Clone repository
cd /var/www
git clone https://github.com/your-repo/credit.iq.git
cd credit.iq

# Create production .env file
cp .env.example .env
nano .env

# Lock down .env file permissions
chmod 600 .env
```

### Step 4: Obtain Let's Encrypt SSL Certificate
```bash
# Install Certbot
apt install certbot -y

# Stop any running webserver on port 80
systemctl stop nginx 2>/dev/null || true

# Obtain SSL Certificate (Replace credit.yourdomain.com with your actual domain)
certbot certonly --standalone -d credit.yourdomain.com --preferred-challenges http

# Copy or symlink certificates into deploy/ssl/
mkdir -p deploy/ssl
cp /etc/letsencrypt/live/credit.yourdomain.com/fullchain.pem deploy/ssl/
cp /etc/letsencrypt/live/credit.yourdomain.com/privkey.pem deploy/ssl/
```

### Step 5: Launch with Docker Compose
```bash
cd deploy
docker compose up -d --build

# Check running status
docker compose ps
docker compose logs -f
```

---

## 4. ICAI UDIN Audit Verification Check

### Why UDIN is Mandatory for Banks:
- Per ICAI Council decision, UDIN is **mandatory from 1 July 2019** for all audit and assurance reports.
- Any balance sheet for FY 2019-20, FY 2020-21, FY 2021-22, FY 2022-23, FY 2023-24, or FY 2024-25 that lacks a valid 18-digit UDIN is legally **unauthenticated** and may be an unfiled draft or fraudulent statement.

### What Credit.IQ Validates Automatically:
1. **18-Character Syntax**: `YY` (Year) + `MMMMMM` (6-digit CA Membership) + `XXXXXXXXXX` (10-char ICAI hash).
2. **CA Membership Matching**: Cross-checks the 6 digits in the UDIN against the signing CA partner's Membership Number extracted from the balance sheet signature block.
3. **Year Plausibility**: Compares the generation year in the UDIN against the financial year and signing date.
4. **Official ICAI Verification**:
   - URL: **https://udin.icai.org/search-udin**
   - Credit officers can click the direct link provided in the memorandum and UI to verify the certificate on the ICAI portal.
