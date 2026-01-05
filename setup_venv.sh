#!/bin/bash
# 创建虚拟环境并安装依赖

echo "正在创建虚拟环境..."
python3 -m venv venv

echo "激活虚拟环境..."
source venv/bin/activate

echo "升级 pip..."
pip install --upgrade pip

echo "安装项目依赖..."
pip install -r requirements.txt

echo ""
echo "✅ 虚拟环境创建完成！"
echo ""
echo "⚠️  重要提示：如果你使用 conda，请先退出 conda base 环境："
echo "  conda deactivate"
echo ""
echo "然后激活虚拟环境："
echo "  source venv/bin/activate"
echo ""
echo "验证虚拟环境是否正确激活："
echo "  which python"
echo "  # 应该显示: .../BG3_LLM_Agent/venv/bin/python"
echo ""
echo "要退出虚拟环境，请运行："
echo "  deactivate"

