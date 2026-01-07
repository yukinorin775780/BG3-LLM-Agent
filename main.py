"""
BG3 LLM Agent - Main Entry Point
Reads character attributes and generates dialogue using LLM API (阿里云百炼)
"""

import os
import sys
import json
from dotenv import load_dotenv
from characters.shadowheart import SHADOWHEART_ATTRIBUTES, create_prompt, get_ability_modifiers
from core.engine import generate_dialogue

# Load environment variables from .env file
load_dotenv()

# 定义记忆文件保存的位置
MEMORY_FILE = "data/shadowheart_memory.json"


def load_character_attributes():
    """Load Shadowheart's attributes from the character file"""
    return SHADOWHEART_ATTRIBUTES


def load_memory():
    """从本地文件读取记忆"""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
                print(f"🧠 [System] 成功唤醒记忆，共读取 {len(history)} 条往事...")
                return history
        except Exception as e:
            print(f"⚠️ [System] 记忆文件读取失败: {e}")
    return []


def save_memory(history):
    """把记忆写入本地文件"""
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        print("💾 [System] 记忆已固化至莎尔的卷轴中。")
    except Exception as e:
        print(f"❌ [System] 存档失败: {e}")


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
    ability_modifiers = get_ability_modifiers(attributes['ability_scores'])
    for ability, score in attributes['ability_scores'].items():
        modifier = ability_modifiers[ability]
        print(f"  {ability}: {score} (+{modifier:+d})")
    print()     
    
    # Generate initial greeting
    print("Generating initial greeting...")
    try:
        # 1. 在循环开始前，生成一次 System Prompt（影心的人设）
        system_prompt = create_prompt(attributes)
        
        # 2. 【关键修改】启动时尝试加载旧记忆
        # 如果没有旧记忆，就从空列表开始
        conversation_history = load_memory()
        
        print("=" * 60)
        # 如果是新对话（没记忆），生成并打印开场白
        if not conversation_history:
            # 生成初始问候（使用空的对话历史）
            dialogue = generate_dialogue(system_prompt, conversation_history=conversation_history)
            
            # 清理引号
            if dialogue:
                dialogue = dialogue.strip('"').strip("'")
            
            print(f"{attributes['name']} (Looking at you warily):")
            print(f'"{dialogue}"')
            
            # 把初始问候加入对话历史
            conversation_history.append({"role": "assistant", "content": dialogue})
        else:
            # 如果有记忆，显示不同的开场白
            print(f"{attributes['name']} (Remembers you): *Nods slightly acknowledging your return*")
        print("=" * 60)
        print()
        
        # Start interactive conversation
        print("💬 开始与影心对话（输入 'quit' 或 'exit' 退出并存档）")
        print("=" * 60)
        print()
        
        while True:
            try:
                # Get user input
                user_input = input("你: ").strip()
                
                if not user_input:
                    continue
                
                # 退出指令
                if user_input.lower() in ['quit', 'exit', '退出', 'q']:
                    # 【关键修改】退出前自动存档
                    save_memory(conversation_history)
                    print("\n再见！")
                    break
                
                # 1. 存入用户输入
                conversation_history.append({"role": "user", "content": user_input})
                
                # 2. 生成回复 (注意：这里我们传入整个历史)
                print(f"\n{attributes['name']}: ", end="", flush=True)
                response = generate_dialogue(system_prompt, conversation_history=conversation_history)
                
                # 处理一下回复格式
                if response:
                    response = response.strip('"').strip("'")
                    print(f'"{response}"')
                else:
                    print("（没有回应）")
                print()
                
                # 3. 存入 AI 回复
                conversation_history.append({"role": "assistant", "content": response})
                
                # 4. 【可选】每轮对话都自动存档（防止程序崩了丢失记忆）
                # save_memory(conversation_history)
                
                # 5. 滚动窗口：防止 Token 爆炸（保留最近 20 轮）
                # 注意：这里我们只是截断"发给 AI"的列表，还是截断"存储"的列表？
                # 为了简单，我们暂时让记忆文件也保持在 20 轮以内，避免文件无限膨胀
                if len(conversation_history) > 20:
                    conversation_history = conversation_history[-20:]
                    
            except KeyboardInterrupt:
                # 强制中断也要存档
                save_memory(conversation_history)
                print("\n\n再见！")
                break
            except Exception as e:
                print(f"\n❌ 错误: {e}")
                print("请重试...\n")
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print("\n请安装必要的依赖包:")
        print("  pip install dashscope python-dotenv")
        
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

