# BG3-LLM-Agent

一个基于大语言模型的博德之门3角色对话生成器，使用阿里云百炼 API。

## 功能特性

- 完整的 D&D 5e 角色属性建模
- 基于角色属性的智能对话生成
- 支持影心（Shadowheart）角色

## 安装依赖

### 方法一：使用自动设置脚本（推荐）

```bash
./setup_venv.sh
```

脚本会自动：
1. 创建虚拟环境 `venv`
2. 激活虚拟环境
3. 升级 pip
4. 安装所有依赖

### 方法二：手动创建虚拟环境

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境（macOS/Linux）
source venv/bin/activate

# 激活虚拟环境（Windows）
# venv\Scripts\activate

# 升级 pip
pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt
```

**注意**：每次使用项目前，记得先激活虚拟环境！

## 配置

1. 在项目根目录创建 `.env` 文件：

```bash
# 阿里云百炼 API 配置
BAILIAN_API_KEY=your_api_key_here
# 或者使用 DASHSCOPE_API_KEY（两者都可以）
# DASHSCOPE_API_KEY=your_api_key_here

# 可选：如果需要自定义 API base URL（通常不需要）
# DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/api/v1
```

2. 获取 API Key：
   - 访问 [阿里云百炼控制台](https://dashscope.console.aliyun.com/)
   - 创建并获取你的 API Key
   - 将 API Key 填入 `.env` 文件

**注意**：通常只需要配置 API Key，SDK 会自动使用正确的 API endpoint。只有在特殊情况下才需要配置 `DASHSCOPE_API_BASE`。

## 使用方法

**重要**：使用前请确保已激活虚拟环境！

```bash
# 激活虚拟环境（macOS/Linux）
source venv/bin/activate

# 激活虚拟环境（Windows）
# venv\Scripts\activate

# 运行主程序
python main.py
```

程序会：
1. 加载影心的角色属性
2. 根据属性生成符合人设的对话
3. 通过百炼 API 生成第一句对话

使用完毕后，可以退出虚拟环境：
```bash
deactivate
```

## 项目结构

```
BG3_LLM_Agent/
├── characters/
│   └── shadowheart.py    # 影心的 D&D 属性定义
├── core/
│   ├── engine.py         # 游戏引擎（待实现）
│   └── dice_roller.py    # 骰子系统（待实现）
├── main.py               # 主程序入口
├── requirements.txt      # Python 依赖
└── .env                  # API 密钥配置（需自行创建）
```

## 注意事项

- `.env` 文件包含敏感信息，已被 `.gitignore` 忽略，不会提交到 Git
- 确保已安装所有依赖包
- API Key 请妥善保管，不要泄露
