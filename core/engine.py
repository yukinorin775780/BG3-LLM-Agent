import os
from openai import OpenAI
import sys
from dotenv import load_dotenv

# 加载环境变量（必须在获取环境变量之前调用）
load_dotenv()

# ==========================================
# 配置区域
# ==========================================
API_KEY = os.getenv("BAILIAN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
BASE_URL = os.getenv("DASHSCOPE_API_BASE")
MODEL_NAME = "qwen-plus"  # 或者 deepseek-v3

# 检查 API Key 是否存在
if not API_KEY:
    print("❌ 错误: 未找到 API Key")
    print("\n请配置 API Key:")
    print("1. 在项目根目录创建 .env 文件")
    print("2. 添加以下内容之一:")
    print("   BAILIAN_API_KEY=your_api_key_here")
    print("   或")
    print("   DASHSCOPE_API_KEY=your_api_key_here")
    print("\n获取 API Key:")
    print("  访问 https://dashscope.console.aliyun.com/")
    sys.exit(1)

# 初始化客户端
try:
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
except Exception as e:
    print(f"❌ 错误: 初始化 AI 客户端失败: {e}")
    print("\n请检查:")
    print("1. API Key 是否正确")
    print("2. 网络连接是否正常")
    print("3. BASE_URL 配置是否正确（如果设置了）")
    sys.exit(1)

def generate_dialogue(system_prompt, conversation_history=None):
    """
    核心生成函数：将 System Prompt 和 对话历史 组合后发送给 AI
    
    Args:
        system_prompt (str): 影心的人设（只发一次，作为基石）
        conversation_history (list): 之前的对话记录 [{"role": "user",...}, ...]
    
    Returns:
        str: 生成的对话内容，如果出错则返回错误提示
    """
    if conversation_history is None:
        conversation_history = []

    # 1. 构建最终的消息列表
    # 逻辑：[系统人设] + [之前的对话历史]
    messages = [{"role": "system", "content": system_prompt}]
    
    # 把历史记录拼接到后面
    messages.extend(conversation_history)

    try:
        # 2. 调用 API
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,  # type: ignore
            temperature=0.7,
            max_tokens=500  # 控制回复长度
        )
        content = completion.choices[0].message.content
        return content if content else "（影心似乎陷入了沉思，没有回应……）"

    except Exception as e:
        print(f"\n[Engine Error]: {e}")
        return "（影心似乎陷入了沉思，没有回应……）"