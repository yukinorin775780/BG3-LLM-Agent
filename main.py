"""
BG3 LLM Agent - Main Entry Point
Reads character attributes and generates dialogue using LLM API (阿里云百炼)
"""

import os
import sys
import json
from dotenv import load_dotenv
from characters.loader import load_character
from core.engine import generate_dialogue, parse_approval_change

# Load environment variables from .env file
load_dotenv()

# 定义记忆文件保存的位置
MEMORY_FILE = "data/shadowheart_memory.json"

# 角色名称
CHARACTER_NAME = "shadowheart"


def calculate_ability_modifier(ability_score):
    """
    Calculate D&D 5e ability modifier from ability score.
    
    Formula: (ability_score - 10) // 2
    
    Args:
        ability_score: The ability score (typically 1-20)
    
    Returns:
        int: The ability modifier
    """
    return (ability_score - 10) // 2


def get_ability_modifiers(ability_scores):
    """
    Calculate all ability modifiers from ability scores.
    
    Args:
        ability_scores: Dictionary of ability scores (e.g., {"STR": 13, "DEX": 14, ...})
    
    Returns:
        dict: Dictionary of ability modifiers with same keys
    """
    return {ability: calculate_ability_modifier(score) for ability, score in ability_scores.items()}




def load_memory(default_relationship_score=0):
    """
    从本地文件读取记忆，支持优先级系统。
    
    优先级（从高到低）：
    1. 记忆文件中的 relationship_score（如果存在）
    2. 传入的 default_relationship_score（通常来自 YAML 配置）
    3. 默认值 0
    
    Args:
        default_relationship_score: 默认关系值，通常从 YAML 配置文件中读取
    
    Returns:
        dict: 包含 relationship_score 和 history 的字典
    """
    # 尝试从记忆文件读取
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:  # 如果是空文件，使用默认值
                    print(f"🧠 [System] 记忆文件为空，使用 YAML 配置的关系值: {default_relationship_score}")
                    return {"relationship_score": default_relationship_score, "history": []}
                
                data = json.loads(content)
                
                # 向后兼容：如果文件是列表格式（旧格式），转换为新格式
                if isinstance(data, list):
                    print(f"🧠 [System] 检测到旧格式记忆文件，正在转换...")
                    print(f"💕 [System] 使用 YAML 配置的关系值: {default_relationship_score}")
                    return {"relationship_score": default_relationship_score, "history": data}
                
                # 新格式：包含 relationship_score 和 history
                if isinstance(data, dict):
                    # 优先使用记忆文件中的关系值，如果没有则使用默认值
                    relationship_score = data.get("relationship_score")
                    if relationship_score is None:
                        # 记忆文件中没有关系值，使用 YAML 配置的值
                        relationship_score = default_relationship_score
                        print(f"🧠 [System] 记忆文件中没有关系值，使用 YAML 配置: {relationship_score}")
                    else:
                        # 使用记忆文件中的关系值（最高优先级）
                        print(f"🧠 [System] 成功唤醒记忆，共读取 {len(data.get('history', []))} 条往事...")
                        print(f"💕 [System] 当前关系值（来自记忆）: {relationship_score}/100")
                    
                    history = data.get("history", [])
                    return {"relationship_score": relationship_score, "history": history}
                
                # 如果格式不对，使用默认值
                print(f"⚠️ [System] 记忆文件格式错误，使用 YAML 配置的关系值: {default_relationship_score}")
                return {"relationship_score": default_relationship_score, "history": []}
                
        except Exception as e:
            # 记忆文件读取失败，使用 YAML 配置的值
            print(f"⚠️ [System] 记忆文件读取失败，使用 YAML 配置的关系值: {default_relationship_score} ({e})")
            return {"relationship_score": default_relationship_score, "history": []}
    
    # 记忆文件不存在，使用 YAML 配置的值
    print(f"🧠 [System] 未找到记忆文件，使用 YAML 配置的关系值: {default_relationship_score}")
    return {"relationship_score": default_relationship_score, "history": []}


def save_memory(memory_data):
    """把记忆写入本地文件"""
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(memory_data, f, ensure_ascii=False, indent=2)
        print("💾 [System] 记忆已固化至莎尔的卷轴中。")
    except Exception as e:
        print(f"❌ [System] 存档失败: {e}")


def main():
    """Main function to load attributes and generate dialogue"""
    print("=" * 60)
    print("BG3 LLM Agent - Shadowheart Dialogue Generator")
    print("=" * 60)
    
    # Load character
    print("Loading Shadowheart's attributes...")
    character = load_character(CHARACTER_NAME)
    attributes = character.data  # 保留对原始数据的引用，用于显示
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
        # 1. 【关键修改】启动时尝试加载旧记忆
        # 优先级：记忆文件 > YAML 配置 > 默认值 0
        # 从 YAML 配置中获取初始关系值作为默认值
        default_relationship = attributes.get('relationship', 0)
        memory_data = load_memory(default_relationship_score=default_relationship)
        relationship_score = memory_data["relationship_score"]
        conversation_history = memory_data["history"]
        
        # 2. 生成 System Prompt（使用 Character 对象的 render_prompt 方法）
        system_prompt = character.render_prompt(relationship_score)
        
        print("=" * 60)
        # 如果是新对话（没记忆），生成并打印开场白
        if not conversation_history:
            # 生成初始问候（使用空的对话历史）
            dialogue = generate_dialogue(system_prompt, conversation_history=conversation_history)
            
            # 解析 approval change（初始问候通常不会有变化，但为了统一处理）
            approval_change, cleaned_dialogue = parse_approval_change(dialogue)
            
            # 更新关系值
            relationship_score += approval_change
            
            # 清理引号
            if cleaned_dialogue:
                cleaned_dialogue = cleaned_dialogue.strip('"').strip("'")
            
            print(f"{attributes['name']} (Looking at you warily):")
            print(f'"{cleaned_dialogue}"')
            
            # 把初始问候加入对话历史（存储清理后的文本）
            conversation_history.append({"role": "assistant", "content": cleaned_dialogue})
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
                    memory_data = {
                        "relationship_score": relationship_score,
                        "history": conversation_history
                    }
                    save_memory(memory_data)
                    print("\n再见！")
                    break
                
                # 1. 存入用户输入
                conversation_history.append({"role": "user", "content": user_input})
                
                # 2. 更新 system prompt 以反映当前关系值（因为关系值可能已改变）
                system_prompt = character.render_prompt(relationship_score)
                
                # 3. 生成回复 (注意：这里我们传入整个历史)
                print(f"\n{attributes['name']}: ", end="", flush=True)
                response = generate_dialogue(system_prompt, conversation_history=conversation_history)
                
                # 4. 解析 approval change
                approval_change, cleaned_response = parse_approval_change(response)
                
                # 5. 更新关系值
                if approval_change != 0:
                    old_score = relationship_score
                    relationship_score += approval_change
                    # 限制关系值在 -100 到 100 之间
                    relationship_score = max(-100, min(100, relationship_score))
                    
                    # 打印系统调试信息
                    change_str = f"+{approval_change}" if approval_change > 0 else str(approval_change)
                    print(f"\n💕 [System] 关系值变化: {change_str} (当前: {relationship_score}/100)")
                    print(f"{attributes['name']}: ", end="", flush=True)
                
                # 6. 处理一下回复格式
                if cleaned_response:
                    cleaned_response = cleaned_response.strip('"').strip("'")
                    print(f'"{cleaned_response}"')
                else:
                    print("（没有回应）")
                print()
                
                # 7. 存入 AI 回复（存储清理后的文本，不包含 approval tag）
                conversation_history.append({"role": "assistant", "content": cleaned_response})
                
                # 8. 【可选】每轮对话都自动存档（防止程序崩了丢失记忆）
                # memory_data = {
                #     "relationship_score": relationship_score,
                #     "history": conversation_history
                # }
                # save_memory(memory_data)
                
                # 9. 滚动窗口：防止 Token 爆炸（保留最近 20 轮）
                # 注意：这里我们只是截断"发给 AI"的列表，还是截断"存储"的列表？
                # 为了简单，我们暂时让记忆文件也保持在 20 轮以内，避免文件无限膨胀
                if len(conversation_history) > 20:
                    conversation_history = conversation_history[-20:]
                    
            except KeyboardInterrupt:
                # 强制中断也要存档
                memory_data = {
                    "relationship_score": relationship_score,
                    "history": conversation_history
                }
                save_memory(memory_data)
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

