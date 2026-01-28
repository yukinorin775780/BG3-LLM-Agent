"""
BG3 Narrative Engine - Config Editor
配置编辑器：可视化编辑角色属性和背包
"""

import os
import yaml
import streamlit as st
from pathlib import Path

# 设置页面配置
st.set_page_config(
    page_title="BG3 Config Editor",
    page_icon="⚔️",
    layout="wide"
)

# 项目根目录路径
PROJECT_ROOT = Path(__file__).parent.parent
ITEMS_YAML = PROJECT_ROOT / "config" / "items.yaml"
CHARACTER_YAML = PROJECT_ROOT / "characters" / "shadowheart.yaml"
MEMORY_FILE = PROJECT_ROOT / "data" / "shadowheart_memory.json"


def load_data():
    """
    加载数据文件
    返回: (items_dict, character_dict) 或 (None, None) 如果文件不存在
    """
    items_data = None
    character_data = None
    
    # 加载物品数据库 (只读)
    if not ITEMS_YAML.exists():
        st.error(f"❌ 物品数据库未找到: {ITEMS_YAML}")
    else:
        try:
            with open(ITEMS_YAML, 'r', encoding='utf-8') as f:
                items_data = yaml.safe_load(f)
            st.success(f"✅ 物品数据库已加载: {len(items_data.get('items', {}))} 个物品")
        except Exception as e:
            st.error(f"❌ 读取物品数据库失败: {e}")
    
    # 加载角色数据 (读写)
    if not CHARACTER_YAML.exists():
        st.error(f"❌ 角色文件未找到: {CHARACTER_YAML}")
    else:
        try:
            with open(CHARACTER_YAML, 'r', encoding='utf-8') as f:
                character_data = yaml.safe_load(f)
            st.success(f"✅ 角色数据已加载: {character_data.get('name', 'Unknown')}")
        except Exception as e:
            st.error(f"❌ 读取角色文件失败: {e}")
    
    return items_data, character_data


def save_character_data(character_data):
    """
    保存角色数据到 YAML 文件
    """
    try:
        with open(CHARACTER_YAML, 'w', encoding='utf-8') as f:
            yaml.dump(character_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        return True
    except Exception as e:
        st.error(f"❌ 保存失败: {e}")
        return False


def main():
    """主函数"""
    st.title("⚔️ BG3 Narrative Engine - Config Editor")
    st.markdown("---")
    
    # 加载数据
    items_data, character_data = load_data()
    
    if items_data is None or character_data is None:
        st.stop()
    
    # 初始化 session state（用于存储编辑后的数据）
    if 'character_data' not in st.session_state:
        st.session_state.character_data = character_data.copy()
    
    # 获取物品列表
    items_dict = items_data.get('items', {})
    item_options = [f"{item_id} - {item_data.get('name', item_id)}" 
                    for item_id, item_data in items_dict.items()]
    
    # 创建左右两栏布局
    col_left, col_right = st.columns(2)
    
    # ==========================================
    # 左侧栏：角色属性编辑
    # ==========================================
    with col_left:
        st.header("📊 角色属性 (Attributes)")
        
        # 确保 ability_scores 存在
        if 'ability_scores' not in st.session_state.character_data:
            st.session_state.character_data['ability_scores'] = {}
        
        ability_scores = st.session_state.character_data['ability_scores']
        
        # 能力值滑块
        st.subheader("能力值 (Ability Scores)")
        ability_names = {
            'STR': '力量 (Strength)',
            'DEX': '敏捷 (Dexterity)',
            'CON': '体质 (Constitution)',
            'INT': '智力 (Intelligence)',
            'WIS': '感知 (Wisdom)',
            'CHA': '魅力 (Charisma)'
        }
        
        for abbr, full_name in ability_names.items():
            current_value = ability_scores.get(abbr, 10)
            new_value = st.slider(
                full_name,
                min_value=1,
                max_value=20,
                value=current_value,
                key=f"ability_{abbr}"
            )
            ability_scores[abbr] = new_value
        
        st.markdown("---")
        
        # 好感度滑块
        st.subheader("💕 好感度 (Relationship)")
        if 'relationship' not in st.session_state.character_data:
            st.session_state.character_data['relationship'] = 0
        
        current_relationship = st.session_state.character_data.get('relationship', 0)
        new_relationship = st.slider(
            "关系值 (Relationship Score)",
            min_value=-100,
            max_value=100,
            value=current_relationship,
            key="relationship_slider"
        )
        st.session_state.character_data['relationship'] = new_relationship
        
        # 显示当前好感度状态
        if new_relationship < -50:
            st.warning(f"😠 敌对关系: {new_relationship}")
        elif new_relationship < 0:
            st.info(f"😐 冷淡关系: {new_relationship}")
        elif new_relationship < 50:
            st.success(f"😊 友好关系: {new_relationship}")
        else:
            st.success(f"❤️ 亲密关系: {new_relationship}")
    
    # ==========================================
    # 右侧栏：背包管理
    # ==========================================
    with col_right:
        st.header("🎒 背包管理 (Inventory)")
        
        # 确保 inventory 存在
        if 'inventory' not in st.session_state.character_data:
            st.session_state.character_data['inventory'] = []
        
        inventory_list = st.session_state.character_data['inventory']
        
        # 显示当前背包
        st.subheader("当前背包物品")
        if not inventory_list:
            st.info("📦 背包为空")
        else:
            for idx, item_id in enumerate(inventory_list):
                item_name = items_dict.get(item_id, {}).get('name', item_id)
                col_item, col_btn = st.columns([4, 1])
                with col_item:
                    st.write(f"• **{item_name}** (`{item_id}`)")
                with col_btn:
                    if st.button("❌ Remove", key=f"remove_{idx}"):
                        # 从列表中移除
                        inventory_list.pop(idx)
                        st.session_state.character_data['inventory'] = inventory_list
                        st.rerun()
        
        st.markdown("---")
        
        # 添加物品
        st.subheader("添加物品")
        if item_options:
            selected_item_display = st.selectbox(
                "选择要添加的物品",
                options=item_options,
                key="item_selector"
            )
            
            # 从显示文本中提取 item_id
            if selected_item_display:
                selected_item_id = selected_item_display.split(" - ")[0]
                
                if st.button("➕ Add Item", key="add_item_btn"):
                    # 检查是否已存在
                    if selected_item_id in inventory_list:
                        st.warning(f"⚠️ 物品已存在于背包中: {items_dict.get(selected_item_id, {}).get('name', selected_item_id)}")
                    else:
                        inventory_list.append(selected_item_id)
                        st.session_state.character_data['inventory'] = inventory_list
                        st.success(f"✅ 已添加: {items_dict.get(selected_item_id, {}).get('name', selected_item_id)}")
                        st.rerun()
        else:
            st.warning("⚠️ 没有可用的物品")
    
    # ==========================================
    # 侧边栏：保存功能
    # ==========================================
    with st.sidebar:
        st.header("💾 保存设置")
        st.markdown("---")
        
        # 显示当前状态摘要
        st.subheader("📋 当前状态")
        ability_scores = st.session_state.character_data.get('ability_scores', {})
        relationship = st.session_state.character_data.get('relationship', 0)
        inventory_count = len(st.session_state.character_data.get('inventory', []))
        
        st.write(f"**能力值**: {len(ability_scores)} 项")
        st.write(f"**好感度**: {relationship}")
        st.write(f"**背包物品**: {inventory_count} 个")
        
        st.markdown("---")
        
        # 保存按钮
        if st.button("💾 Save Changes", type="primary", use_container_width=True):
            # 将 session_state 中的所有更改同步到 character_data
            # 需要深度复制，因为 YAML 可能包含嵌套结构
            import copy
            updated_data = copy.deepcopy(character_data)
            
            # 更新能力值
            if 'ability_scores' in st.session_state.character_data:
                updated_data['ability_scores'] = st.session_state.character_data['ability_scores'].copy()
            
            # 更新好感度
            if 'relationship' in st.session_state.character_data:
                updated_data['relationship'] = st.session_state.character_data['relationship']
            
            # 更新背包
            if 'inventory' in st.session_state.character_data:
                updated_data['inventory'] = st.session_state.character_data['inventory'].copy()
            
            # 保存到文件
            if save_character_data(updated_data):
                # 更新 session_state 和 character_data 引用
                st.session_state.character_data = updated_data
                st.success("✅ Character data saved successfully!")
                st.balloons()
            else:
                st.error("❌ Save failed. Please check the error message above.")
        
        st.markdown("---")
        st.caption("💡 提示: 修改后请点击保存按钮以持久化更改")
        
        # ==========================================
        # 危险区域：重置游戏记忆
        # ==========================================
        st.markdown("---")
        st.header("⚠️ Danger Zone")
        
        # 检查记忆文件是否存在
        memory_exists = MEMORY_FILE.exists() if MEMORY_FILE else False
        
        if memory_exists:
            st.warning("⚠️ Save data detected. Config changes may be ignored by the game.")
            st.caption(f"File: `{MEMORY_FILE.name}`")
            
            if st.button("🗑️ Reset/Delete Save Data", type="secondary", use_container_width=True):
                try:
                    # 删除记忆文件
                    MEMORY_FILE.unlink()
                    st.success("✅ Memory wiped! Next run will use the new Config values.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to delete save data: {e}")
        else:
            st.info("ℹ️ No save data found. Game will use Config values on next run.")


if __name__ == "__main__":
    main()
