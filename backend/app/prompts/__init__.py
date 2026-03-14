"""
Prompts 管理模块

集中管理所有 LLM Prompt 模板
"""
import os
import re
from typing import Dict, Optional

# Prompt 文件路径
PROMPTS_FILE = os.path.join(os.path.dirname(__file__), "prompts.md")


class PromptManager:
    """Prompt 管理器"""

    _instance = None
    _prompts: Dict[str, str] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_prompts()
        return cls._instance

    def _load_prompts(self):
        """从 markdown 文件加载所有 prompts"""
        if not os.path.exists(PROMPTS_FILE):
            print(f"[PromptManager] Warning: {PROMPTS_FILE} not found, using default prompts")
            self._load_default_prompts()
            return

        try:
            with open(PROMPTS_FILE, 'r', encoding='utf-8') as f:
                content = f.read()

            # 解析 markdown 中的 prompt 代码块
            # 格式: ## N. Prompt名称 ... ```markdown ... ```
            # 支持中英文名称
            pattern = r'##\s*\d+\.\s*([^\n]+?)\s*Prompt.*?```markdown\n(.*?)```'
            matches = re.findall(pattern, content, re.DOTALL)

            for name, prompt_content in matches:
                # 生成 key: 去掉多余空格，小写，空格转下划线
                key = name.strip().lower().replace(' ', '_')
                # 中文名称直接映射
                if not key:
                    key = name.strip()
                self._prompts[key] = prompt_content.strip()
                print(f"[PromptManager] Loaded prompt: {key}")

            # 如果没有加载到任何 prompt，使用默认
            if not self._prompts:
                self._load_default_prompts()

        except Exception as e:
            print(f"[PromptManager] Error loading prompts: {e}")
            self._load_default_prompts()

    def _load_default_prompts(self):
        """加载默认 prompts"""
        self._prompts = {
            'customer_service_system': """你是智能客服助手，正在为用户"{username}"提供服务。

你的职责：
1. 友好、专业地回答用户的售前、售后、物流、退款等问题
2. 用中文回复，语气亲切自然
3. 如果不确定答案，引导用户提供更多信息

回复要求：
- 开头要称呼用户，如"{username}，您好"
- 回答要简洁明了，控制在100字以内
- 如果是问候语，要热情回应""",

            'greeting_generation': """你是智能客服助手，为用户'{username}'提供服务。

首问要求：
- 自然欢迎
- 简要说明可咨询范围（如订单、物流、退款、售后规则等）
- 鼓励用户直接描述问题
- 不要一上来索要订单号或让用户选类型
- 不超过50字

推荐风格：
"你好，我是智能客服助手。你可以直接告诉我遇到的问题，比如订单、物流、退款或售后规则，我来帮你看看。"

请生成一句符合上述要求的首问问候语。""",


            'intent_recognition': """你是智能客服系统的意图理解引擎。请深度分析用户输入的语义，准确识别用户真实意图。

用户输入: {user_input}

当前会话状态:
- 当前主题: {current_topic}
- 当前任务: {current_task}
- 待补槽位: {pending_slot}
- 最近对话历史: {recent_messages}

请基于语义理解（而非关键词匹配）分析用户意图，输出 JSON 格式...
"""
        }
        print("[PromptManager] Loaded default prompts")

    def get(self, name: str, **kwargs) -> str:
        """
        获取 prompt 模板并填充变量

        Args:
            name: prompt 名称
            **kwargs: 模板变量

        Returns:
            填充后的 prompt 字符串
        """
        template = self._prompts.get(name, "")
        if not template:
            print(f"[PromptManager] Warning: Prompt '{name}' not found")
            return ""

        try:
            return template.format(**kwargs)
        except KeyError as e:
            print(f"[PromptManager] Warning: Missing variable {e} for prompt '{name}'")
            return template

    def reload(self):
        """重新加载 prompts"""
        self._prompts.clear()
        self._load_prompts()
        print("[PromptManager] Prompts reloaded")


# 全局 prompt 管理器实例
prompt_manager = PromptManager()


# 便捷函数
def get_prompt(name: str, **kwargs) -> str:
    """获取 prompt 模板"""
    return prompt_manager.get(name, **kwargs)


def reload_prompts():
    """重新加载 prompts"""
    prompt_manager.reload()
