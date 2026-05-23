---
name: python-env
description: "Python 环境、运行脚本、执行 pytest 测试、安装 pip 依赖包时必须使用的 Anaconda Agent 虚拟环境。Python 解释器 E:/ananconda/envs/Agent/python.exe"
---

# Python 环境

**必须使用** Anaconda 虚拟环境 `Agent`，不要使用系统 Python。

- **Python 可执行文件**: `E:/ananconda/envs/Agent/python.exe`
- **环境名称**: `Agent`
- **包管理器**: `E:/ananconda/envs/Agent/python.exe -m pip`

## 常用命令

```bash
# 运行 Python 脚本 / 测试 / 模块
E:/ananconda/envs/Agent/python.exe <script.py>
E:/ananconda/envs/Agent/python.exe -m pytest tests -q
E:/ananconda/envs/Agent/python.exe -m pip install <package>
```
