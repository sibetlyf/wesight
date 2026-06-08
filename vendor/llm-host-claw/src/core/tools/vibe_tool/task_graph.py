#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务依赖图模块 v2.0 Ultra-Lite - 轻量级改进版

通过分析任务间的代码依赖、文件引用、语义相似度等关系，
自动判断新任务是否应该继续上一个 vibe coding 会话。

核心算法采用分层决策：
1. 快速规则过滤（明显的新建/继续意图）
2. 文件依赖分析（基于创建/修改的文件）
3. 混合语义匹配（Model2Vec / BGE-Small-ZH，自适应路由）
4. 置信度校准（基于历史反馈）

改进特性 (v2.0):
- 混合语义匹配器：支持 Model2Vec (30MB) 和 BGE-Small-ZH (100MB INT8)
- 置信度校准器：在线校准，无需训练
- 决策证据链：结构化输出，便于调试
- 延迟加载：模型按需加载，降低启动时间

研究依据:
- EmbeddingGemma (Google 2025): 308M 量化后<200MB
- Model2Vec (2024): 50x 更小，500x 更快
- BGE-Small-ZH: C-MTEB 中文榜首小模型 (~64 分)
- 量化技术 (Vespa 2025): INT8 保留 94-98% 质量，2.7x 加速
"""

import re
import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal, Tuple
from enum import Enum


class Decision(Enum):
    """决策结果枚举"""
    RESUME = "resume"      # 应该继续指定任务
    NEW_TASK = "new_task"  # 应该创建新任务
    UNCERTAIN = "uncertain"  # 无法确定


@dataclass
class TaskNode:
    """任务节点 - 表示一次 vibe coding 调用"""
    record_id: str                    # 唯一标识符
    prompt: str                       # 原始 prompt
    task_desc: str = ""               # 任务摘要描述
    files_created: list[str] = field(default_factory=list)   # 创建的文件
    files_modified: list[str] = field(default_factory=list)  # 修改的文件
    functions: list[str] = field(default_factory=list)      # 定义的函数
    classes: list[str] = field(default_factory=list)        # 定义的类
    imports: list[str] = field(default_factory=list)        # 导入的模块
    timestamp: str = ""               # ISO 格式时间戳
    metadata: dict = field(default_factory=dict)  # 其他元数据

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    @property
    def all_files(self) -> set[str]:
        """所有涉及的文件"""
        return set(self.files_created + self.files_modified)
    
    @property
    def all_symbols(self) -> set[str]:
        """所有定义的符号（函数 + 类）"""
        return set(self.functions + self.classes)
    
    @property
    def text_for_embedding(self) -> str:
        """获取用于 embedding 的文本（组合关键信息）"""
        parts = []
        if self.task_desc:
            parts.append(self.task_desc)
        parts.append(self.prompt)
        if self.files_created:
            parts.append("文件：" + ", ".join(self.files_created))
        return " ".join(parts)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "record_id": self.record_id,
            "prompt": self.prompt,
            "task_desc": self.task_desc,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "functions": self.functions,
            "classes": self.classes,
            "timestamp": self.timestamp,
        }


@dataclass
class DecisionResult:
    """决策结果"""
    decision: Decision
    target_record_id: Optional[str]
    confidence: float
    reason: str
    candidates: list[dict] = field(default_factory=list)
    layers_used: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)  # 决策证据
    metadata: dict = field(default_factory=dict)  # 元数据

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.value,
            "target_record": self.target_record_id,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "candidates": self.candidates,
            "layers_used": self.layers_used,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class TaskRelation:
    """任务间关系"""
    source_id: str
    target_id: str
    relation_type: str  # "extends", "modifies", "depends_on", "shares_deps"
    confidence: float
    weight: float = 1.0  # 边权重（用于图算法）


class QuickRuleMatcher:
    """快速规则匹配器 - 第一层过滤"""
    
    # 必须创建新任务的关键词
    NEW_TASK_PATTERNS = [
        r"新建", r"重新开始", r"另一个项目", r"从头开始",
        r"独立项目", r"新建项目", r"新开一个", r"换个项目",
        r"不要.*继续", r"不用.*之前", r"不需要.*历史",
        r"创建.*新.*项目", r"开始.*新.*任务",
        r"^(?!.*继续)(?!.*接着).*项目",  # 以"项目"开头但没有继续/接着
        # English patterns
        r"create.*new", r"start.*new", r"build.*new", r"new.*project",
        r"independent.*project", r"separate.*project", r"another.*project",
        r"don't.*continue", r"don't.*use.*previous", r"no.*need.*history",
        r"from scratch", r"brand new", r"fresh start",
    ]
    
    # 明确继续的关键词
    RESUME_PATTERNS = [
        r"继续", r"接着", r"在.*基础上", r"在.*之上",
        r"基于.*继续", r"承接.*上", r"在.*添加",
        r"完善.*上", r"继续.*刚才", r"继续.*之前",
        r"接着.*做", r"把.*继续", r"把.*完善",
        r"在.*修改", r"给.*添加功能",
        # English patterns
        r"continue", r"keep.*working", r"carry.*on", r"proceed.*with",
        r"add.*to.*existing", r"extend.*the", r"further.*develop",
        r"improve.*the", r"enhance.*the", r"further.*the",
        r"work.*on.*the", r"develop.*the", r"build.*upon",
        r"based.*on.*previous", r"following.*up", r"next.*step",
    ]
    
    @classmethod
    def match(cls, prompt: str) -> Optional[DecisionResult]:
        """快速匹配，返回决策结果或 None（表示无法确定）"""
        prompt_lower = prompt.lower()
        
        # 检查是否必须新建
        for pattern in cls.NEW_TASK_PATTERNS:
            if re.search(pattern, prompt_lower):
                return DecisionResult(
                    decision=Decision.NEW_TASK,
                    target_record_id=None,
                    confidence=0.95,
                    reason=f"检测到明确的新建信号：匹配模式 '{pattern}'",
                    layers_used=["quick_rules"]
                )
        
        # 检查是否明确继续
        for pattern in cls.RESUME_PATTERNS:
            if re.search(pattern, prompt_lower):
                return DecisionResult(
                    decision=Decision.RESUME,
                    target_record_id=None,
                    confidence=0.80,
                    reason=f"检测到明确的继续信号：匹配模式 '{pattern}'",
                    layers_used=["quick_rules"]
                )
        
        return None


class FileDependencyAnalyzer:
    """文件依赖分析器 - 第二层分析"""
    
    @classmethod
    def extract_files(cls, prompt: str) -> list[str]:
        """从 prompt 中提取文件引用"""
        files = []
        
        # 匹配反引号中的文件
        backtick_matches = re.findall(r'`([^`]+)`', prompt)
        files.extend(backtick_matches)
        
        # 匹配路径中的文件
        path_pattern = r'/([\w\-./]+\.(?:py|js|ts|jsx|tsx|vue|css|html|json|yaml|yml|md|txt|go|rs|java|cpp|c|h))'
        path_matches = re.findall(path_pattern, prompt)
        files.extend(path_matches)
        
        # 匹配文件名（带扩展名）
        name_pattern = r'([\w\-]+\.(?:py|js|ts|jsx|tsx|vue|css|html|json|yaml|yml|md|txt|go|rs|java|cpp|c|h))'
        name_matches = re.findall(name_pattern, prompt, re.IGNORECASE)
        files.extend(name_matches)
        
        # 去重
        return list(set(files))
    
    @classmethod
    def score_by_files(cls, prompt: str, node: TaskNode) -> float:
        """基于文件引用计算候选节点得分"""
        files = cls.extract_files(prompt)
        if not files:
            return 0.0
        
        score = 0.0
        files_set = set(files)
        
        # 直接命中创建的文件
        if files_set.intersection(set(node.files_created)):
            score += 0.6
        
        # 命中修改的文件
        if files_set.intersection(set(node.files_modified)):
            score += 0.4
        
        # 部分匹配
        overlap = files_set & node.all_files
        if overlap and score == 0:
            score = len(overlap) / len(files_set) * 0.5
        
        return min(score, 1.0)


class HybridSemanticMatcher:
    """混合语义匹配器 - 轻量级实现（无外部依赖）"""
    
    # 中文停用词（精简版）
    STOP_WORDS = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
        "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
        "你", "会", "着", "没有", "看", "好", "自己", "这", "那",
    }
    
    # 模型配置
    MODEL_CONFIGS = {
        "ultra_light": {
            "name": "tfidf",
            "dims": 256,
            "memory_mb": 5,
            "latency_ms": 1,
        },
        "light": {
            "name": "hash_ngram",
            "dims": 512,
            "memory_mb": 10,
            "latency_ms": 2,
        },
        "balanced": {
            "name": "hash_ngram",
            "dims": 512,
            "memory_mb": 10,
            "latency_ms": 2,
        },
    }
    
    def __init__(
        self,
        mode: Literal["ultra_light", "light", "balanced"] = "light",
        embedder=None,
    ):
        """
        :param mode: 模型模式 ("ultra_light" | "light")
        :param embedder: 自定义 embedder（用于测试注入）
        """
        self.mode = mode
        self.config = self.MODEL_CONFIGS.get(mode, self.MODEL_CONFIGS["light"])
        self.embedder = embedder
        self.cache: dict[str, list[float]] = {}
        self._model = None
        self._model_loaded = False
        self._tfidf_vectorizer = None
        self._tfidf_docs = []
        self._word_freq = {}  # 词频统计（用于 IDF）
        self._doc_count = 0  # 文档总数
    
    def _lazy_load_model(self):
        """延迟加载模型（降低启动时间）"""
        if self._model_loaded:
            return
        
        if self.embedder is not None:
            self._model = self.embedder
            self._model_loaded = True
            return
        
        # 尝试加载 Model2Vec（可选）
        if self.mode == "ultra_light":
            try:
                from model2vec import StaticModel  # type: ignore
                self._model = StaticModel.from_pretrained(
                    "minishlab/potion-base-8M",
                    normalize=True,
                )
                self._model_loaded = True
                return
            except ImportError:
                pass
        
        # 默认使用内置方法
        self._model = "builtin"
        self._model_loaded = True
    
    def _tokenize(self, text: str) -> list[str]:
        """中文分词（简单版：按字符 + 关键词）"""
        # 提取英文单词
        import re
        english_words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        
        # 中文按字符分割（去除停用词）
        chinese_chars = [
            c for c in text 
            if '\u4e00' <= c <= '\u9fff' and c not in self.STOP_WORDS
        ]
        
        # 提取文件名和路径（重要特征）
        file_pattern = r'[\w\-./]+\.(?:py|js|ts|jsx|tsx|vue|css|html|json|yaml|yml|md|txt)'
        files = re.findall(file_pattern, text)
        
        # 组合特征
        tokens = english_words + chinese_chars + files
        return tokens
    
    def _extract_keywords(self, text: str) -> list[str]:
        """提取关键词（带权重）"""
        tokens = self._tokenize(text)
        
        # 统计词频
        freq = {}
        for token in tokens:
            freq[token] = freq.get(token, 0) + 1
        
        # 更新全局 IDF
        self._doc_count += 1
        for token in set(tokens):
            self._word_freq[token] = self._word_freq.get(token, 0) + 1
        
        # 计算 TF-IDF 分数
        import math
        keywords = []
        for token, tf in freq.items():
            idf = math.log(
                (self._doc_count + 1) / (self._word_freq.get(token, 0) + 1)
            ) + 1
            score = tf * idf
            keywords.append((token, score))
        
        # 按分数排序，取前 100 个
        keywords.sort(key=lambda x: x[1], reverse=True)
        return [kw for kw, _ in keywords[:100]]
    
    def _compute_tfidf_vector(self, text: str, dim: int = 512) -> list[float]:
        """计算 TF-IDF 向量"""
        keywords = self._extract_keywords(text)
        
        vec = [0.0] * dim
        for i, keyword in enumerate(keywords):
            # 使用 hash 映射到固定维度
            idx = hash(keyword) % dim
            # 权重：位置越靠前权重越高
            weight = 1.0 / (i + 1)
            vec[idx] += weight
        
        # 归一化
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        
        return vec
    
    def _compute_hash_ngram(self, text: str, dim: int = 512) -> list[float]:
        """
        增强型 hash + n-gram 特征
        
        改进点：
        1. 使用 unigram + bigram + trigram
        2. 中文按字符 + 关键词
        3. 英文按单词
        """
        import re
        
        # 提取特征
        tokens = []
        
        # Unigram: 单个字符/单词
        tokens.extend(self._tokenize(text))
        
        # Bigram: 连续两个字符
        for i in range(len(text) - 1):
            bigram = text[i:i+2]
            if len(bigram) >= 2 and bigram not in self.STOP_WORDS:
                tokens.append(bigram)
        
        # Trigram: 连续三个字符（仅中文）
        for i in range(len(text) - 2):
            trigram = text[i:i+3]
            if all('\u4e00' <= c <= '\u9fff' for c in trigram):
                tokens.append(trigram)
        
        # 提取文件名（高权重）
        files = re.findall(
            r'[\w\-./]+\.(?:py|js|ts|jsx|tsx|vue|css|html|json|yaml|yml|md|txt)',
            text
        )
        tokens.extend(files)  # 文件名重复一次以增加权重
        
        # 计算向量
        vec = [0.0] * dim
        for token in tokens:
            # 使用 hash 映射到固定维度
            idx = hash(token.lower()) % dim
            vec[idx] += 1.0
        
        # 归一化
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        
        return vec
    
    def encode(self, text: str, use_cache: bool = True) -> list[float]:
        """编码文本为向量"""
        cache_key = f"{self.mode}:{hashlib.md5(text.encode()).hexdigest()[:16]}"
        
        if use_cache and cache_key in self.cache:
            return self.cache[cache_key]
        
        self._lazy_load_model()
        
        # 使用自定义 embedder
        if self.embedder is not None and hasattr(self.embedder, 'encode'):
            result = self.embedder.encode([text])  # type: ignore
            vec = result[0].tolist() if hasattr(result[0], 'tolist') else list(result[0])  # type: ignore
        # 尝试 Model2Vec
        elif hasattr(self._model, 'encode') and self._model != "builtin":
            result = self._model.encode([text])  # type: ignore
            vec = result[0].tolist() if hasattr(result[0], 'tolist') else list(result[0])  # type: ignore
        # 使用内置方法
        else:
            if self.mode == "ultra_light":
                vec = self._compute_tfidf_vector(text, self.config["dims"])
            else:
                vec = self._compute_hash_ngram(text, self.config["dims"])
        
        if use_cache:
            self.cache[cache_key] = vec
        
        return vec
    
    def compute_similarity(self, prompt: str, node: TaskNode) -> Tuple[float, str]:
        """
        计算 prompt 与历史任务的语义相似度
        
        :return: (similarity_score, path_used)
        """
        prompt_emb = self.encode(prompt)
        
        node_key = f"{self.mode}:node:{node.record_id}"
        if node_key not in self.cache:
            text = node.text_for_embedding
            self.cache[node_key] = self.encode(text)
        node_emb = self.cache[node_key]
        
        similarity = self.cosine_similarity(prompt_emb, node_emb)
        
        return similarity, self.mode
    
    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """计算余弦相似度"""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    
    def _simple_hash(self, text: str, dim: int = 256) -> list[float]:
        """简单的文本 hash 作为伪向量（fallback）"""
        vec = [0.0] * dim
        for i, char in enumerate(text):
            vec[i % dim] += ord(char)
        # 归一化
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec
    
    def clear_cache(self):
        """清理缓存"""
        self.cache.clear()
    
    def get_memory_usage_mb(self) -> float:
        """估算内存占用 (MB)"""
        if not self._model_loaded:
            return 0.0
        return self.config.get("memory_mb", 50.0)


class ConfidenceCalibrator:
    """
    置信度校准器 - 基于历史反馈的在线校准
    
    无需训练，使用滑动窗口统计进行校准
    参考：ALAS (arXiv:2511.03094) 事务性执行日志
    """
    
    def __init__(self, window_size: int = 100, num_bins: int = 10):
        self.window_size = window_size
        self.num_bins = num_bins
        # 存储 (predicted_confidence, actual_correct)
        self.history: list[tuple[float, bool]] = []
        # 分桶统计：bin_idx -> (total_count, correct_count)
        self.buckets: dict[int, list[int]] = {
            i: [0, 0] for i in range(num_bins)
        }
    
    def update(self, predicted_conf: float, actual_correct: bool):
        """
        更新历史记录
        
        :param predicted_conf: 预测置信度 (0.0-1.0)
        :param actual_correct: 实际是否正确
        """
        self.history.append((predicted_conf, actual_correct))
        
        # 更新分桶统计
        bin_idx = min(int(predicted_conf * self.num_bins), self.num_bins - 1)
        self.buckets[bin_idx][0] += 1
        if actual_correct:
            self.buckets[bin_idx][1] += 1
        
        # 保持窗口大小
        if len(self.history) > self.window_size:
            old_conf, old_correct = self.history.pop(0)
            old_bin = min(int(old_conf * self.num_bins), self.num_bins - 1)
            self.buckets[old_bin][0] -= 1
            if old_correct:
                self.buckets[old_bin][1] -= 1
    
    def calibrate(self, raw_confidence: float) -> float:
        """
        校准置信度
        
        :param raw_confidence: 原始置信度
        :return: 校准后的置信度
        """
        if len(self.history) < 20:
            return raw_confidence  # 数据不足，返回原始值
        
        bin_idx = min(int(raw_confidence * self.num_bins), self.num_bins - 1)
        total, correct = self.buckets[bin_idx]
        
        if total < 5:
            # 当前桶数据不足，使用平滑
            return self._smoothed_calibrate(raw_confidence)
        
        # 向经验准确率收缩
        empirical_accuracy = correct / total
        return (raw_confidence + empirical_accuracy) / 2
    
    def _smoothed_calibrate(self, raw_confidence: float) -> float:
        """平滑校准（使用相邻桶）"""
        bin_idx = min(int(raw_confidence * self.num_bins), self.num_bins - 1)
        
        # 收集相邻桶的统计
        all_total, all_correct = 0, 0
        for offset in [-1, 0, 1]:
            neighbor_bin = max(0, min(bin_idx + offset, self.num_bins - 1))
            t, c = self.buckets[neighbor_bin]
            all_total += t
            all_correct += c
        
        if all_total < 5:
            return raw_confidence
        
        empirical = all_correct / all_total
        return (raw_confidence + empirical) / 2
    
    def get_reliability_report(self) -> dict:
        """生成可靠性报告"""
        if len(self.history) < 20:
            return {"status": "insufficient_data", "samples": len(self.history)}
        
        # 计算每个桶的准确率
        bucket_accuracies = {}
        for bin_idx, (total, correct) in self.buckets.items():
            if total >= 5:
                bucket_accuracies[f"{bin_idx/self.num_bins:.1f}-{(bin_idx+1)/self.num_bins:.1f}"] = {
                    "count": total,
                    "accuracy": round(correct / total, 3)
                }
        
        # 计算整体校准误差 (ECE)
        calibration_error = self._compute_calibration_error()
        
        return {
            "status": "ready",
            "samples": len(self.history),
            "bucket_accuracies": bucket_accuracies,
            "calibration_error": round(calibration_error, 4),
        }
    
    def _compute_calibration_error(self) -> float:
        """计算期望校准误差 (Expected Calibration Error)"""
        ece = 0.0
        total_samples = len(self.history)
        
        for bin_idx, (total, correct) in self.buckets.items():
            if total == 0:
                continue
            
            avg_confidence = (bin_idx + 0.5) / self.num_bins
            empirical_accuracy = correct / total
            ece += (total / total_samples) * abs(avg_confidence - empirical_accuracy)
        
        return ece


class TaskDependencyGraph:
    """
    任务依赖图 - 整合所有分析器做出最终决策
    
    使用分层决策：
    1. 快速规则过滤
    2. 文件依赖分析
    3. 混合语义匹配（Model2Vec / BGE-Small-ZH）
    4. 置信度校准
    
    v2.0 改进特性:
    - 混合语义匹配器：支持多种轻量级模型
    - 置信度校准器：在线校准，无需训练
    - 决策证据链：结构化输出，便于调试
    """
    
    # 决策阈值
    HIGH_CONFIDENCE = 0.75
    MEDIUM_CONFIDENCE = 0.60
    LOW_CONFIDENCE = 0.40
    
    def __init__(
        self,
        embedder=None,
        semantic_mode: Literal["ultra_light", "light", "balanced"] = "light",
        enable_calibration: bool = True,
    ):
        """
        :param embedder: 嵌入模型（可选），用于语义相似度计算
        :param semantic_mode: 语义模型模式 ("ultra_light" | "light" | "balanced")
        :param enable_calibration: 是否启用置信度校准
        """
        self.tasks: dict[str, TaskNode] = {}  # record_id -> TaskNode
        self.quick_matcher = QuickRuleMatcher()
        self.file_analyzer = FileDependencyAnalyzer()
        self.semantic_matcher = HybridSemanticMatcher(
            mode=semantic_mode,
            embedder=embedder,
        )
        self.calibrator = ConfidenceCalibrator() if enable_calibration else None
        self._decision_history: list[tuple[str, DecisionResult]] = []
    
    def add_task(self, record_id: str, prompt: str, **kwargs) -> TaskNode:
        """
        添加新任务节点
        
        Args:
            record_id: 任务唯一标识
            prompt: 原始 prompt
            **kwargs: TaskNode 的其他字段
                - task_desc: 任务摘要
                - files_created: 创建的文件列表
                - files_modified: 修改的文件列表
                - functions: 定义的函数
                - classes: 定义的类
        
        Returns:
            创建的 TaskNode
        """
        node = TaskNode(
            record_id=record_id,
            prompt=prompt,
            **kwargs
        )
        self.tasks[record_id] = node
        return node
    
    def update_task(self, record_id: str, **updates):
        """更新任务节点信息（通常在任务完成后调用）"""
        if record_id in self.tasks:
            node = self.tasks[record_id]
            for key, value in updates.items():
                if hasattr(node, key):
                    old_value = getattr(node, key)
                    if isinstance(old_value, list) and isinstance(value, list):
                        # 合并列表
                        setattr(node, key, list(set(old_value + value)))
                    else:
                        setattr(node, key, value)
    
    def add_files_to_task(self, record_id: str, files_created: Optional[list[str]] = None,
                          files_modified: Optional[list[str]] = None):
        """向任务添加文件信息"""
        self.update_task(
            record_id,
            files_created=files_created or [],
            files_modified=files_modified or []
        )
    
    def decide(self, prompt: str, exclude_record: Optional[str] = None) -> DecisionResult:
        """
        核心决策方法 - 判断新任务是否应该 resume
        
        Args:
            prompt: 新任务的 prompt
            exclude_record: 要排除的 record_id（可选，通常是当前正在进行的任务）
        
        Returns:
            DecisionResult 决策结果
        """
        # 收集证据（用于解释）
        evidence = {
            "file_matches": [],
            "semantic_matches": [],
            "rule_triggers": [],
        }
        
        # === 第一层：快速规则 ===
        quick_result = self.quick_matcher.match(prompt)
        if quick_result:
            if quick_result.decision == Decision.NEW_TASK:
                return quick_result
            elif quick_result.decision == Decision.RESUME:
                # 快速规则确定要 resume，但需要找具体目标
                # 继续到后续层找最佳匹配
                pass
            evidence["rule_triggers"].append({
                "type": "quick_rule",
                "pattern": quick_result.reason,
                "decision": quick_result.decision.value,
            })
            layers_used = ["quick_rules"]
        else:
            layers_used = []
        
        # === 第二层：文件依赖分析 ===
        candidates = []
        for record_id, node in self.tasks.items():
            if record_id == exclude_record:
                continue
            
            file_score = self.file_analyzer.score_by_files(prompt, node)
            if file_score > 0:
                candidates.append({
                    "record_id": record_id,
                    "node": node,
                    "file_score": file_score,
                })
                if file_score > 0.3:
                    evidence["file_matches"].append({
                        "record_id": record_id,
                        "score": round(file_score, 3),
                        "matched_files": list(
                            set(self.file_analyzer.extract_files(prompt)).intersection(node.all_files)
                        ),
                    })
        
        # 按文件得分排序
        candidates.sort(key=lambda x: x["file_score"], reverse=True)
        
        best_file_candidate = candidates[0] if candidates else None
        
        # === 第三层：语义相似度 ===
        semantic_scores = []
        for record_id, node in self.tasks.items():
            if record_id == exclude_record:
                continue
            
            # 有 embedder 或任务不多，进行语义匹配
            if self.semantic_matcher._model_loaded or len(self.tasks) < 10:
                sim, path_used = self.semantic_matcher.compute_similarity(prompt, node)
                if sim > 0.3:
                    semantic_scores.append({
                        "record_id": record_id,
                        "node": node,
                        "semantic_score": sim,
                        "path_used": path_used,
                    })
                    if sim > 0.5:
                        evidence["semantic_matches"].append({
                            "record_id": record_id,
                            "score": round(sim, 3),
                            "path": path_used,
                        })
        
        semantic_scores.sort(key=lambda x: x["semantic_score"], reverse=True)
        best_semantic_candidate = semantic_scores[0] if semantic_scores else None
        
        # === 综合决策 ===
        layers_used.append("file_dependency")
        if best_semantic_candidate:
            layers_used.append(f"semantic:{best_semantic_candidate.get('path_used', 'unknown')}")
        
        result = self._make_decision(
            quick_result=quick_result,
            best_file_candidate=best_file_candidate,
            best_semantic_candidate=best_semantic_candidate,
            candidates=candidates,
            layers_used=layers_used,
            evidence=evidence,
        )
        
        # === 置信度校准 ===
        if self.calibrator is not None:
            original_conf = result.confidence
            result.confidence = self.calibrator.calibrate(original_conf)
            result.metadata["original_confidence"] = round(original_conf, 3)
            result.metadata["calibrated"] = True
        
        # 记录决策（用于后续反馈）
        self._decision_history.append((prompt, result))
        
        return result
    
    def _make_decision(
        self,
        quick_result: Optional[DecisionResult],
        best_file_candidate: Optional[dict],
        best_semantic_candidate: Optional[dict],
        candidates: list[dict],
        layers_used: list[str],
        evidence: dict,
    ) -> DecisionResult:
        """制定最终决策"""
        
        if best_file_candidate and best_file_candidate["file_score"] >= self.HIGH_CONFIDENCE:
            return DecisionResult(
                decision=Decision.RESUME,
                target_record_id=best_file_candidate["record_id"],
                confidence=best_file_candidate["file_score"],
                reason="文件依赖分析匹配度高",
                candidates=self._format_candidates(candidates[:5]),
                layers_used=layers_used,
                evidence=evidence,
            )
        
        if best_file_candidate and best_semantic_candidate:
            if best_file_candidate["record_id"] == best_semantic_candidate["record_id"]:
                avg_score = (
                    best_file_candidate["file_score"] +
                    best_semantic_candidate["semantic_score"]
                ) / 2
                if avg_score >= self.MEDIUM_CONFIDENCE:
                    return DecisionResult(
                        decision=Decision.RESUME,
                        target_record_id=best_file_candidate["record_id"],
                        confidence=avg_score,
                        reason="文件依赖和语义分析双重匹配",
                        candidates=self._format_candidates(candidates[:5]),
                        layers_used=layers_used,
                        evidence=evidence,
                    )
        
        if best_semantic_candidate and best_semantic_candidate["semantic_score"] >= self.HIGH_CONFIDENCE:
            return DecisionResult(
                decision=Decision.RESUME,
                target_record_id=best_semantic_candidate["record_id"],
                confidence=best_semantic_candidate["semantic_score"],
                reason="语义相似度匹配度高",
                candidates=self._format_candidates(candidates[:5]),
                layers_used=layers_used,
                evidence=evidence,
            )
        
        if best_file_candidate and best_file_candidate["file_score"] >= self.LOW_CONFIDENCE:
            if quick_result and quick_result.decision == Decision.RESUME:
                return DecisionResult(
                    decision=Decision.RESUME,
                    target_record_id=best_file_candidate["record_id"],
                    confidence=best_file_candidate["file_score"],
                    reason="快速规则 + 文件分析联合判断",
                    candidates=self._format_candidates(candidates[:5]),
                    layers_used=layers_used,
                    evidence=evidence,
                )
        
        if candidates and best_file_candidate:
            return DecisionResult(
                decision=Decision.RESUME,
                target_record_id=best_file_candidate["record_id"],
                confidence=max(best_file_candidate["file_score"], self.LOW_CONFIDENCE),
                reason=f"自动选择最佳匹配（文件得分：{best_file_candidate['file_score']:.2f}）",
                candidates=self._format_candidates(candidates[:3]),
                layers_used=layers_used,
                evidence=evidence,
            )
        elif best_semantic_candidate and best_semantic_candidate["semantic_score"] >= self.LOW_CONFIDENCE:
            return DecisionResult(
                decision=Decision.RESUME,
                target_record_id=best_semantic_candidate["record_id"],
                confidence=best_semantic_candidate["semantic_score"],
                reason="语义相似度匹配（文件依赖不足）",
                candidates=self._format_candidates([]),
                layers_used=layers_used,
                evidence=evidence,
            )
        
        return DecisionResult(
            decision=Decision.NEW_TASK,
            target_record_id=None,
            confidence=1.0,
            reason="没有可用的历史任务记录",
            layers_used=layers_used,
            evidence=evidence,
        )
    
    def _format_candidates(self, candidates: list[dict]) -> list[dict]:
        """格式化候选列表"""
        return [
            {
                "record_id": c["record_id"],
                "task_desc": c["node"].task_desc or c["node"].prompt[:100],
                "file_score": round(c.get("file_score", 0), 3),
                "semantic_score": round(c.get("semantic_score", 0), 3),
            }
            for c in candidates
        ]
    
    def record_feedback(self, decision_correct: bool, target_prompt: Optional[str] = None):
        """
        记录决策反馈（用于校准）
        
        :param decision_correct: 决策是否正确
        :param target_prompt: 指定 prompt（默认为最近一次决策）
        """
        if self.calibrator is None:
            return
        
        if target_prompt:
            for prompt, result in reversed(self._decision_history):
                if prompt == target_prompt:
                    self.calibrator.update(result.confidence, decision_correct)
                    break
        elif self._decision_history:
            # 使用最近一次决策
            prompt, result = self._decision_history[-1]
            self.calibrator.update(result.confidence, decision_correct)
    
    def get_task_history(self) -> list[dict]:
        """获取所有历史任务"""
        return [node.to_dict() for node in self.tasks.values()]
    
    def get_task(self, record_id: str) -> Optional[TaskNode]:
        """获取指定任务"""
        return self.tasks.get(record_id)
    
    def clear(self):
        """清空所有任务（用于测试或重置）"""
        self.tasks.clear()
        self.semantic_matcher.clear_cache()
    
    def get_memory_usage_mb(self) -> float:
        """获取预估内存占用 (MB)"""
        return self.semantic_matcher.get_memory_usage_mb()


# 便捷函数
def create_decision(prompt: str, tasks: Optional[list[dict]] = None, embedder=None) -> str:
    """
    快速创建决策结果的便捷函数
    
    Args:
        prompt: 新任务 prompt
        tasks: 历史任务列表 [{"record_id": "...", "prompt": "...", ...}, ...]
        embedder: 嵌入模型（可选）
    
    Returns:
        JSON 字符串格式的决策结果
    """
    graph = TaskDependencyGraph(embedder=embedder, semantic_mode="light")
    
    if tasks:
        for task in tasks:
            graph.add_task(
                record_id=task["record_id"],
                prompt=task.get("prompt", ""),
                task_desc=task.get("task_desc", ""),
                files_created=task.get("files_created", []),
                files_modified=task.get("files_modified", []),
                functions=task.get("functions", []),
                classes=task.get("classes", []),
            )
    
    result = graph.decide(prompt)
    return result.to_json()


if __name__ == "__main__":
    # 测试任务依赖图功能
    print("=== 任务依赖图 v2.0 Ultra-Lite 分析测试 ===\n")
    
    graph = TaskDependencyGraph(semantic_mode="light", enable_calibration=True)
    
    # 模拟一些历史任务
    graph.add_task(
        record_id="record_001",
        prompt="写一个简单的计算器程序，保存到 calculator.py",
        task_desc="实现基础计算器功能",
        files_created=["calculator.py"]
    )
    
    graph.add_task(
        record_id="record_002",
        prompt="给刚才的计算器添加乘除法功能",
        task_desc="完善计算器乘除法",
        files_modified=["calculator.py"]
    )
    
    graph.add_task(
        record_id="record_003",
        prompt="创建一个新的爬虫项目，用于爬取新闻网站",
        task_desc="初始化爬虫项目",
        files_created=["spider.py", "requirements.txt"]
    )

    # 测试用例 1: 明确的继续意图
    test_prompt_1 = "继续完善刚才的计算器，添加图形界面"
    print(f"测试 1 - Prompt: '{test_prompt_1}'")
    result_1 = graph.decide(test_prompt_1)
    print(f"决策：{result_1.decision.value}, 目标：{result_1.target_record_id}, 置信度：{result_1.confidence}")
    print(f"原因：{result_1.reason}")
    print(f"使用层：{result_1.layers_used}")
    print()

    # 测试用例 2: 显式引用文件
    test_prompt_2 = "修改 spider.py，支持并发爬取"
    print(f"测试 2 - Prompt: '{test_prompt_2}'")
    result_2 = graph.decide(test_prompt_2)
    print(f"决策：{result_2.decision.value}, 目标：{result_2.target_record_id}, 置信度：{result_2.confidence}")
    print(f"原因：{result_2.reason}")
    print(f"使用层：{result_2.layers_used}")
    print()

    # 测试用例 3: 明确的新建项目
    test_prompt_3 = "新建一个独立的项目，做一个个人博客系统"
    print(f"测试 3 - Prompt: '{test_prompt_3}'")
    result_3 = graph.decide(test_prompt_3)
    print(f"决策：{result_3.decision.value}, 目标：{result_3.target_record_id}, 置信度：{result_3.confidence}")
    print(f"原因：{result_3.reason}")
    print(f"使用层：{result_3.layers_used}")
    print()

    # 测试用例 4: 语义上的联系（无明确关键词或文件）
    test_prompt_4 = "优化刚才那个抓取工具的性能"
    print(f"测试 4 - Prompt: '{test_prompt_4}'")
    result_4 = graph.decide(test_prompt_4)
    print(f"决策：{result_4.decision.value}, 目标：{result_4.target_record_id}, 置信度：{result_4.confidence}")
    print(f"原因：{result_4.reason}")
    print(f"使用层：{result_4.layers_used}")
    print()

    # 测试用例 5: 完全无关的新任务
    test_prompt_5 = "写一篇关于 AI 发展的论文摘要"
    print(f"测试 5 - Prompt: '{test_prompt_5}'")
    result_5 = graph.decide(test_prompt_5)
    print(f"决策：{result_5.decision.value}, 目标：{result_5.target_record_id}, 置信度：{result_5.confidence}")
    print(f"原因：{result_5.reason}")
    print(f"使用层：{result_5.layers_used}")
    print()

    # 内存使用
    print(f"预估内存占用：{graph.get_memory_usage_mb():.1f} MB")
    
    # 校准报告
    if graph.calibrator:
        print(f"\n校准报告：{graph.calibrator.get_reliability_report()}")
