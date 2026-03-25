import os
import chromadb
from datetime import datetime
from typing import List

from config import settings


class EpisodicMemoryManager:
    """
    RAG-based Episodic Memory Manager.
    负责将长期的日记事件和重要对话向量化存储，并支持语义检索。
    """

    def __init__(self, collection_name: str = "bg3_memories"):
        # 记忆数据库存储在本地，和 JSON 存档放在一起
        self.db_path = os.path.join(settings.SAVE_DIR, "chroma_db")
        os.makedirs(self.db_path, exist_ok=True)

        # 初始化 ChromaDB 客户端 (本地持久化模式)
        self.client = chromadb.PersistentClient(path=self.db_path)

        # 获取或创建 Collection
        self._collection_name = collection_name
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def clear_all_memories(self):
        """
        清空所有长期记忆 (硬重置)。
        直接删除当前的 Collection 并重新创建一个干净的。
        """
        try:
            self.client.delete_collection(self._collection_name)
            self.collection = self.client.create_collection(name=self._collection_name)
            print("💥 [系统] 长期记忆库 (ChromaDB) 已彻底清空！")
        except Exception as e:
            print(f"⚠️ 清空记忆失败: {e}")

    def add_memory(self, text: str, speaker: str = "system", metadata: dict = None):
        """
        写入一条新记忆。
        :param text: 记忆内容（如："玩家在晨曦时分将一瓶治疗药水强行塞给了莱埃泽尔"）
        """
        if not text.strip():
            return

        memory_id = f"mem_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        meta = metadata or {}
        meta["speaker"] = speaker
        meta["timestamp"] = datetime.now().isoformat()

        # ChromaDB 会自动将 text 转换为向量并存入
        self.collection.add(
            documents=[text],
            metadatas=[meta],
            ids=[memory_id],
        )
        print(f"🧠 [记忆凝结] {speaker} 的记忆已存入深层潜意识: {text[:30]}...")

    def retrieve_relevant_memories(self, query: str, top_k: int = 3) -> List[str]:
        """
        根据当前对话（Query），检索最相关的长期记忆。
        """
        if not query.strip():
            return []

        # 如果库里没东西，直接返回
        if self.collection.count() == 0:
            return []

        results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, self.collection.count()),
        )

        memories = []
        if results and results.get("documents") and results["documents"][0]:
            for doc in results["documents"][0]:
                memories.append(doc)

        return memories


# 单例模式，方便全局调用
episodic_memory = EpisodicMemoryManager()
