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

## 配置

编辑 `config.json`：

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
2. 无效则使用账号密码登录 SSO（需输入验证码）
3. 获取 ETEAMSID 并缓存到本地
4. 获取待阅列表并自动处理

## 依赖

- requests
- pycryptodome
- beautifulsoup4
- selenium
