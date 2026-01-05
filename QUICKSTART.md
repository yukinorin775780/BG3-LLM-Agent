# 快速开始指南

## 1. 激活虚拟环境

```bash
source venv/bin/activate
```

激活后，你的终端提示符前会显示 `(venv)`。

## 2. 安装依赖

```bash
pip install -r requirements.txt
```

这会安装：
- `dashscope` - 阿里云百炼 API SDK
- `python-dotenv` - 环境变量管理

## 3. 配置 API Key

创建 `.env` 文件（如果还没有）：

```bash
# 在项目根目录创建 .env 文件
cat > .env << EOF
BAILIAN_API_KEY=your_api_key_here
EOF
```

将 `your_api_key_here` 替换为你的实际 API Key。

## 4. 运行程序

```bash
python main.py
```

## 5. 退出虚拟环境（可选）

使用完毕后：

```bash
deactivate
```

---

**提示**：每次打开新的终端窗口使用项目时，都需要先激活虚拟环境（步骤1）。

