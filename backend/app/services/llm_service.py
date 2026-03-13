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

    def _build_system_prompt(self, username: str) -> str:
        """构建系统提示词"""
        return f"""你是智能客服助手，正在为用户"{username}"提供服务。

你的职责：
1. 友好、专业地回答用户的售前、售后、物流、退款等问题
2. 用中文回复，语气亲切自然
3. 如果不确定答案，引导用户提供更多信息

回复要求：
- 开头要称呼用户，如"{username}，您好"
- 回答要简洁明了，控制在100字以内
- 如果是问候语，要热情回应"""

    async def chat(
        self,
        user_content: str,
        username: str = "用户",
        context: Optional[List[Dict[str, str]]] = None
    ) -> LLMResponse:
        """
        调用 LLM 进行对话

        Args:
            user_content: 用户输入内容
            username: 用户名称，用于个性化回复
            context: 历史对话上下文

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
            {"role": "system", "content": self._build_system_prompt(username)},
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
                            {"role": "system", "content": f"你是智能客服助手，为用户'{username}'提供服务。生成一句友好的首问问候语，不超过50字。"},
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
