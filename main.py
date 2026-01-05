"""
BG3 LLM Agent - Main Entry Point
Reads character attributes and generates dialogue using LLM API (阿里云百炼)
"""

import os
from dotenv import load_dotenv
from characters.shadowheart import SHADOWHEART_ATTRIBUTES

# Load environment variables from .env file
load_dotenv()

try:
    import dashscope
    from dashscope import Generation
except ImportError:
    print("Warning: dashscope package not found. Please install it with: pip install dashscope")
    dashscope = None
    Generation = None


def load_character_attributes():
    """Load Shadowheart's attributes from the character file"""
    return SHADOWHEART_ATTRIBUTES


def create_character_prompt(attributes):
    """Create a detailed prompt for the LLM based on character attributes"""
    prompt = f"""You are {attributes['name']}, a {attributes['race']} {attributes['class']} in the world of Dungeons & Dragons.

**Character Profile:**
- Race: {attributes['race']}
- Class: {attributes['class']} ({attributes['subclass']})
- Deity: {attributes['deity']}
- Level: {attributes['level']}

**Ability Scores:**
- Strength: {attributes['ability_scores']['STR']} (+{attributes['ability_modifiers']['STR']})
- Dexterity: {attributes['ability_scores']['DEX']} (+{attributes['ability_modifiers']['DEX']})
- Constitution: {attributes['ability_scores']['CON']} (+{attributes['ability_modifiers']['CON']})
- Intelligence: {attributes['ability_scores']['INT']} (+{attributes['ability_modifiers']['INT']})
- Wisdom: {attributes['ability_scores']['WIS']} (+{attributes['ability_modifiers']['WIS']})
- Charisma: {attributes['ability_scores']['CHA']} (+{attributes['ability_modifiers']['CHA']})

**Personality:**
{chr(10).join('- ' + trait for trait in attributes['personality']['traits'])}

**Ideals:** {attributes['personality']['ideals']}
**Bonds:** {attributes['personality']['bonds']}
**Flaws:** {attributes['personality']['flaws']}

**Background:** {attributes['background']['description']}

**Dialogue Style:**
- Tone: {attributes['dialogue_style']['tone']}
- Speech Patterns: {', '.join(attributes['dialogue_style']['speech_patterns'])}

**Task:** Say your first line of dialogue to someone you've just met. Make it mysterious, guarded, but show a hint of your true nature. Keep it brief (1-2 sentences). Speak as Shadowheart would, referencing your devotion to Shar if appropriate.
Output strictly in Chinese (Simplified). The tone should be similar to the official Chinese localization of Baldur's Gate 3 (elegant, archaic, and cold).
"""
    return prompt


def generate_dialogue_with_bailian(prompt, api_key=None):
    """Generate dialogue using 阿里云百炼 API (DashScope)"""
    if dashscope is None or Generation is None:
        raise ImportError("dashscope package is required. Install it with: pip install dashscope")
    
    # Get API key from environment or parameter
    api_key = api_key or os.getenv("BAILIAN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError(
            "百炼 API key not found. Please set BAILIAN_API_KEY or DASHSCOPE_API_KEY in .env file "
            "or pass it as a parameter."
        )
    
    # Set API key for dashscope
    # dashscope SDK 会自动使用正确的 API endpoint
    dashscope.api_key = api_key
    
    # Call DashScope API
    messages = [
        {
            "role": "system",
            "content": "You are a role-playing assistant that generates authentic character dialogue for D&D characters."
        },
        {
            "role": "user",
            "content": prompt
        }
    ]
    
    response = Generation.call(
        model="qwen-plus",  # 使用通义千问模型
        messages=messages,
        result_format='message',  # 重要：指定返回格式为 message
        temperature=0.8,  # 稍微有创造性，让对话更自然
        max_tokens=150,
    )
    
    # 检查响应是否为 None
    if response is None:
        raise Exception("API 调用返回 None，请检查网络连接和 API Key")
    
    # Check if response is successful
    status_code = getattr(response, 'status_code', None)
    
    # 如果状态码不是 200，打印详细错误信息
    if status_code != 200:
        error_msg = getattr(response, 'message', None)
        request_id = getattr(response, 'request_id', None)
        code = getattr(response, 'code', None)
        raise Exception(
            f"API 调用失败\n"
            f"  状态码: {status_code}\n"
            f"  错误信息: {error_msg}\n"
            f"  错误代码: {code}\n"
            f"  请求ID: {request_id}"
        )
    
    # 安全地访问响应数据
    output = getattr(response, 'output', None)
    if not output:
        # 打印响应结构以便调试
        raise Exception(
            f"API 响应中没有 output 数据\n"
            f"  响应类型: {type(response)}\n"
            f"  响应属性: {[attr for attr in dir(response) if not attr.startswith('_')]}"
        )
    
    choices = getattr(output, 'choices', None)
    if not choices:
        raise Exception("API 响应中没有 choices 数据")
    if len(choices) == 0:
        raise Exception("API 响应的 choices 列表为空")
    
    first_choice = choices[0]
    message = getattr(first_choice, 'message', None)
    if not message:
        raise Exception("API 响应中没有 message 数据")
    
    content = getattr(message, 'content', None)
    if content:
        return content.strip() if isinstance(content, str) else str(content)
    else:
        raise Exception("API 响应中的 message 没有 content 字段")


def main():
    """Main function to load attributes and generate dialogue"""
    print("=" * 60)
    print("BG3 LLM Agent - Shadowheart Dialogue Generator")
    print("=" * 60)
    
    # Load character attributes
    print("Loading Shadowheart's attributes...")
    attributes = load_character_attributes()
    print(f"✓ Loaded attributes for {attributes['name']}")
    print(f"  - {attributes['race']} {attributes['class']} (Level {attributes['level']})")
    print(f"  - Deity: {attributes['deity']}")
    print()
    
    # Display key attributes
    print("Key Attributes:")
    for ability, score in attributes['ability_scores'].items():
        modifier = attributes['ability_modifiers'][ability]
        print(f"  {ability}: {score} (+{modifier:+d})")
    print()
    
    # Create prompt and generate dialogue
    print("Generating dialogue...")
    try:
        prompt = create_character_prompt(attributes)
        dialogue = generate_dialogue_with_bailian(prompt)
        
        print("=" * 60)
        print(f"{attributes['name']} says:")
        print("=" * 60)
        print(f'"{dialogue}"')
        print("=" * 60)
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print("\n请安装必要的依赖包:")
        print("  pip install dashscope python-dotenv")
        
    except ValueError as e:
        print(f"❌ 配置错误: {e}")
        print("\n要使用百炼 API，你需要:")
        print("1. 安装 dashscope 包: pip install dashscope")
        print("2. 在项目根目录创建 .env 文件")
        print("3. 添加你的 API key: BAILIAN_API_KEY=your-api-key")
        print("\n或者使用模拟响应进行测试:")
        
        # Fallback mock dialogue
        print("\n" + "=" * 60)
        print("Mock Dialogue (API not configured):")
        print("=" * 60)
        print('"Shar\'s will be done. I sense there\'s more to you than meets the eye, '
              'just as there is more to me. Trust is earned, not given freely."')
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ 意外错误: {e}")
        print(f"错误类型: {type(e).__name__}")
        import traceback
        print("\n详细错误信息:")
        traceback.print_exc()


if __name__ == "__main__":
    main()

