# newoa

OA待阅自动处理工具

## 功能

- 自动登录 SSO 系统
- 自动处理 OA 待阅任务
  - 手动已阅（isremark=20）
  - 自动已阅（isremark=60）
- ETEAMSID 本地缓存，避免重复登录

## 环境

- Python 3.8+
- Windows/Linux/macOS

## 安装

```bash
pip install -r requirements.txt
```

如果需要通过代理安装（如使用 Clash、V2Ray 等）：

```bash
pip install -r requirements.txt --proxy http://127.0.0.1:7890
```

或指定代理端口：

```bash
pip install ddddocr --proxy http://127.0.0.1:你的代理端口
```

## 配置

首次运行时会提示输入用户名和密码，配置会自动保存到 `config.json`。

也可以手动编辑 `config.json`：

```json
{
    "username": "你的用户名",
    "password": "你的密码"
}
```

## 运行

```bash
python main.py
```

## 流程说明

1. 检查本地缓存的 ETEAMSID 是否有效
2. 无效则使用账号密码登录 SSO（自动识别验证码）
3. 获取 ETEAMSID 并缓存到本地
4. 获取待阅列表并自动处理

### 流程图

```mermaid
flowchart TD
    A[启动程序] --> B{检查 ETEAMSID 缓存}

    B -->|有效| C1[使用缓存的 ETEAMSID]
    C1 --> C2[POST /api/workflow/list/data/getPortalListData<br/>验证 ETEAMSID 是否有效]
    C2 -->|有效| L[获取待阅列表]
    C2 -->|无效| B

    B -->|无效| D{config.json 有账号密码?}
    D -->|有| E[读取账号密码]
    D -->|无| F[交互式输入账号密码]
    F --> G[保存到 config.json]
    G --> E

    E --> H[GET /sso/login<br/>获取 csrf_token, RSA公钥, return_url, client_id]

    H --> I[GET /validatecode/image<br/>获取验证码图片]
    I --> J[OCR 识别验证码]
    J -->|失败| I
    J -->|成功| K[POST /sso/login<br/>提交: csrf_token, username, password, validateCode]

    K -->|返回 cookies<br/>含 auth_token| L1[从 cookies 获取 auth_token]
    L1 --> M[GET /sso/oauth2/authorize<br/>Cookie: auth_token<br/>返回 redirect_location]

    M --> N[解析 redirect_location<br/>获取 tk, authurl, code]
    N --> O[GET /papi/bs/iaauthlogin/login/oauth2<br/>参数: tk, authurl, code<br/>返回 cookies 含 ETEAMSID]

    O --> P[提取 ETEAMSID<br/>缓存到 eteamsid_cache.json]
    P --> L

    L --> Q[POST /api/workflow/list/data/getPortalListData<br/>Cookie: ETEAMSID<br/>获取待阅列表]

    Q --> R{遍历待阅项<br/>按 isremark 分类}

    R -->|isremark=20| S[POST /api/workflow/core/flow/annotation<br/>Cookie: ETEAMSID<br/>参数: requestId, nodeid, isRemark=20<br/>手动已阅]

    R -->|isremark=60| T[POST /api/workflow/core/flowPage/updateReqInfo<br/>Cookie: ETEAMSID<br/>参数: requestId<br/>自动已阅]

    S --> U[完成]
    T --> U
```

### 数据传递说明

| 步骤 | API 端点 | 获取数据 | 用于下一步 |
|------|----------|----------|------------|
| 1 | GET /sso/login | csrf_token, public_key, return_url, client_id | 登录参数 |
| 2 | GET /validatecode/image | 验证码图片 | OCR 识别 |
| 3 | POST /sso/login | cookies (含 auth_token) | OAuth2 授权 |
| 4 | GET /sso/oauth2/authorize | redirect_location (含 tk, code) | 获取 ETEAMSID |
| 5 | GET /papi/bs/iaauthlogin/login/oauth2 | cookies (含 ETEAMSID) | API 请求凭证 |
| 6 | POST /api/workflow/list/data/getPortalListData | 待阅列表 data[] | 分类处理 |
| 7 | POST /flow/annotation | 处理结果 | 完成手动已阅 |
| 8 | POST /flowPage/updateReqInfo | 处理结果 | 完成自动已阅 |

## 验证码识别

使用 [ddddocr](https://github.com/kan련/ddddocr) 自动识别验证码，支持常见的字母数字组合验证码。

如遇识别失败，可查看同目录下的 `validate_code.png` 图片人工确认。

## 依赖

- requests
- pycryptodome
- beautifulsoup4
- selenium
- ddddocr
