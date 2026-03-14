"""
评测器模块 - 实现三层评测体系
"""
import json
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class EvalResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"


@dataclass
class EvaluationScore:
    """评测分数"""
    rule_based_pass: bool = False
    llm_judge_pass: bool = False
    state_flow_pass: bool = False
    overall_pass: bool = False
    score: int = 0  # 1-5
    violations: List[str] = field(default_factory=list)
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class RuleBasedEvaluator:
    """规则评测器 - 基于关键词和规则的快速评测"""

    def evaluate(
        self,
        bot_reply: str,
        expected_keywords: Dict[str, List[str]],
        forbidden_keywords: Dict[str, List[str]],
        pass_criteria: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """
        执行规则评测

        Args:
            bot_reply: 机器人回复内容
            expected_keywords: 期望关键词配置 {any_of: [...], all_of: [...]}
            forbidden_keywords: 禁止关键词配置 {any_of: [...]}
            pass_criteria: 通过标准 {must_have: [...], must_not_have: [...]}

        Returns:
            评测结果
        """
        violations = []
        checks_passed = []

        # 检查期望关键词 (any_of - 至少命中一个)
        # 注意：如果关键词是抽象概念（长度>10），可能不是字面匹配，而是语义匹配，此时放宽检查
        if expected_keywords.get("any_of"):
            matched = any(kw in bot_reply for kw in expected_keywords["any_of"])
            if not matched:
                # 如果关键词都是长句（抽象概念），则由 LLM 评测器处理，规则层不强制
                all_abstract = all(len(kw) > 10 for kw in expected_keywords["any_of"])
                if not all_abstract:
                    violations.append(f"未命中任何期望关键词: {expected_keywords['any_of']}")
            else:
                matched_kws = [kw for kw in expected_keywords["any_of"] if kw in bot_reply]
                checks_passed.append(f"命中期望关键词: {matched_kws}")

        # 检查期望关键词 (all_of - 必须全部命中)
        if expected_keywords.get("all_of"):
            missing = [kw for kw in expected_keywords["all_of"] if kw not in bot_reply]
            if missing:
                violations.append(f"缺失必须关键词: {missing}")
            else:
                checks_passed.append(f"全部必须关键词已命中")

        # 检查禁止关键词
        if forbidden_keywords.get("any_of"):
            found_forbidden = [kw for kw in forbidden_keywords["any_of"] if kw in bot_reply]
            if found_forbidden:
                violations.append(f"出现禁止关键词: {found_forbidden}")
            else:
                checks_passed.append("未出现禁止关键词")

        # 检查通过标准 (must_have) - 这些是抽象概念，主要由 LLM 评测器处理
        # 规则层只检查是否包含明显的禁止模式
        if pass_criteria.get("must_not_have"):
            for criterion in pass_criteria["must_not_have"]:
                # 只对明显的关键词进行检查
                if len(criterion) > 5 and criterion.lower() in bot_reply.lower():
                    violations.append(f"违反禁止标准: {criterion}")

        return {
            "pass": len(violations) == 0,
            "violations": violations,
            "checks_passed": checks_passed,
            "score": 5 if len(violations) == 0 else max(1, 5 - len(violations))
        }


class LLMJudgeEvaluator:
    """LLM 评审器 - 使用大模型进行智能评测"""

    def __init__(self, llm_service):
        self.llm_service = llm_service

    async def evaluate(
        self,
        objective: str,
        steps: List[Dict[str, Any]],
        bot_reply: str,
        pass_criteria: Dict[str, List[str]],
        forbidden_keywords: Dict[str, List[str]],
        judge_prompt: str
    ) -> Dict[str, Any]:
        """
        使用 LLM 进行智能评测

        Args:
            objective: 测试目标
            steps: 测试步骤
            bot_reply: 机器人实际回复
            pass_criteria: 通过标准
            forbidden_keywords: 禁止关键词
            judge_prompt: LLM 评审提示词

        Returns:
            评测结果 JSON
        """
        # 构建评审提示
        evaluation_prompt = self._build_judge_prompt(
            objective=objective,
            steps=steps,
            bot_reply=bot_reply,
            pass_criteria=pass_criteria,
            forbidden_keywords=forbidden_keywords,
            judge_prompt=judge_prompt
        )

        try:
            response = await self.llm_service.chat(
                user_content=evaluation_prompt,
                username="test_judge",
                context=None
            )

            # 解析 LLM 返回的 JSON
            result = self._parse_judge_response(response.content)
            return result

        except Exception as e:
            print(f"[LLMJudge] Evaluation failed: {e}")
            return {
                "pass": False,
                "score": 1,
                "violations": [f"LLM 评测失败: {str(e)}"],
                "reason": "评测过程异常"
            }

    def _build_judge_prompt(
        self,
        objective: str,
        steps: List[Dict[str, Any]],
        bot_reply: str,
        pass_criteria: Dict[str, List[str]],
        forbidden_keywords: Dict[str, List[str]],
        judge_prompt: str
    ) -> str:
        """构建评审提示"""

        # 构建步骤描述 - 包含完整的对话流程
        steps_desc = []
        bot_reply_lines = bot_reply.split('\n') if bot_reply else []
        bot_reply_idx = 0

        for step in steps:
            role = step.get("role", "unknown")
            if role == "user":
                steps_desc.append(f"用户: {step.get('text', '')}")
            elif role == "bot":
                # 获取对应的实际机器人回复
                actual_reply = ""
                if bot_reply_idx < len(bot_reply_lines):
                    # 提取行号后的内容 (格式: "1. 回复内容")
                    line = bot_reply_lines[bot_reply_idx]
                    if ". " in line:
                        actual_reply = line.split(". ", 1)[1]
                    else:
                        actual_reply = line
                    bot_reply_idx += 1
                exp = step.get("expected_behavior", [])
                steps_desc.append(f"机器人预期: {exp}")
                if actual_reply:
                    steps_desc.append(f"机器人实际: {actual_reply}")

        prompt = f"""你是一个电商客服机器人体验测试评审器。
请根据以下信息进行评估。

## 测试目标
{objective}

## 测试步骤（含实际回复）
{chr(10).join(steps_desc)}

## 完整机器人回复记录
{bot_reply}

## 通过标准
必须包含: {pass_criteria.get('must_have', [])}
必须不包含: {pass_criteria.get('must_not_have', [])}

## 禁止关键词
{forbidden_keywords.get('any_of', [])}

## 评审重点
{judge_prompt}

## 输出要求
请输出以下 JSON 格式：
{{
    "pass": true/false,
    "score": 1-5,
    "intent_correct": true/false,
    "context_kept": true/false,
    "no_repeated_question": true/false,
    "action_boundary_correct": true/false,
    "result_explained_clearly": true/false,
    "next_step_guided": true/false,
    "fallback_reasonable": true/false,
    "history_continuity": true/false,
    "reference_resolution_correct": true/false,
    "query_vs_action_distinct": true/false,
    "continuity_score": 1-5,
    "violations": [],
    "reason": "简要说明通过或失败的原因"
}}

只输出 JSON，不要其他内容。"""

        return prompt

    def _parse_judge_response(self, content: str) -> Dict[str, Any]:
        """解析 LLM 评审响应"""
        try:
            # 尝试直接解析 JSON
            result = json.loads(content)
            return self._normalize_result(result)
        except json.JSONDecodeError:
            # 尝试从文本中提取 JSON
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    return self._normalize_result(result)
                except json.JSONDecodeError:
                    pass

            # 解析失败，返回默认结果
            return {
                "pass": False,
                "score": 1,
                "violations": ["无法解析 LLM 评审结果"],
                "reason": content[:100]
            }

    def _normalize_result(self, result: Dict) -> Dict[str, Any]:
        """规范化评审结果"""
        return {
            "pass": bool(result.get("pass", False)),
            "score": int(result.get("score", 1)),
            "intent_correct": bool(result.get("intent_correct", False)),
            "context_kept": bool(result.get("context_kept", False)),
            "no_repeated_question": bool(result.get("no_repeated_question", False)),
            "action_boundary_correct": bool(result.get("action_boundary_correct", False)),
            "result_explained_clearly": bool(result.get("result_explained_clearly", False)),
            "next_step_guided": bool(result.get("next_step_guided", False)),
            "fallback_reasonable": bool(result.get("fallback_reasonable", False)),
            "history_continuity": bool(result.get("history_continuity", False)),
            "reference_resolution_correct": bool(result.get("reference_resolution_correct", False)),
            "query_vs_action_distinct": bool(result.get("query_vs_action_distinct", False)),
            "continuity_score": int(result.get("continuity_score", 1)),
            "violations": result.get("violations", []),
            "reason": result.get("reason", "")
        }


class StateFlowEvaluator:
    """状态流评测器 - 检查意图、工具触发、上下文保持"""

    def evaluate(
        self,
        session_state: Dict[str, Any],
        expected_intent: Optional[str],
        triggered_tools: List[str],
        expected_tools: List[str],
        forbidden_tools: List[str],
        context_checks: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行状态流评测

        Args:
            session_state: 会话状态
            expected_intent: 期望意图
            triggered_tools: 实际触发的工具
            expected_tools: 期望触发的工具
            forbidden_tools: 禁止触发的工具
            context_checks: 上下文检查配置

        Returns:
            评测结果
        """
        violations = []
        checks_passed = []

        # 检查意图正确性
        actual_intent = session_state.get("current_intent")
        if expected_intent and actual_intent != expected_intent:
            violations.append(f"意图不匹配: 期望 {expected_intent}, 实际 {actual_intent}")
        elif expected_intent:
            checks_passed.append(f"意图正确: {actual_intent}")

        # 检查工具触发
        # 期望工具必须触发
        for tool in expected_tools:
            if tool not in triggered_tools:
                violations.append(f"未触发期望工具: {tool}")
            else:
                checks_passed.append(f"已触发工具: {tool}")

        # 禁止工具不能触发
        for tool in forbidden_tools:
            if tool in triggered_tools:
                violations.append(f"错误触发了禁止工具: {tool}")
            else:
                checks_passed.append(f"未触发禁止工具: {tool}")

        # 检查上下文保持
        if context_checks.get("active_order_id"):
            expected_order = context_checks["active_order_id"]
            actual_order = session_state.get("active_order_id")
            if actual_order != expected_order:
                violations.append(f"订单号上下文丢失: 期望 {expected_order}, 实际 {actual_order}")
            else:
                checks_passed.append(f"订单号上下文保持: {actual_order}")

        # 检查 pending_slot
        if context_checks.get("pending_slot") is not None:
            expected_slot = context_checks["pending_slot"]
            actual_slot = session_state.get("pending_slot")
            if actual_slot != expected_slot:
                violations.append(f"pending_slot 不匹配: 期望 {expected_slot}, 实际 {actual_slot}")
            else:
                checks_passed.append(f"pending_slot 正确: {actual_slot}")

        # 检查是否重复补槽
        if context_checks.get("no_repeated_question", False):
            # 检查历史中是否有重复问题
            history = session_state.get("history", [])
            questions_asked = [msg.get("text", "") for msg in history if msg.get("role") == "bot"]
            # 简单的重复检测：检查最近的追问是否与之前相同
            if len(questions_asked) >= 2:
                last_question = questions_asked[-1]
                prev_questions = questions_asked[:-1]
                if any(self._is_similar_question(last_question, pq) for pq in prev_questions):
                    violations.append("检测到重复追问")
                else:
                    checks_passed.append("无重复追问")

        # 检查话题承接
        if context_checks.get("topic_continuity"):
            if session_state.get("is_topic_shift"):
                violations.append("不应切换话题时应保持话题连续")
            else:
                checks_passed.append("话题保持连续")

        return {
            "pass": len(violations) == 0,
            "violations": violations,
            "checks_passed": checks_passed,
            "intent": actual_intent,
            "triggered_tools": triggered_tools,
            "score": 5 if len(violations) == 0 else max(1, 5 - len(violations))
        }

    def _is_similar_question(self, q1: str, q2: str) -> bool:
        """判断两个问题是否相似（简单实现）"""
        # 提取关键信息：订单号、问题类型等
        keywords = ["订单号", "问题类型", "诉求类型", "退款", "物流"]
        q1_kws = set(kw for kw in keywords if kw in q1)
        q2_kws = set(kw for kw in keywords if kw in q2)
        # 如果关键词集合相同，认为是相似问题
        return q1_kws == q2_kws and len(q1_kws) > 0
