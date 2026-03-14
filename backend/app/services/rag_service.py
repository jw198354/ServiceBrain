"""
RAG 服务 - 知识检索与回答生成

负责：
- 文档向量化与索引
- 相似度检索
- 知识回答生成
"""
from typing import List, Optional, Dict, Any
import os

from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Chroma
from langchain.text_splitter import CharacterTextSplitter
from langchain.docstore.document import Document

from app.services.llm_service import LLMService


KNOWLEDGE_BASE_PROMPT = """你是智能客服助手，基于以下知识库内容回答用户问题。

用户问题: {question}

相关知识点:
{context}

请根据以上知识点，用亲切、口语化的客服语气回答用户。
要求:
1. 先直接给出答案
2. 简要解释原因
3. 语气友好自然
4. 如果不确定，引导用户提供更多信息
5. 回答控制在 150 字以内
"""


class RAGService:
    """RAG 知识检索服务"""
    
    def __init__(self, persist_directory: str = "./data/chroma_db"):
        """
        初始化 RAG 服务
        
        Args:
            persist_directory: 向量数据库持久化目录
        """
        self.persist_directory = persist_directory
        self.embeddings = None
        self.vectorstore = None
        self.llm_service = None
        
        # 延迟初始化（避免在导入时初始化）
        self._initialized = False
    
    def _initialize(self):
        """延迟初始化"""
        if self._initialized:
            return
        
        try:
            # 使用 OpenAI 兼容的 embedding API
            self.embeddings = OpenAIEmbeddings(
                openai_api_base=os.getenv("EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                openai_api_key=os.getenv("EMBEDDING_API_KEY", ""),
                model=os.getenv("EMBEDDING_MODEL", "text-embedding-v2")
            )
            
            # 加载或创建向量数据库
            if os.path.exists(self.persist_directory):
                self.vectorstore = Chroma(
                    persist_directory=self.persist_directory,
                    embedding_function=self.embeddings
                )
                print(f"[RAGService] 加载已有向量数据库: {self.persist_directory}")
            else:
                self.vectorstore = None
                print(f"[RAGService] 向量数据库不存在，等待初始化: {self.persist_directory}")
            
            self.llm_service = LLMService()
            self._initialized = True
            
        except Exception as e:
            print(f"[RAGService] 初始化失败: {e}")
            self._initialized = False
    
    async def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        添加文档到知识库
        
        Args:
            documents: 文档内容列表
            metadatas: 文档元数据列表
            
        Returns:
            是否成功
        """
        self._initialize()
        
        if not self.embeddings:
            print("[RAGService] Embedding 服务未初始化")
            return False
        
        try:
            # 文本切分
            text_splitter = CharacterTextSplitter(
                chunk_size=500,
                chunk_overlap=50,
                separator="\n"
            )
            
            docs = []
            for i, text in enumerate(documents):
                chunks = text_splitter.split_text(text)
                for chunk in chunks:
                    metadata = metadatas[i] if metadatas and i < len(metadatas) else {}
                    docs.append(Document(page_content=chunk, metadata=metadata))
            
            # 添加到向量数据库
            if self.vectorstore is None:
                self.vectorstore = Chroma.from_documents(
                    documents=docs,
                    embedding=self.embeddings,
                    persist_directory=self.persist_directory
                )
            else:
                self.vectorstore.add_documents(docs)
            
            # 持久化
            self.vectorstore.persist()
            print(f"[RAGService] 成功添加 {len(docs)} 个文档片段")
            return True
            
        except Exception as e:
            print(f"[RAGService] 添加文档失败: {e}")
            return False
    
    async def retrieve(
        self,
        query: str,
        top_k: int = 3,
        score_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        检索相关知识
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            score_threshold: 相似度阈值
            
        Returns:
            检索结果列表
        """
        self._initialize()
        
        if not self.vectorstore:
            print("[RAGService] 向量数据库未初始化")
            return []
        
        try:
            # 相似度搜索
            results = self.vectorstore.similarity_search_with_score(query, k=top_k)
            
            # 过滤低相似度结果
            filtered_results = []
            for doc, score in results:
                # 注意：Chroma 返回的距离分数越低越相似
                # 转换为相似度分数（0-1，越高越相似）
                similarity = 1 - score
                
                if similarity >= score_threshold:
                    filtered_results.append({
                        "content": doc.page_content,
                        "metadata": doc.metadata,
                        "similarity": similarity
                    })
            
            print(f"[RAGService] 检索到 {len(filtered_results)} 条相关知识")
            return filtered_results
            
        except Exception as e:
            print(f"[RAGService] 检索失败: {e}")
            return []
    
    async def answer(
        self,
        question: str,
        username: str = "用户",
        top_k: int = 3
    ) -> Dict[str, Any]:
        """
        基于知识库回答问题
        
        Args:
            question: 用户问题
            username: 用户名
            top_k: 检索结果数量
            
        Returns:
            回答结果，包含 answer 和 sources
        """
        self._initialize()
        
        # 1. 检索相关知识
        retrieved_docs = await self.retrieve(question, top_k=top_k)
        
        if not retrieved_docs:
            return {
                "answer": None,
                "sources": [],
                "hit": False,
                "message": "未找到相关知识"
            }
        
        # 2. 构建上下文
        context = "\n\n".join([
            f"[{i+1}] {doc['content']}"
            for i, doc in enumerate(retrieved_docs)
        ])
        
        # 3. 生成回答
        prompt = KNOWLEDGE_BASE_PROMPT.format(
            question=question,
            context=context
        )
        
        try:
            response = await self.llm_service.chat(
                user_content=prompt,
                username=username,
                context=None
            )
            
            return {
                "answer": response.content,
                "sources": retrieved_docs,
                "hit": True,
                "message": "知识检索成功"
            }
            
        except Exception as e:
            print(f"[RAGService] 生成回答失败: {e}")
            return {
                "answer": None,
                "sources": retrieved_docs,
                "hit": True,
                "message": f"生成回答失败: {e}"
            }
    
    async def initialize_knowledge_base(self) -> bool:
        """
        初始化默认知识库
        
        添加电商客服常见知识文档
        """
        default_documents = [
            # 退款规则
            """退款规则说明：
1. 签收后 7 天内可申请退款
2. 商品需保持完好，不影响二次销售
3. 特殊商品（生鲜、定制等）不支持无理由退款
4. 退款申请后 1-3 个工作日处理
5. 退款原路返回，到账时间视银行而定，一般为 3-7 个工作日
6. 超过 7 天的订单需要联系客服人工处理""",
            
            # 运费规则
            """运费规则说明：
1. 全场满 99 元包邮（偏远地区除外）
2. 不满 99 元收取 6 元运费
3. 新疆、西藏、内蒙古等偏远地区满 199 元包邮
4. 退货时：质量问题商家承担运费，非质量问题用户承担运费
5. 换货时：质量问题商家承担双向运费""",
            
            # 发货规则
            """发货规则说明：
1. 一般下单后 24 小时内发货
2. 预售商品按预售时间发货
3. 节假日可能延迟，请耐心等待
4. 发货后会通过短信和 APP 推送通知
5. 如需修改地址，请在发货前联系客服
6. 已发货订单无法修改地址""",
            
            # 售后服务
            """售后服务说明：
1. 支持 7 天无理由退换货
2. 质量问题 30 天内可退换
3. 商品问题请提供照片凭证
4. 售后申请路径：我的订单 -> 申请售后
5. 售后处理时间：1-3 个工作日
6. 紧急问题可联系在线客服加急处理""",
            
            # 账户安全
            """账户安全说明：
1. 请妥善保管账户密码
2. 不要向他人透露验证码
3. 发现异常登录请及时修改密码
4. 绑定手机号可提升账户安全
5. 大额交易建议开启支付密码"""
        ]
        
        metadatas = [
            {"category": "退款", "topic": "refund"},
            {"category": "运费", "topic": "shipping"},
            {"category": "发货", "topic": "delivery"},
            {"category": "售后", "topic": "aftersale"},
            {"category": "账户", "topic": "account"}
        ]
        
        return await self.add_documents(default_documents, metadatas)
