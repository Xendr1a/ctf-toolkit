FROM alpine:3.20 AS build
RUN apk add --no-cache gcc musl-dev
WORKDIR /build
COPY src/chall.c .
RUN gcc -O2 -Wall -Wextra -s -o chall chall.c

FROM python:3.12-slim
WORKDIR /app
COPY --from=build /build/chall /app/chall
COPY src/server.py /app/server.py
RUN useradd --system --uid 10001 ctf && chown -R ctf /app
USER ctf
EXPOSE {{PORT}}
# FLAG 由 compose/GZCTF 在运行时注入环境变量；二进制里只有口令，没有 flag。
CMD ["python3", "/app/server.py"]
