# Docker 密钥目录

敏感配置以**文件**形式挂载到容器 `/run/secrets/`（与 TestNewHarness 相同）。本目录除 README 外默认 **不** 进 Git；根目录 **`.env` 纳入 Git**（团队可在其中写非密钥配置或密钥，请用私有远程）。

## 文件清单

| 宿主机文件 | 容器路径 | 写入配置字段 | 说明 |
|-----------|---------|--------------|------|
| `qwen_api_key` | `/run/secrets/qwen_api_key` | `text_model.qwen_api_key` | Qwen / LiteLLM 云 API Key |
| `api_key` | `/run/secrets/api_key` | `security.api_key` | `X-API-Key` 认证（F20） |
| `jwt_secret` | `/run/secrets/jwt_secret` | `security.jwt_secret` | JWT 签名（若启用） |

**优先级**：`/run/secrets/<name>` **>** 仓库根 `.env` **>** `configs/override.yaml` **>** `configs/default.yaml`

## 创建（Linux / macOS）

```bash
mkdir -p secrets
echo -n 'sk-your-qwen-key' > secrets/qwen_api_key
echo -n 'your-api-key' > secrets/api_key
chmod 600 secrets/*
```

## 创建（Windows PowerShell）

```powershell
New-Item -ItemType Directory -Force -Path secrets
Set-Content -Path secrets/qwen_api_key -Value 'sk-your-qwen-key' -NoNewline
Set-Content -Path secrets/api_key -Value 'your-api-key' -NoNewline
```

## 本地开发（无 Docker）

无 `/run/secrets/` 时，在仓库根目录 `.env` 中配置即可（见 `.env.example`）。

修改后重启应用：`docker compose restart app` 或重启 uvicorn。
