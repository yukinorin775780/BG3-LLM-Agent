import os
from openai import OpenAI
import sys
import re
from config import settings

# 检查 API Key 是否存在
if not settings.API_KEY:
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
    client = OpenAI(api_key=settings.API_KEY, base_url=settings.BASE_URL)
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
            model=settings.MODEL_NAME,
            messages=messages,  # type: ignore
            temperature=0.7,
            max_tokens=500  # 控制回复长度
        )
        content = completion.choices[0].message.content
        return content if content else "（影心似乎陷入了沉思，没有回应……）"

    except Exception as e:
        print(f"\n[Engine Error]: {e}")
        return "（影心似乎陷入了沉思，没有回应……）"


def update_summary(current_summary: str, recent_history: list) -> str:
    """
    Generate or update a story summary using the LLM.
    
    Takes the previous summary and recent conversation history, then uses the LLM
    to condense the recent events into the summary, keeping it concise and in
    third-person perspective.
    
    Args:
        current_summary: The existing story summary (empty string for first summary)
        recent_history: List of recent conversation messages to summarize
    
    Returns:
        str: The updated summary string
    """
    # Format recent history for the prompt
    history_text = ""
    for msg in recent_history:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        if role == 'user':
            history_text += f"Player: {content}\n"
        elif role == 'assistant':
            history_text += f"Shadowheart: {content}\n"
    
    # Construct the prompt
    if current_summary:
        prompt = f"""Here is the previous story summary: '{current_summary}'

Here are the recent events:
{history_text}

Please condense the recent events into the summary, keeping it concise and in third-person perspective. 
Update the summary to include these new events while maintaining continuity."""
    else:
        prompt = f"""Here are recent events:
{history_text}

Please create a concise story summary in third-person perspective, capturing the key events and relationship dynamics."""
    
    try:
        messages = [{"role": "user", "content": prompt}]
        completion = client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=messages,  # type: ignore
            temperature=0.3,  # Lower temperature for more consistent summarization
            max_tokens=300  # Keep summaries concise
        )
        content = completion.choices[0].message.content
        return content.strip() if content else current_summary
    except Exception as e:
        print(f"\n[Engine Error] Summary generation failed: {e}")
        return current_summary  # Return existing summary on error


def parse_ai_response(response_text: str) -> dict:
    """
    Parse [THOUGHT], [APPROVAL], [STATE], and [ACTION] tags from LLM response.
    
    Extracts thought block, approval delta, new state if any, action if any,
    and the dialogue text with all tags and thought content removed.
    
    Args:
        response_text: Raw text from LLM
    
    Returns:
        dict with keys:
            - thought (str or None): Content between [THOUGHT] and [/THOUGHT]
            - approval (int): Relationship change, clamped to -5..+5 (default 0)
            - new_state (str or None): "SILENT", "VULNERABLE", "NORMAL", or None
            - action (str or None): e.g. "USE_POTION"
            - text (str): Spoken dialogue with all tags and thought block stripped
    """
    if not response_text:
        return {"thought": None, "approval": 0, "new_state": None, "action": None, "text": ""}

    text = response_text.strip()
    approval = 0
    new_state = None
    action = None
    thought = None

    # Extract [THOUGHT] ... [/THOUGHT] (first occurrence; . matches newlines)
    thought_pattern = r'\[THOUGHT\](.*?)\[/THOUGHT\]'
    thought_match = re.search(thought_pattern, text, re.IGNORECASE | re.DOTALL)
    if thought_match:
        thought = thought_match.group(1).strip()
    # Remove thought block from text so it does not appear in spoken dialogue
    cleaned_text = re.sub(thought_pattern, '', text, flags=re.IGNORECASE | re.DOTALL)

    # Extract [APPROVAL: +X] or [APPROVAL: -X] (anywhere in text; last occurrence wins)
    approval_pattern = r'\[APPROVAL:\s*([+-]?\d+)\s*\]'
    approval_matches = list(re.finditer(approval_pattern, cleaned_text, re.IGNORECASE))
    if approval_matches:
        score_str = approval_matches[-1].group(1)
        approval = int(score_str)
        approval = max(-5, min(5, approval))  # Clamp to -5..+5

    # Extract [STATE: SILENT], [STATE: VULNERABLE], or [STATE: NORMAL] (last occurrence wins)
    state_pattern = r'\[STATE:\s*(SILENT|VULNERABLE|NORMAL)\s*\]'
    state_matches = list(re.finditer(state_pattern, cleaned_text, re.IGNORECASE))
    if state_matches:
        new_state = state_matches[-1].group(1).upper()

    # Extract [ACTION: (\w+)] (e.g. USE_POTION)
    action_pattern = r'\[ACTION:\s*([\w_]+)\s*\]'
    action_matches = list(re.finditer(action_pattern, cleaned_text, re.IGNORECASE))
    if action_matches:
        action = action_matches[-1].group(1).upper()

    # Remove all remaining tags to produce final spoken text
    cleaned_text = re.sub(approval_pattern, '', cleaned_text, flags=re.IGNORECASE)
    cleaned_text = re.sub(state_pattern, '', cleaned_text, flags=re.IGNORECASE)
    cleaned_text = re.sub(action_pattern, '', cleaned_text, flags=re.IGNORECASE)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip().strip('"').strip("'")

    return {"thought": thought, "approval": approval, "new_state": new_state, "action": action, "text": cleaned_text}