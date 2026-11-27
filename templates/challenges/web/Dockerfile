FROM python:3.12-slim
WORKDIR /app
COPY src/ /app/
RUN useradd --system --uid 10001 ctf
USER ctf
EXPOSE {{PORT}}
# FLAG 由 compose/GZCTF 在运行时注入环境变量，不打进镜像层。
CMD ["python3", "/app/app.py"]
