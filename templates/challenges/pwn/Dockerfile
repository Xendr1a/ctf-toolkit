FROM alpine:3.20 AS build
RUN apk add --no-cache gcc musl-dev
WORKDIR /build
COPY src/chall.c .
RUN gcc -O2 -Wall -Wextra -o chall chall.c

FROM alpine:3.20
RUN apk add --no-cache socat
WORKDIR /app
COPY --from=build /build/chall /app/chall
EXPOSE {{PORT}}
# FLAG 由 compose/GZCTF 在运行时注入环境变量；这里不写 ENV/ARG，镜像层里没有 flag。
CMD ["socat", "TCP-LISTEN:{{PORT}},reuseaddr,fork", "EXEC:/app/chall,stderr"]
