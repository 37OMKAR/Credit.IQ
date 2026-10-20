# ==============================================================================
# Credit.IQ - Production Dockerfile
# Bank-Grade Financial Document Extraction & Credit Appraisal Engine
# ==============================================================================

FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies for compiled wheels (Pillow, PyMuPDF, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ocr.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt -r requirements-ocr.txt

# Final runtime image
FROM python:3.12-slim AS runner

WORKDIR /app

# Install runtime system libraries (Tesseract OCR for scanned docs, libgl for opencv)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create secure non-root user
RUN useradd -m -u 1001 -s /bin/bash appuser

# Copy installed Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy application source code
COPY --chown=appuser:appuser . /app

# Create necessary persistent directories with appropriate permissions
RUN mkdir -p /app/cases /app/reports /app/data && \
    chown -R appuser:appuser /app/cases /app/reports /app/data

USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=true", \
     "--browser.gatherUsageStats=false", \
     "--server.maxUploadSize=50"]
