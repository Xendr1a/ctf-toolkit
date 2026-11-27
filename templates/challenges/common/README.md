# {{NAME}}

- 分类：{{CATEGORY_TITLE}}（`{{CATEGORY}}`）
- 容器内端口：`{{PORT}}`
- GZCTF 类型：`DynamicContainer`（平台按队伍生成 flag，用 `GZCTF_FLAG` 注入）
- 附件：{{ATTACHMENTS_HUMAN}}

> `toolkit new-challenge` 生成的骨架。先把 `src/` 里的占位逻辑换成真实考点，再按文末清单出题。

## 目录

```
Dockerfile           # 镜像构建；FLAG 不写进任何镜像层
docker-compose.yml   # 本地自测；FLAG 只在这里按运行时环境变量注入
challenge.json       # GZCTF 上传配置（分类/分值/flag 模板/附件/资源限制）
flag.txt.example     # flag 示例；复制成 flag.txt 后填写真 flag（已 gitignore）
src/                 # 题目源码骨架
README.md            # 本文件
```

## 本地起题

```bash
cp flag.txt.example flag.txt
$EDITOR flag.txt
export FLAG="$(cat flag.txt)"
docker compose up -d --build
```

连接方式：

```bash
{{ACCESS_HINT}}
```

停止并清掉卷：

```bash
docker compose down -v
```

想换本机端口时加 `HOST_PORT=12345`（容器内仍是 `{{PORT}}`）：

```bash
HOST_PORT=12345 docker compose up -d
```

FLAG 的读取顺序是 `GZCTF_FLAG` → `FLAG`。`GZCTF_FLAG` 由 GZCTF 动态容器平台注入；
`FLAG` 只用于本地 compose。Dockerfile 里没有 `ENV FLAG` / `ARG FLAG`，flag 也不会写进镜像内文件。

## 自测

```bash
toolkit test-challenge .
```

它会：`compose up -d --build` → 等端口连通 → **无论成败都** `down -v --remove-orphans`。
只验「起得来、端口通」，不解题。首次构建可能较慢，可加 `--timeout 600`。

手动确认镜像层没有 flag：

```bash
docker build -t {{IMAGE}} .
docker history --no-trunc {{IMAGE}} | grep -F 'flag{' || echo '镜像层无 flag'
```

## 上传 GZCTF（人工）

1. 构建并导出镜像：

   ```bash
   docker build -t {{IMAGE}} .
   docker save {{IMAGE}} | gzip > {{NAME}}-image.tar.gz
   ```

2. 后台「题目管理 → 新建题目」，按 `challenge.json` 填表：

   | 表单字段 | challenge.json 键 | 本工程值 |
   |---|---|---|
   | 标题 | `title` | `{{NAME}}` |
   | 分类 | `category` | `{{CATEGORY_TITLE}}` |
   | 类型 | `type` | `DynamicContainer` |
   | 描述/题面 | `content` | 见文件（改成真正题面，不写解法） |
   | Flag 模板 | `flagTemplate` | `flag{[GUID]}`（动态题填这里） |
   | 分值 | `originalScore` | `1000` |
   | 容器镜像 | `containerImage` | `{{IMAGE}}`（上传导出的 tar，或填已推送的镜像名） |
   | 内存限制 | `memoryLimit` | `128` MiB |
   | CPU | `cpuCount` | `1` |
   | 存储 | `storageLimit` | `256` MiB |
   | 暴露端口 | `exposePort` | `{{PORT}}` |
   | 附件 | `attachments` / `fileName` | 见文件 |

   `flag` 只是静态/本地占位值；GZCTF 动态容器用 `flagTemplate`，不要把它当固定 flag 填。

3. 上传附件（若 `attachments` 非空）和镜像 tar，保存后启用；用普通账号实际打一遍。

## 出题清单

- [ ] `src/` 换成真实考点，删掉骨架里的演示逻辑
- [ ] `flag.txt` 写真实 flag，`git status` 确认它没被跟踪
- [ ] `challenge.json` 的题面/分值/端口/内存与实际一致
- [ ] `toolkit test-challenge .` 通过
- [ ] `docker history` 确认镜像层没有 flag
- [ ] 附件能独立解出（如果有附件）
- [ ] 上传 GZCTF 后用普通账号验证连接与提交
- [ ] 检查 README/题面没有泄露解法

## 解题路径（出题人填写，勿发给选手）

（留空）
