# 1. Sử dụng image Python chính thức với Alpine
FROM python:3.12-alpine3.20

# 2. Đặt thư mục làm việc trong container
WORKDIR /app

# 3. Cài đặt các gói hệ thống cần thiết
RUN apk add --no-cache gcc musl-dev libffi-dev

# 4. Sao chép file requirements.txt trước để tận dụng cache
COPY requirements.txt .

# 5. Cài đặt các gói Python cần thiết
RUN pip install --no-cache-dir -r requirements.txt

# 6. Sao chép toàn bộ mã nguồn vào container
COPY . .

# 7. Đặt biến môi trường (tùy chọn)
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

# 8. Mở cổng Flask (mặc định 5002)
EXPOSE 5002

# 9. Lệnh chạy ứng dụng Flask bằng Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:5002", "app:app"]
