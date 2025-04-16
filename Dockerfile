# Dùng image chính thức Python slim
FROM python:3.12-slim

# Đặt thư mục làm việc
WORKDIR /app

# Cài đặt các thư viện hệ thống cần thiết
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Cài torch trước để tránh lỗi
RUN pip install --upgrade pip \
 && pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Copy requirements và cài đặt các thư viện Python còn lại
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=100 -r requirements.txt

# Copy toàn bộ mã nguồn vào container
COPY . .

# Tải model sentence-transformers trước (để cache sẵn vào image)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-mpnet-base-v2')"

# Biến môi trường cho Flask (có thể bỏ nếu dùng Gunicorn)
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

EXPOSE 5002

# Chạy ứng dụng bằng Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:5002", "app:app"]
