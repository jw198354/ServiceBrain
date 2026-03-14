"""
LLM 服务 - 大语言模型调用

负责：
- 调用 Moonshot/OpenAI 等 LLM API
- 客服对话生成
- 意图理解增强
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import httpx
from app.core.config import settings
from app.prompts import get_prompt


@dataclass
class LLMMessage:
    """LLM 消息格式"""
    role: str  # system, user, assistant
    content: str


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None


class LLMService:
    """大语言模型服务"""

    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.base_url = settings.LLM_BASE_URL
        self.api_key = settings.LLM_API_KEY
        self.model = settings.LLM_MODEL
        print(f"[LLMService] Provider: {self.provider}, BaseURL: {self.base_url}, Model: {self.model}")
        print(f"[LLMService] API Key configured: {bool(self.api_key)}")

    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _build_system_prompt(self, username: str, runtime_context: Optional[Dict[str, Any]] = None) -> str:
        """
        构建系统提示词

        Args:
            username: 用户名称
            runtime_context: 运行时业务上下文（可信状态数据）
        """
        # 主系统 Prompt
        main_prompt = get_prompt('客服对话系统', username=username)

        # 如果提供了运行时上下文，注入到 Prompt 中
        if runtime_context:
            context_str = self._format_runtime_context(runtime_context)
            main_prompt += f"\n\n{context_str}"

        return main_prompt

    def _format_runtime_context(self, context: Dict[str, Any]) -> str:
        """
        格式化运行时业务上下文为 Prompt 字符串

        实现 Grounded LLM：让模型基于可信状态生成回复
        """
        lines = ["\n## 运行时业务上下文（可信状态数据）\n"]

        # 会话摘要
        summary = context.get('conversation_summary')
        if summary:
            lines.append(f"### 会话摘要\n{summary}\n")

        # 当前活跃上下文
        known_context = context.get('known_context', {})
        if known_context:
            lines.append("### 当前活跃上下文")
            if known_context.get('active_order_id'):
                lines.append(f"- 活跃订单号: {known_context['active_order_id']}")
            if known_context.get('active_issue_type'):
                lines.append(f"- 当前问题类型: {known_context['active_issue_type']}")
            if known_context.get('last_resolution'):
                lines.append(f"- 上一步处理结果: {known_context['last_resolution']}")
            if known_context.get('pending_slot'):
                lines.append(f"- 待补充信息: {known_context['pending_slot']}")
            lines.append("")

        # 用户画像
        user_profile = context.get('known_user_profile', {})
        if user_profile:
            lines.append("### 用户画像")
            if user_profile.get('username'):
                lines.append(f"- 用户名: {user_profile['username']}")
            if user_profile.get('is_returning_user') is not None:
                lines.append(f"- 是否回访用户: {'是' if user_profile['is_returning_user'] else '否'}")
            lines.append("")

        # 知识库检索结果
        knowledge = context.get('knowledge_results', [])
        if knowledge:
            lines.append("### 知识库检索结果")
            for idx, item in enumerate(knowledge[:3], 1):  # 最多3条
                if item.get('hit'):
                    lines.append(f"{idx}. 问题: {item.get('question', 'N/A')}")
                    lines.append(f"   答案: {item.get('answer', 'N/A')}")
            lines.append("")

        # 可用工具及调用条件
        tools = context.get('available_tools', [])
        policy = context.get('tool_call_policy', {})
        if tools:
            lines.append("### 可用工具")
            for tool in tools:
                requires = policy.get(f"{tool}_requires", [])
                if requires:
                    lines.append(f"- {tool}: 需要参数 {requires}")
                else:
                    lines.append(f"- {tool}")
            lines.append("")

        # 重要规则
        lines.append("""### 重要规则
1. 你必须基于上述【运行时业务上下文】生成回复，不要编造数据
2. 如果用户询问订单状态，直接使用【当前活跃上下文】中的信息
3. 如果需要调用工具，检查所需参数是否已满足
4. 如果知识库已命中，优先使用知识库答案，不要自行发挥
5. 回复必须自然，不要暴露上述结构化数据给用户的痕迹
""")

        # 工具调用前置约束（安全红线）
        lines.append("""
### 工具调用前置约束（安全红线）

在调用任何工具前，必须先判断用户当前意图：

**意图类型与工具匹配规则：**
- **知识咨询**（规则、时效、原因）：禁止调用任何执行工具
- **进度查询**（现在呢/怎么样了/进度）：只能调用状态查询工具，禁止调用执行工具（如 refund_apply）
- **执行请求**（帮我处理/申请/办理）：参数齐全时才可调用执行工具，参数不齐时先补槽
- **规则解释**（为什么不行/什么原因）：禁止调用执行工具

**特殊约束（防误触）：**
- 如果【当前活跃上下文】中 active_order_id 已存在，不得重复追问订单号
- 如果 last_resolution 为 "refund_submitted_processing" 或 "success"，且用户询问"现在呢/进度呢"，只能查询状态，严禁再次调用 refund_apply
- 工具返回 system_error 时，必须解释为"系统处理异常"，禁止解释为用户不满足条件

**调用前自检清单：**
1. [ ] 用户明确是执行意图（不是咨询、不是查询）
2. [ ] 所需关键参数已齐全（如 order_id 已提供）
3. [ ] 不是重复执行（历史状态不是已提交/处理中）
4. [ ] 工具类型与意图匹配（查询 vs 执行不混用）

**违反以上任何一条，禁止调用工具，改用自然语言回复。**
""")

        return "\n".join(lines)

    async def chat(
        self,
        user_content: str,
        username: str = "用户",
        context: Optional[List[Dict[str, str]]] = None,
        runtime_context: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        """
        调用 LLM 进行对话

        Args:
            user_content: 用户输入内容
            username: 用户名称，用于个性化回复
            context: 历史对话上下文（消息列表）
            runtime_context: 运行时业务上下文（可信状态数据）

        Returns:
            LLMResponse: LLM 回复内容
        """
        # 如果没有配置 API Key，返回默认回复
        if not self.api_key:
            return LLMResponse(
                content=f"{username}，您好！很高兴为您服务。有什么我可以帮您的吗？",
                model="default"
            )

        messages = [
            {"role": "system", "content": self._build_system_prompt(username, runtime_context)},
        ]

        # 添加上下文
        if context:
            for msg in context[-5:]:  # 只取最近5轮
                messages.append(msg)

        messages.append({"role": "user", "content": user_content})

        try:
            print(f"[LLM] Sending request to {self.base_url}/chat/completions")
            print(f"[LLM] Model: {self.model}, Messages: {messages}")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(),
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 500
                    }
                )
                response.raise_for_status()
                data = response.json()
                print(f"[LLM] Response received: {data}")

                return LLMResponse(
                    content=data["choices"][0]["message"]["content"],
                    model=data.get("model", self.model),
                    usage=data.get("usage")
                )

        except httpx.HTTPError as e:
            print(f"[LLM] API error: {e}")
            if hasattr(e, 'response'):
                print(f"[LLM] Error response: {e.response.text}")
            # API 调用失败时返回默认回复
            return LLMResponse(
                content=f"{username}，您好！很高兴为您服务。有什么我可以帮您的吗？",
                model="fallback"
            )
        except Exception as e:
            print(f"[LLM] Service error: {e}")
            return LLMResponse(
                content=f"{username}，您好！很高兴为您服务。有什么我可以帮您的吗？",
                model="fallback"
            )

    async def generate_greeting(self, username: str) -> str:
        """生成首问问候语"""
        if not self.api_key:
            return f"你好，{username}，我是你的智能客服助手。你可以直接告诉我遇到的问题，比如订单、物流、退款或售后规则，我来帮你看看。"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(),
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": get_prompt('首问问候语生成', username=username)},
                            {"role": "user", "content": "请生成首问问候语"}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 100
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]

        except Exception:
            # 失败时使用默认问候语
            return f"你好，{username}，我是你的智能客服助手。你可以直接告诉我遇到的问题，比如订单、物流、退款或售后规则，我来帮你看看。"
