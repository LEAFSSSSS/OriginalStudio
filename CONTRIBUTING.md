# 参与拾序 / Contributing

感谢你帮助这个项目变得更易用。中文或英文反馈都可以。

## 报告问题

请通过 [Issues](https://github.com/LEAFSSSSS/OriginalStudio/issues) 提供：

- Windows 与 Python 版本、项目版本。
- 从哪里开始，点击了哪些按钮。
- 预期结果和实际结果。
- 如涉及文件格式，提供可公开的小样本或说明编码与扩展名。

优先提供能独立复现问题的信息。分享日志或截图前，请移除个人路径、素材内容与凭据。

## 提出需求

描述你在整理或检索什么素材、当前卡在哪一步，以及希望怎样完成这项工作。欢迎先讨论使用场景，再决定实现方式。

## 提交代码

1. Fork 项目并从 `main` 创建自己的分支。
2. 按 README 准备 Python 3.11 环境。界面为原生 ES modules，无需前端构建。
3. 每个 PR 聚焦一项改动，并说明原因、影响范围和你实际执行的检查。
4. 保留现有文件路径校验、本机请求限制、SQLite 事务与任务恢复行为。
5. 不提交 `.env`、模型、素材、数据库、虚拟环境或运行日志。

维护检查命令：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Get-ChildItem static/*.js | ForEach-Object { node --check $_.FullName }
```

如未执行某项检查，请在 PR 中如实说明。

## License

By submitting a contribution, you agree to license it under the project's **GPL-3.0-only** license. Keep third-party copyright and license notices when adding external material.
