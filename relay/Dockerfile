FROM python:3.13-slim
RUN pip install --no-cache-dir "websockets>=14,<18"
COPY relay.py /relay.py
USER nobody
EXPOSE 8105
CMD ["python3", "-u", "/relay.py", "--port", "8105"]
