# Pre-commit 配置说明

## 概述

本项目已配置 pre-commit hooks，在每次 git commit 前自动执行代码检查和格式化。

## 包含的 hooks

1. **ruff lint** - 代码质量检查并自动修复
2. **ruff format** - 代码格式化
3. **trailing-whitespace** - 移除行尾空白
4. **end-of-file-fixer** - 确保文件以换行符结尾
5. **check-yaml** - YAML 文件语法检查
6. **check-added-large-files** - 防止提交大文件

## 使用方法

### 安装依赖
```bash
pdm install
```

### 安装 pre-commit hooks
```bash
pdm run pre-commit install
```

### 手动运行所有检查
```bash
pdm run pre-commit run --all-files
```

### 手动运行特定 hook
```bash
pdm run pre-commit run ruff-format
```

## 注意事项

- 如果 pre-commit 检查失败，提交会被阻止
- 如果代码被自动修复，需要重新 `git add` 并提交
- 可以使用 `git commit --no-verify` 跳过 pre-commit 检查（不推荐）
