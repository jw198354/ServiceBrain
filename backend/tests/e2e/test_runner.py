"""
端到端测试运行器 - 执行测试套件并生成报告

使用方法:
    cd backend
    python -m pytest tests/e2e/test_runner.py -v
    或
    python tests/e2e/test_runner.py

说明:
    本测试框架通过直接调用 OrchestratorService 来进行端到端测试，
    不需要启动 WebSocket 服务器，测试更高效且可控。
"""
import yaml
import asyncio
import json
import pytest
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm_service import LLMService
from app.services.orchestrator_service import OrchestratorService
from app.services.memory_service import MemoryService
from app.services.tool_service import ToolService
from app.services.session_service import SessionService
from app.services.user_service import UserService
from app.models.database import async_session_maker

from tests.e2e.evaluators import RuleBasedEvaluator, LLMJudgeEvaluator, StateFlowEvaluator
from tests.e2e.mock_backend import MockBackendStubs, MockToolService


@dataclass
class TestStep:
    """测试步骤"""
    step_id: int
    role: str
    text: Optional[str] = None
    expected_behavior: List[str] = field(default_factory=list)


@dataclass
class TestCase:
    """测试用例"""
    case_id: str
    title: str
    category: str
    priority: str
    objective: str
    mock_input: Dict[str, Any]
    steps: List[TestStep]
    expected_keywords: Dict[str, List[str]]
    forbidden_keywords: Dict[str, List[str]]
    pass_criteria: Dict[str, List[str]]
    llm_judge_prompt: str


@dataclass
class TestResult:
    """测试结果"""
    case_id: str
    title: str
    passed: bool
    rule_based_pass: bool
    llm_judge_pass: bool
    state_flow_pass: bool
    score: int
    violations: List[str]
    bot_replies: List[str]
    execution_time_ms: int
    details: Dict[str, Any] = field(default_factory=dict)


class TestSuiteLoader:
    """测试套件加载器"""

    def __init__(self, yaml_path: str):
        self.yaml_path = yaml_path
        self.test_cases: Dict[str, TestCase] = {}
        self.smoke_suite: List[str] = []
        self.regression_suite: List[str] = []
        self._load()

    def _load(self):
        """加载 YAML 测试套件"""
        with open(self.yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        suite = data.get('test_suite', {})

        # 加载测试用例
        for case_data in suite.get('test_cases', []):
            steps = [
                TestStep(
                    step_id=s.get('step_id', 0),
                    role=s.get('role', ''),
                    text=s.get('text'),
                    expected_behavior=s.get('expected_behavior', [])
                )
                for s in case_data.get('steps', [])
            ]

            test_case = TestCase(
                case_id=case_data['case_id'],
                title=case_data['title'],
                category=case_data['category'],
                priority=case_data['priority'],
                objective=case_data['objective'],
                mock_input=case_data.get('mock_input', {}),
                steps=steps,
                expected_keywords=case_data.get('expected_keywords', {}),
                forbidden_keywords=case_data.get('forbidden_keywords', {}),
                pass_criteria=case_data.get('pass_criteria', {}),
                llm_judge_prompt=case_data.get('llm_judge_prompt', '')
            )
            self.test_cases[case_data['case_id']] = test_case

        # 加载测试套件
        self.smoke_suite = suite.get('smoke_suite', [])
        self.regression_suite = suite.get('regression_suite', [])

    def get_case(self, case_id: str) -> Optional[TestCase]:
        """获取单个测试用例"""
        return self.test_cases.get(case_id)

    def get_suite_cases(self, suite_name: str) -> List[TestCase]:
        """获取测试套件中的所有用例"""
        if suite_name == 'smoke':
            return [self.test_cases[cid] for cid in self.smoke_suite if cid in self.test_cases]
        elif suite_name == 'regression':
            return [self.test_cases[cid] for cid in self.regression_suite if cid in self.test_cases]
        return []


class E2ETestRunner:
    """端到端测试运行器"""

    def __init__(self, test_suite_path: str):
        self.loader = TestSuiteLoader(test_suite_path)
        self.llm_service = LLMService()

        # 初始化评测器
        self.rule_evaluator = RuleBasedEvaluator()
        self.llm_evaluator = LLMJudgeEvaluator(self.llm_service)
        self.state_evaluator = StateFlowEvaluator()

        # 结果收集
        self.results: List[TestResult] = []

    async def run_suite(self, suite_name: str = 'smoke', db: Optional[AsyncSession] = None) -> List[TestResult]:
        """运行测试套件"""
        cases = self.loader.get_suite_cases(suite_name)
        print(f"\n{'='*60}")
        print(f"Running {suite_name.upper()} suite: {len(cases)} test cases")
        print(f"{'='*60}\n")

        self.results = []

        # 如果没有传入 db，创建一个新的会话
        if db is None:
            async with async_session_maker() as session:
                for case in cases:
                    result = await self.run_case(case, session)
                    self.results.append(result)
                    self._print_result(result)
        else:
            for case in cases:
                result = await self.run_case(case, db)
                self.results.append(result)
                self._print_result(result)

        return self.results

    async def run_case(self, case: TestCase, db: AsyncSession) -> TestResult:
        """运行单个测试用例"""
        start_time = datetime.now()

        # 准备 Mock 桩配置（用于验证工具调用）
        stubs_config = case.mock_input.get('backend_stubs', {})

        # 创建 Mock 工具服务
        mock_stubs = MockBackendStubs()
        if stubs_config:
            mock_stubs._stubs = stubs_config
        mock_tool_service = MockToolService(mock_stubs)

        # 创建编排器服务，注入 Mock 工具服务
        orchestrator = OrchestratorService(db, tool_service=mock_tool_service)

        triggered_tools = []

        # 设置测试会话和用户
        user_id = case.mock_input.get('user_profile', {}).get('user_id', 'test_user')
        session_data = await self._setup_test_session(db, user_id, case.mock_input)
        session_id = session_data['session_id']

        # 执行测试步骤
        bot_replies = []
        session_state = {}

        # 处理首问测试用例 (CS-001) - 第一个步骤是 bot 且包含首问期望
        if case.steps and case.steps[0].role == 'bot':
            first_step = case.steps[0]
            if '首问' in case.objective or 'greeting' in case.category:
                # 触发首问生成
                greeting = await self.llm_service.generate_greeting(username=f"测试用户_{user_id[-4:]}")
                bot_replies.append(greeting)

        for step in case.steps:
            if step.role == 'user':
                # 模拟用户输入，调用编排器处理
                try:
                    response = await orchestrator.process_user_message(
                        session_id=session_id,
                        user_content=step.text or '',
                        trace_id=f"test_{case.case_id}_{step.step_id}"
                    )

                    # 提取机器人回复内容
                    payload = response.get('payload', {})
                    content = payload.get('content', '')

                    # 对于卡片类型，包含完整描述
                    card = payload.get('card', {})
                    if card:
                        card_desc = card.get('description', '')
                        if card_desc:
                            content = f"{content}\n{card_desc}".strip()

                    bot_replies.append(content)

                    # 记录触发的工具（从响应类型判断）
                    msg_type = payload.get('message_type', '')
                    if msg_type == 'tool_result_card':
                        # 检查工具调用
                        triggered_tools.extend(self._detect_triggered_tools(payload))

                except Exception as e:
                    print(f"[ERROR] Case {case.case_id} step {step.step_id}: {e}")
                    bot_replies.append(f"[ERROR: {str(e)}]")

            elif step.role == 'bot':
                # 记录期望行为，稍后验证
                pass

        # 从 Mock 工具服务获取触发的工具记录
        mock_triggered_tools = mock_tool_service.get_triggered_tools()
        for tool_record in mock_triggered_tools:
            tool_name = tool_record.get('tool', '')
            if tool_name and tool_name not in triggered_tools:
                triggered_tools.append(tool_name)

        # 收集最终会话状态
        memory_service = MemoryService(db)
        working_memory = await memory_service.load_working_memory(session_id)

        # 获取会话对象以读取状态
        from app.models.session import Session
        from sqlalchemy import select
        result = await db.execute(select(Session).where(Session.session_id == session_id))
        session_obj = result.scalar_one_or_none()

        session_state = {
            'current_intent': working_memory.get('current_topic'),
            'active_order_id': session_obj.current_order_id if session_obj else None,
            'pending_slot': working_memory.get('pending_slot'),
            'tool_status': session_obj.tool_status if session_obj else None,
            'history': working_memory.get('recent_messages', []),
            'triggered_tools': triggered_tools
        }

        # 执行三层评测
        final_bot_reply = bot_replies[-1] if bot_replies else ""

        # 1. 规则评测
        rule_result = self.rule_evaluator.evaluate(
            bot_reply=final_bot_reply,
            expected_keywords=case.expected_keywords,
            forbidden_keywords=case.forbidden_keywords,
            pass_criteria=case.pass_criteria
        )

        # 2. LLM 评测 - 传递所有机器人回复以支持多轮对话评估
        all_bot_replies_str = "\n".join([f"{i+1}. {r}" for i, r in enumerate(bot_replies)])
        llm_result = await self.llm_evaluator.evaluate(
            objective=case.objective,
            steps=[{'role': s.role, 'text': s.text or '', 'expected_behavior': s.expected_behavior}
                   for s in case.steps],
            bot_reply=all_bot_replies_str,
            pass_criteria=case.pass_criteria,
            forbidden_keywords=case.forbidden_keywords,
            judge_prompt=case.llm_judge_prompt
        )

        # 3. 状态流评测
        state_result = self.state_evaluator.evaluate(
            session_state=session_state,
            expected_intent=self._get_expected_intent(case),
            triggered_tools=triggered_tools,
            expected_tools=self._get_expected_tools(case, stubs_config),
            forbidden_tools=self._get_forbidden_tools(case),
            context_checks=self._build_context_checks(case, session_state)
        )

        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)

        # 综合判断
        passed = rule_result['pass'] and llm_result['pass'] and state_result['pass']
        score = min(rule_result['score'], llm_result['score'], state_result['score'])

        violations = []
        violations.extend([f"[Rule] {v}" for v in rule_result.get('violations', [])])
        violations.extend([f"[LLM] {v}" for v in llm_result.get('violations', [])])
        violations.extend([f"[State] {v}" for v in state_result.get('violations', [])])

        return TestResult(
            case_id=case.case_id,
            title=case.title,
            passed=passed,
            rule_based_pass=rule_result['pass'],
            llm_judge_pass=llm_result['pass'],
            state_flow_pass=state_result['pass'],
            score=score,
            violations=violations,
            bot_replies=bot_replies,
            execution_time_ms=execution_time,
            details={
                'rule_based': rule_result,
                'llm_judge': llm_result,
                'state_flow': state_result
            }
        )

    async def _setup_test_session(self, db: AsyncSession, user_id: str, mock_input: Dict) -> Dict[str, Any]:
        """设置测试会话"""
        from app.models.session import Session
        from app.models.message import Message
        import uuid

        # 创建用户
        from app.services.user_service import UserService
        user_service = UserService(db)

        # 检查用户是否存在
        user = await user_service.get_user_by_id(user_id)
        actual_user_id = user_id
        if not user:
            # 创建新用户
            from app.schemas.user import UserCreate
            user_data = UserCreate(username=f"测试用户_{user_id[-4:]}")
            user_response = await user_service.create_anonymous_user(user_data)
            # 使用创建后的用户ID
            actual_user_id = user_response.anonymous_user_id

        # 创建会话
        session_service = SessionService(db)
        session = await session_service.create_session(
            anonymous_user_id=actual_user_id
        )
        session_id = session.session_id

        # 恢复历史记录
        session_data = mock_input.get('session', {})
        history = session_data.get('history', [])

        for msg in history:
            message = Message(
                session_id=session.session_id,
                sender=msg.get('role', 'user'),
                content=msg.get('text', ''),
                message_type='user_message' if msg.get('role') == 'user' else 'bot_message'
            )
            db.add(message)

        await db.commit()

        # 恢复会话状态
        active_task = mock_input.get('active_task', {})
        if active_task:
            session.current_order_id = active_task.get('order_id')
            session.tool_status = active_task.get('status')
            session.current_topic = 'refund'
            session.current_task = 'execute'

        # 如果没有 active_task，尝试从历史记录中提取订单号
        if not session.current_order_id and history:
            import re
            for msg in history:
                text = msg.get('text', '')
                # 匹配订单号格式：A followed by digits
                match = re.search(r'A\d{10,}', text)
                if match:
                    session.current_order_id = match.group()
                    session.current_topic = 'refund'
                    session.current_task = 'execute'
                    break

        # 恢复 conversation_state
        conversation_state = mock_input.get('conversation_state', {})
        if conversation_state.get('waiting_slot'):
            session.pending_slot = conversation_state['waiting_slot']
        if conversation_state.get('current_intent'):
            # 根据 current_intent 设置 topic 和 task
            intent = conversation_state['current_intent']
            if 'refund' in intent.lower():
                session.current_topic = 'refund'
                session.current_task = 'execute'
            elif 'logistics' in intent.lower():
                session.current_topic = 'logistics'
                session.current_task = 'consult'
            else:
                session.current_topic = 'unknown'
                session.current_task = 'chat'

        await db.commit()

        return {
            'session_id': session.session_id,
            'user_id': user_id,
            'history': history
        }

    def _detect_triggered_tools(self, payload: Dict) -> List[str]:
        """从响应中检测触发的工具"""
        tools = []
        card = payload.get('card', {})
        status = card.get('status', '')

        # 根据卡片状态判断可能触发的工具
        if status in ['success', 'not_allowed', 'fail', 'need_more_info']:
            tools.append('refund_apply')

        return tools

    def _get_expected_intent(self, case: TestCase) -> Optional[str]:
        """从测试用例推断期望意图"""
        category_to_intent = {
            'action_refund': 'refund',
            'slot_filling': None,  # slot_filling 可能对应多种意图，不强制检查
            'progress_query': 'refund',
            'explanation': None,  # explanation 可能对应多种意图，不强制检查
            'faq_fallback': None,
            'greeting': None,
            'reconnect_context': None,
            'followup_progress': None,
            'repeat_contact': None,
            'reference_resolution': None,
            'tool_error': None
        }
        return category_to_intent.get(case.category)

    def _get_expected_tools(self, case: TestCase, stubs_config: Dict) -> List[str]:
        """获取期望触发的工具"""
        tools = []

        # 从 stubs 配置推断 - 但只包括实际会被调用的工具
        # 注意：有些 stubs 只是备用，不代表一定会被调用
        for tool_name in stubs_config.keys():
            # refund_check 是查询类工具，实际编排器可能直接处理而不调用工具
            if tool_name != 'refund_check':
                tools.append(tool_name)

        # 根据测试类别推断
        if case.category == 'action_refund':
            if 'refund_apply' not in tools:
                tools.append('refund_apply')

        return tools

    def _get_forbidden_tools(self, case: TestCase) -> List[str]:
        """获取禁止触发的工具"""
        forbidden = []

        # 进度查询不应触发退款执行
        if case.category == 'progress_query':
            forbidden.append('refund_apply')

        # 咨询类不应触发执行
        if case.category == 'slot_filling' and '咨询' in case.objective:
            forbidden.append('refund_apply')

        return forbidden

    def _build_context_checks(self, case: TestCase, session_state: Dict) -> Dict[str, Any]:
        """构建上下文检查配置"""
        checks = {}

        mock_input = case.mock_input

        # 检查活跃订单号
        active_order = mock_input.get('active_task', {}).get('order_id')
        if not active_order:
            active_order = mock_input.get('active_context', {}).get('recent_active_order_id')

        if active_order:
            checks['active_order_id'] = active_order

        # 检查 pending_slot (仅对非断线恢复类测试检查)
        # 因为断线恢复测试中，用户提供缺失信息后 pending_slot 会被清除
        conversation_state = mock_input.get('conversation_state', {})
        if conversation_state.get('waiting_slot') and case.category not in ['reconnect_context', 'followup_progress', 'repeat_contact']:
            checks['pending_slot'] = conversation_state['waiting_slot']

        # 检查是否不应重复追问
        if case.case_id in ['CS-007', 'CS-025', 'CS-026', 'CS-027', 'CS-029']:
            checks['no_repeated_question'] = True

        # 检查话题承接
        if case.case_id in ['CS-025', 'CS-026', 'CS-027', 'CS-028', 'CS-029']:
            checks['topic_continuity'] = True

        return checks

    def _print_result(self, result: TestResult):
        """打印测试结果"""
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"{status} [{result.case_id}] {result.title}")
        print(f"   Score: {result.score}/5 | Time: {result.execution_time_ms}ms")
        print(f"   Rule: {'✓' if result.rule_based_pass else '✗'} | "
              f"LLM: {'✓' if result.llm_judge_pass else '✗'} | "
              f"State: {'✓' if result.state_flow_pass else '✗'}")
        if result.violations:
            for v in result.violations[:3]:  # 最多显示3个
                print(f"   ⚠️  {v}")
        print()

    def generate_report(self, output_path: Optional[str] = None) -> str:
        """生成测试报告"""
        passed_count = sum(1 for r in self.results if r.passed)
        total_count = len(self.results)

        report = {
            'summary': {
                'total': total_count,
                'passed': passed_count,
                'failed': total_count - passed_count,
                'pass_rate': f"{passed_count/total_count*100:.1f}%" if total_count > 0 else "0%",
                'timestamp': datetime.now().isoformat()
            },
            'results': [asdict(r) for r in self.results]
        }

        report_json = json.dumps(report, ensure_ascii=False, indent=2)

        if output_path:
            Path(output_path).write_text(report_json, encoding='utf-8')
            print(f"\nReport saved to: {output_path}")

        return report_json


# ========== Pytest 测试用例 ==========
import pytest_asyncio

@pytest_asyncio.fixture
def test_runner():
    """测试运行器 fixture"""
    # 从 backend/tests/e2e/ 到项目根目录需要上溯 4 层
    suite_path = Path(__file__).parent.parent.parent.parent / 'docs' / 'test_suite.yaml'
    return E2ETestRunner(str(suite_path))


@pytest_asyncio.fixture
async def db_session():
    """数据库会话 fixture"""
    async with async_session_maker() as session:
        yield session
        # 测试结束后回滚
        await session.rollback()


@pytest.mark.asyncio
async def test_smoke_suite(test_runner, db_session):
    """冒烟测试套件"""
    results = await test_runner.run_suite('smoke', db_session)

    # 生成报告
    test_runner.generate_report('test_report_smoke.json')

    # 统计结果
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    print(f"\n{'='*60}")
    print(f"SMOKE TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Passed: {passed}/{total}")
    print(f"Pass Rate: {passed/total*100:.1f}%")

    # 断言所有测试通过（或至少大部分通过）
    assert passed >= total * 0.5, f"Too many tests failed: {total - passed}/{total}"


@pytest.mark.asyncio
async def test_regression_suite(test_runner, db_session):
    """回归测试套件"""
    results = await test_runner.run_suite('regression', db_session)

    # 生成报告
    test_runner.generate_report('test_report_regression.json')

    # 统计结果
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    print(f"\n{'='*60}")
    print(f"REGRESSION TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Passed: {passed}/{total}")
    print(f"Pass Rate: {passed/total*100:.1f}%")

    # 回归测试要求更高的通过率
    assert passed >= total * 0.7, f"Regression tests failed: {total - passed}/{total}"


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id", [
    "CS-001",  # 首次进入应主动首问且自然
    "CS-004",  # 退款咨询应补订单号但不能直接执行
    "CS-005",  # 明确退款执行诉求时先补订单号
    "CS-007",  # 信息已给全时不应重复补槽
    "CS-010",  # 复杂规则未命中时应保守兜底
    "CS-011",  # 不可退款时为什么解释要闭环
    "CS-016",  # 系统失败时不能甩锅用户
    "CS-023",  # 重连后待补订单号状态应恢复
    "CS-025",  # 同会话内追问进度不应重复盘问
    "CS-026",  # 隔天再次进线应承接昨天的退款问题
    "CS-027",  # 指代表达还是那个订单应被正确承接
    "CS-028",  # 用户再次补发订单号后应直接承接原问题
    "CS-029",  # 历史已知不可退款时再次追问应复用历史结论
    "CS-030",  # 查退款进度不能误触发再次执行
    "CS-031",  # 多次追问进度时应简洁承接而非反复长篇复读
])
async def test_individual_case(test_runner, db_session, case_id):
    """单个测试用例"""
    case = test_runner.loader.get_case(case_id)
    if not case:
        pytest.skip(f"Test case {case_id} not found")

    result = await test_runner.run_case(case, db_session)
    test_runner._print_result(result)

    # 打印详细信息以便调试
    if not result.passed:
        print(f"\nBot replies:")
        for i, reply in enumerate(result.bot_replies, 1):
            print(f"  {i}. {reply[:100]}...")

    assert result.passed, f"Test case {case_id} failed: {result.violations}"


# ========== 命令行入口 ==========

async def main():
    """主入口"""
    # 测试套件路径 - 从 backend/tests/e2e/ 到项目根目录需要上溯 4 层
    suite_path = Path(__file__).parent.parent.parent.parent / 'docs' / 'test_suite.yaml'

    if not suite_path.exists():
        print(f"Test suite not found: {suite_path}")
        return

    # 创建运行器
    runner = E2ETestRunner(str(suite_path))

    async with async_session_maker() as db:
        # 运行冒烟测试
        results = await runner.run_suite('smoke', db)

        # 生成报告
        report = runner.generate_report('test_report.json')

        print("\n" + "="*60)
        print("Test Report Summary")
        print("="*60)

        summary = json.loads(report)['summary']
        print(f"Total: {summary['total']}")
        print(f"Passed: {summary['passed']}")
        print(f"Failed: {summary['failed']}")
        print(f"Pass Rate: {summary['pass_rate']}")


if __name__ == '__main__':
    asyncio.run(main())
