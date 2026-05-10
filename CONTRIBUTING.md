# Contributing to BrowsePilot

感谢你对 BrowsePilot 的关注。欢迎以 Issue 或 Pull Request 的形式参与贡献。

## 开发环境

```bash
# Python 3.11+
uv venv && source .venv/Scripts/activate
uv pip install -r requirements.txt
playwright install chromium

# 前端
cd frontend-vue && npm install
```

## 分支策略

- `master` — 稳定版本
- 功能开发请从 `master` 创建特性分支：`feature/your-feature`
- 修复请创建：`fix/your-bugfix`

## 提交规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
feat: 新功能
fix: 错误修复
docs: 文档变更
refactor: 重构
chore: 构建/工具变更
test: 测试相关
```

提交信息使用英文，简洁描述改动内容。

## 代码风格

- Python：遵循 PEP 8
- TypeScript/Vue：遵循项目已有的 ESLint 配置
- 优先使用已有模块中的模式，保持风格一致
- 命名清晰，函数单一职责

## 测试

提交前请确保：

```bash
# Backend 能正常启动
python -m browser_mcp.main &  # 端口 8090
uvicorn backend.app.main:app --port 8000

# 发送测试请求验证 Agent 流程
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"task": "Hello", "session_id": "test"}'
```

## Issue 规范

- Bug 报告：描述复现步骤、预期行为、实际行为、环境信息
- 功能请求：描述使用场景和期望的解决方案

## Pull Request 流程

1. Fork 仓库，从 `master` 创建分支
2. 实现改动并提交
3. 确保代码能正常启动和运行
4. 提交 PR，描述改动内容和原因
5. 等待 Review

感谢你的贡献！
