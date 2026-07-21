FROM registry.access.redhat.com/ubi9/python-312:1

USER 0
WORKDIR /opt/app

COPY app/requirements.txt /opt/app/requirements.txt
RUN pip install --no-cache-dir -r /opt/app/requirements.txt

COPY app/ /opt/app/

ENV HOME=/opt/app \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

USER 1001

CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]
