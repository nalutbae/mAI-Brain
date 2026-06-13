"""mAI-Brain AI 챗봇 — 쿼리 확장 모듈

3가지 전략으로 사용자 질문을 확장하여 검색 품질을 향상:
1. Multi-Query Expansion: LLM이 3-5개 질문 변형을 생성 → 각각 검색 → 결과 병합(중복 제거)
2. HyDE (Hypothetical Document Embedding): LLM이 가상 답변을 생성 → 답변 임베딩으로 검색
3. Korean Synonym Expansion: 한국 법률/비즈니스 용어, 약어, 높임말 동의어 확장

auto 모드: 짧은 쿼리(<10자) 또는 한국 법률 용어 감지 시 적절한 전략 자동 선택.
"""

from __future__ import annotations

import enum
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.core.embedding import EmbeddingResult, get_embedding_provider
from app.core.llm import get_llm_client
from app.models.chat import SearchHit

logger = logging.getLogger(__name__)


# =========================================================================== #
# 전략 Enum
# =========================================================================== #

class QueryExpansionStrategy(str, enum.Enum):
    """쿼리 확장 전략"""
    MULTI_QUERY = "multi_query"
    HYDE = "hyde"
    KOREAN_SYNONYMS = "korean_synonyms"
    AUTO = "auto"
    NONE = "none"  # 확장 없음


@dataclass
class ExpansionResult:
    """쿼리 확장 결과

    Attributes:
        original_query: 원본 질문
        expanded_queries: 확장된 질문 리스트 (원본 포함)
        strategy_used: 사용된 전략
        hyde_embedding: HyDE 전략 시 가상 답변의 임베딩 (다른 전략은 None)
        hyde_answer: HyDE 전략 시 생성된 가상 답변 텍스트 (다른 전략은 None)
    """
    original_query: str
    expanded_queries: list[str] = field(default_factory=list)
    strategy_used: QueryExpansionStrategy = QueryExpansionStrategy.NONE
    hyde_embedding: Optional[list[float]] = None
    hyde_answer: Optional[str] = None


# =========================================================================== #
# 한국어 동의어 사전 (법률/비즈니스 용어 50+ 매핑)
# =========================================================================== #

KOREAN_SYNONYM_DICT: dict[str, list[str]] = {
    # ── 법률 용어 ──────────────────────────────────────────────────────
    "소유권": ["권리", "등기", "재산권", "소유"],
    "계약": ["합의", "약정", "협약", "계약서", "문서"],
    "소송": ["재판", "법정", "분쟁", "소송사건", "제소"],
    "판결": ["결정", "재판", "판시", "선고", "판례"],
    "위반": ["위배", "저촉", "불법", "규위", "위법"],
    "규정": ["조항", "규칙", "법령", "조례", "규범"],
    "인가": ["승인", "허가", "면허", "인허가", "공인"],
    "허가": ["인가", "승인", "면허", "인허가", "허락"],
    "면허": ["허가", "인가", "자격증", "면허증", "영업허가"],
    "등기": ["등록", "기록", "부동산등기", "등기부등본"],
    "등록": ["등기", "기록", "신고", "가입", "접수"],
    "집행": ["이행", "실행", "강제집행", "집행력"],
    "의무": ["책임", "의무사항", "의무조항", "의무사"],
    "권리": ["소유권", "이익", "자격", "권한", "권리사"],
    "책임": ["의무", "부담", "책임사항", "법적책임"],
    "손해": ["피해", "손실", "손상", "손해배상"],
    "배상": ["보상", "전보", "손해배상", "배상금"],
    "보상": ["배상", "전보", "대가", "보상금"],
    "합의": ["계약", "약정", "동의", "협약", "합의서"],
    "약정": ["계약", "합의", "협약", "약정서"],
    "동의": ["합의", "승인", "허락", "찬성"],
    "성명": ["이름", "이름명", "본명", "성명란"],
    "주소": ["거주지", "소재지", "주소지", "주소란"],
    "대리인": ["대리", "대표자", "대리변호사", "선임대리인"],
    "변호사": ["법률대리인", "변호", "법률가", "대리변호사"],
    "피고": ["피고인", "소송피고", "상대방"],
    "원고": ["소송원고", "원고인", "청구인"],
    "청구": ["요구", "신청", "소송청구", "청구권"],
    "신청": ["요청", "청구", "신청서", "제출"],
    "공고": ["게시", "공시", "통고", "공고문"],

    # ── 비즈니스 용어 ────────────────────────────────────────────────────
    "법인": ["회사", "기업", "법인격", "법인체"],
    "회사": ["법인", "기업", "상장사", "기관"],
    "사업": ["영업", "사업장", "사업자", "사업자등록"],
    "영업": ["사업", "영업활동", "영업행위", "상거래"],
    "투자": ["출자", "투자금", "투자자", "투자계약"],
    "출자": ["투자", "출자금", "출자자", "지분"],
    "지분": ["출자", "주식", "소유지분", "지분율"],
    "주식": ["지분", "주권", "보통주", "주식회사"],
    "이사": ["임원", "이사회", "대표이사", "사외이사"],
    "감사": ["감사인", "감사보고서", "회계감사", "감사위원"],
    "재무": ["재정", "회계", "재무상태", "재무제표"],
    "회계": ["재무", "부기", "회계처리", "회계기준"],
    "부채": ["빚", "차입금", "부채비율", "채무"],
    "자산": ["재산", "자산가치", "유형자산", "무형자산"],
    "수익": ["이익", "소득", "수입", "영업수익"],
    "이익": ["수익", "소득", "이윤", "순이익"],
    "손실": ["결손", "적자", "영업손실", "손실금"],

    # ── 높임말 / 약어 매핑 ────────────────────────────────────────────────
    "소송위": ["소송대리인", "변호사", "법률대리인"],
    "피고인": ["피고", "피의자", "수사대상"],
    "원고인": ["원고", "청구인", "제소자"],
    "법원": ["재판소", "재판부", "법정"],
    "검사": ["검찰", "공소자", "수사관"],
    "판사": ["재판관", "재판장", "수석판사"],
    "법률": ["법", "법령", "법규", "법률조항"],
    "법령": ["법률", "법", "규정", "법령집"],
    "규제": ["통제", "감독", "규제조치", "규제법"],
    "감독": ["규제", "감시", "관리감독", "감독기관"],
    "처분": ["조치", "행정처분", "제재", "제재처분"],
    "제재": ["처벌", "처분", "벌칙", "제재조치"],
    "벌칙": ["제재", "처벌", "벌금", "과태료"],
    "벌금": ["과태료", "벌칙", "처벌금"],
    "과태료": ["벌금", "부과금", "과징금"],
}

# 역방향 인덱스: 동의어 → 원본 단어 (빠른 룩업용)
_REVERSE_SYNONYM_INDEX: dict[str, list[str]] = {}
for _term, _syns in KOREAN_SYNONYM_DICT.items():
    _REVERSE_SYNONYM_INDEX.setdefault(_term, []).append(_term)
    for _syn in _syns:
        _REVERSE_SYNONYM_INDEX.setdefault(_syn, []).append(_term)
        _REVERSE_SYNONYM_INDEX[_syn].extend(
            s for s in _syns if s != _syn and s not in _REVERSE_SYNONYM_INDEX[_syn]
        )

# 한국 법률 용어 감지용 정규식 패턴
_KOREAN_LEGAL_TERMS = re.compile(
    r"(" + "|".join(re.escape(t) for t in KOREAN_SYNONYM_DICT.keys()) + r")"
)


# =========================================================================== #
# 쿼리 확장기 메인 클래스
# =========================================================================== #

class QueryExpander:
    """쿼리 확장기 — 검색 품질 향상을 위해 사용자 질문을 확장.

    사용법:
        expander = QueryExpander()
        result = expander.expand_query("소유권 이전 등기", strategy=QueryExpansionStrategy.AUTO)
        # result.expanded_queries → ["소유권 이전 등기", "권리 이전 등기", ...]
    """

    def __init__(self) -> None:
        self._llm = get_llm_client()

    # ── 공개 메서드 ──────────────────────────────────────────────────────── #

    def expand_query(
        self,
        query: str,
        strategy: QueryExpansionStrategy = QueryExpansionStrategy.AUTO,
    ) -> ExpansionResult:
        """쿼리 확장 수행.

        Args:
            query: 원본 사용자 질문
            strategy: 확장 전략 (auto면 자동 감지)

        Returns:
            ExpansionResult: 확장된 질문 목록 + 메타데이터
        """
        if not query or not query.strip():
            return ExpansionResult(
                original_query=query,
                expanded_queries=[query] if query else [],
                strategy_used=QueryExpansionStrategy.NONE,
            )

        query = query.strip()

        # 전략 자동 선택
        if strategy == QueryExpansionStrategy.AUTO:
            strategy = self._detect_strategy(query)
            logger.info("쿼리 확장 자동 감지: '%s' → %s", query[:30], strategy.value)

        if strategy == QueryExpansionStrategy.NONE:
            return ExpansionResult(
                original_query=query,
                expanded_queries=[query],
                strategy_used=QueryExpansionStrategy.NONE,
            )

        if strategy == QueryExpansionStrategy.MULTI_QUERY:
            return self._expand_multi_query(query)
        elif strategy == QueryExpansionStrategy.HYDE:
            return self._expand_hyde(query)
        elif strategy == QueryExpansionStrategy.KOREAN_SYNONYMS:
            return self._expand_korean_synonyms(query)
        else:
            return ExpansionResult(
                original_query=query,
                expanded_queries=[query],
                strategy_used=QueryExpansionStrategy.NONE,
            )

    def expand_and_search(
        self,
        query: str,
        strategy: QueryExpansionStrategy = QueryExpansionStrategy.AUTO,
        mode=None,
        session_id: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> tuple[list[SearchHit], ExpansionResult]:
        """쿼리 확장 후 검색까지 한 번에 수행.

        확장된 각 질문으로 검색을 수행하고 결과를 병합(중복 제거)합니다.

        Args:
            query: 원본 사용자 질문
            strategy: 확장 전략
            mode: ChatMode (top-k 결정용)
            session_id: 세션 ID
            collection_name: 검색 대상 컬렉션 이름

        Returns:
            (merged_hits, expansion_result): 병합된 검색 결과 + 확장 메타데이터
        """
        from app.config import ChatMode
        from app.core.search import hybrid_search

        if mode is None:
            mode = ChatMode.FACT

        expansion = self.expand_query(query, strategy)

        if expansion.strategy_used == QueryExpansionStrategy.NONE:
            # 확장 없이 기존 검색만 수행
            result = hybrid_search(
                query=query,
                mode=mode,
                session_id=session_id,
                collection_name=collection_name,
            )
            return result.hits, expansion

        # HyDE: 가상 답변 임베딩으로 특수 검색
        if expansion.strategy_used == QueryExpansionStrategy.HYDE and expansion.hyde_embedding:
            hyde_result = self._search_with_hyde_embedding(
                expansion.hyde_embedding,
                mode=mode,
                collection_name=collection_name,
            )
            # 원본 쿼리로도 검색하여 결과 병합
            original_result = hybrid_search(
                query=query,
                mode=mode,
                session_id=session_id,
                collection_name=collection_name,
            )
            merged = self._merge_hits(hyde_result.hits, original_result.hits)
            return merged, expansion

        # Multi-Query / Korean Synonyms: 각 확장 질문으로 검색 후 병합
        all_hits: list[SearchHit] = []
        for expanded_q in expansion.expanded_queries:
            try:
                result = hybrid_search(
                    query=expanded_q,
                    mode=mode,
                    session_id=session_id,
                    collection_name=collection_name,
                )
                all_hits.extend(result.hits)
            except Exception as exc:
                logger.warning("확장 쿼리 검색 실패 ('%s'): %s", expanded_q[:30], exc)

        merged = self._merge_hits(all_hits)
        return merged, expansion

    # ── 전략별 구현 ───────────────────────────────────────────────────────── #

    def _expand_multi_query(self, query: str) -> ExpansionResult:
        """Multi-Query Expansion: LLM이 3-5개 질문 변형 생성.

        프롬프트로 LLM에 질문 변형을 요청하고,
        파싱하여 원본 질문과 함께 반환합니다.
        """
        prompt = self._build_multi_query_prompt(query)

        try:
            response = self._call_llm(prompt)
            variations = self._parse_query_variations(response, query)
        except Exception as exc:
            logger.warning("Multi-Query 확장 실패, 원본 질문만 사용: %s", exc)
            variations = [query]

        # 원본 질문을 항상 첫 번째에 포함
        if query not in variations:
            variations.insert(0, query)

        logger.info(
            "Multi-Query 확장: '%s' → %d개 변형",
            query[:30], len(variations),
        )

        return ExpansionResult(
            original_query=query,
            expanded_queries=variations,
            strategy_used=QueryExpansionStrategy.MULTI_QUERY,
        )

    def _expand_hyde(self, query: str) -> ExpansionResult:
        """HyDE (Hypothetical Document Embedding): LLM이 가상 답변 생성 후 임베딩.

        LLM으로 가상 답변을 생성하고, 그 답변의 임베딩으로 검색합니다.
        문서의 언어 스타일과 더 가까운 임베딩을 얻을 수 있습니다.
        """
        prompt = self._build_hyde_prompt(query)

        try:
            hyde_answer = self._call_llm(prompt)
            if not hyde_answer or not hyde_answer.strip():
                raise ValueError("HyDE: LLM 응답이 비어있음")

            hyde_answer = hyde_answer.strip()

            # 가상 답변 임베딩 생성
            embedding_provider = get_embedding_provider()
            embedding_result: EmbeddingResult = embedding_provider.encode([hyde_answer])

            if not embedding_result.dense:
                raise ValueError("HyDE: 임베딩 결과 없음")

            hyde_embedding = embedding_result.dense[0]

        except Exception as exc:
            logger.warning("HyDE 확장 실패, 원본 질문만 사용: %s", exc)
            return ExpansionResult(
                original_query=query,
                expanded_queries=[query],
                strategy_used=QueryExpansionStrategy.NONE,
            )

        logger.info(
            "HyDE 확장: '%s' → 가상 답변 %d자, 임베딩 차원 %d",
            query[:30], len(hyde_answer), len(hyde_embedding),
        )

        return ExpansionResult(
            original_query=query,
            expanded_queries=[query],  # HyDE는 질문 확장이 아닌 임베딩 교체
            strategy_used=QueryExpansionStrategy.HYDE,
            hyde_embedding=hyde_embedding,
            hyde_answer=hyde_answer,
        )

    def _expand_korean_synonyms(self, query: str) -> ExpansionResult:
        """Korean Synonym Expansion: 한국 법률/비즈니스 용어 동의어 확장.

        사전 기반으로 질문 내 용어의 동의어를 대체한 확장 질문들을 생성합니다.
        원본 질문을 항상 첫 번째에 포함합니다.
        """
        expanded_queries = [query]  # 원본 질문 항상 포함

        # 질문에서 매칭되는 용어 찾기
        matched_terms: dict[str, list[str]] = {}
        for term in KOREAN_SYNONYM_DICT:
            if term in query:
                matched_terms[term] = KOREAN_SYNONYM_DICT[term]

        if not matched_terms:
            logger.info("한국어 동의어 확장: 매칭 용어 없음 — 원본 질문만 사용")
            return ExpansionResult(
                original_query=query,
                expanded_queries=expanded_queries,
                strategy_used=QueryExpansionStrategy.KOREAN_SYNONYMS,
            )

        # 각 매칭 용어를 동의어로 교체한 변형 생성
        # 최대 5개까지만 생성 (너무 많으면 검색 부하 증가)
        for term, synonyms in matched_terms.items():
            for syn in synonyms[:2]:  # 각 용어당 최대 2개 동의어
                if syn != term and syn not in query:
                    expanded = query.replace(term, syn)
                    if expanded not in expanded_queries:
                        expanded_queries.append(expanded)

            # 너무 많으면 중단
            if len(expanded_queries) >= 5:
                break

        # 전체 동의어 조합으로 하나 더 (여러 용어가 동시에 매칭된 경우)
        if len(matched_terms) >= 2:
            combined = query
            for term in matched_terms:
                syns = matched_terms[term]
                if syns:
                    combined = combined.replace(term, syns[0])
            if combined != query and combined not in expanded_queries:
                expanded_queries.append(combined)

        logger.info(
            "한국어 동의어 확장: '%s' → %d개 변형 (매칭 용어: %s)",
            query[:30], len(expanded_queries), list(matched_terms.keys()),
        )

        return ExpansionResult(
            original_query=query,
            expanded_queries=expanded_queries,
            strategy_used=QueryExpansionStrategy.KOREAN_SYNONYMS,
        )

    # ── 자동 전략 감지 ────────────────────────────────────────────────────── #

    def _detect_strategy(self, query: str) -> QueryExpansionStrategy:
        """쿼리 특성에 따라 최적의 확장 전략 자동 선택.

        규칙:
        - 짧은 쿼리 (<10자) → HyDE (문맥 보강)
        - 한국 법률 용어 포함 → Korean Synonyms
        - 그 외 → Multi-Query (일반적인 질문 변형)
        - creative 모드용 질의는 NONE
        """
        # 한국 법률/비즈니스 용어 감지
        if _KOREAN_LEGAL_TERMS.search(query):
            return QueryExpansionStrategy.KOREAN_SYNONYMS

        # 짧은 쿼리 → HyDE
        if len(query) < 10:
            return QueryExpansionStrategy.HYDE

        # 기본 → Multi-Query
        return QueryExpansionStrategy.MULTI_QUERY

    # ── LLM 프롬프트 ──────────────────────────────────────────────────────── #

    @staticmethod
    def _build_multi_query_prompt(query: str) -> str:
        """Multi-Query 확장용 프롬프트."""
        return f"""당신은 한국어 검색 쿼리 확장 전문가입니다.
사용자의 질문을 다양한 관점에서 재표현하여, 원하는 정보를 더 잘 찾을 수 있도록
3개에서 5개의 변형된 질문을 생성하세요.

규칙:
1. 원본 질문의 의도를 유지하되, 다른 표현과 관련 용어를 사용하세요.
2. 법률/비즈니스 문서에서 자주 사용되는 용어를 포함하세요.
3. 각 변형은 한 줄로 작성하세요.
4. 번호나 불릿 마크 없이 각 질문을 새 줄에 작성하세요.
5. 한국어로만 작성하세요.

원본 질문: {query}

변형된 질문:"""

    @staticmethod
    def _build_hyde_prompt(query: str) -> str:
        """HyDE (Hypothetical Document Embedding) 프롬프트."""
        return f"""당신은 한국 법률 및 비즈니스 문서 전문가입니다.
다음 질문에 대해, 실제 문서에서 찾을 수 있을 법한 상세한 답변을 작성하세요.
이 답변은 실제 정보가 아닌 검색을 위한 가상 문서입니다.

규칙:
1. 전문적인 법률/비즈니스 용어를 사용하세요.
2. 구체적이고 상세하게 작성하세요 (3-5문장).
3. 한국어로만 작성하세요.
4. 실제 사실이 아닐 수 있지만, 문서에서 발견될 법한 형식과 내용을 갖추세요.

질문: {query}

가상 문서 답변:"""

    # ── LLM 호출 래퍼 ─────────────────────────────────────────────────────── #

    def _call_llm(self, prompt: str) -> str:
        """LLM 호출 — 기존 LLMClient의 generate_answer를 재사용.

        주의: generate_answer는 SearchHit을 필요로 하지만,
        쿼리 확장용으로는 빈 컨텍스트로 호출합니다.
        """
        # LLMClient.generate_answer 대신 저수준 API 직접 호출
        from app.models.provider import ProviderSettingsStore

        store = ProviderSettingsStore.get()
        active = store.get_active_llm_provider()

        messages = [
            {"role": "system", "content": "당신은 한국어 검색 쿼리 확장 전문가입니다. 간결하고 정확하게 답변하세요."},
            {"role": "user", "content": prompt},
        ]

        return self._llm._call_provider(active, messages, max_tokens=512) or ""

    # ── 응답 파싱 ─────────────────────────────────────────────────────────── #

    @staticmethod
    def _parse_query_variations(response: str, original_query: str) -> list[str]:
        """LLM 응답에서 질문 변형 목록을 파싱."""
        variations = []

        for line in response.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            # 번호 제거: "1. 질문" → "질문"
            line = re.sub(r"^(\d+[\.\)]\s*)", "", line)
            # 불릿 제거: "- 질문", "• 질문" → "질문"
            line = re.sub(r"^[\-\•\*\→]\s*", "", line)

            line = line.strip()
            if line and line != original_query and len(line) >= 2:
                variations.append(line)

        # 중복 제거 (순서 유지)
        seen = set()
        unique = []
        for v in variations:
            if v not in seen:
                seen.add(v)
                unique.append(v)

        return unique[:5] if unique else [original_query]

    # ── HyDE 전용 검색 ─────────────────────────────────────────────────────── #

    @staticmethod
    def _search_with_hyde_embedding(
        hyde_embedding: list[float],
        mode=None,
        collection_name: Optional[str] = None,
    ) -> SearchResult:
        """HyDE 임베딩으로 벡터 DB 검색 (원본 쿼리 임베딩 대신 사용)."""
        from app.config import ChatMode, get_settings
        from app.core.search import SearchResult, _get_top_k
        from app.core.vectordb import get_vector_db

        if mode is None:
            mode = ChatMode.FACT

        initial_k = _get_top_k(mode)

        vdb = get_vector_db()

        # HyDE 임베딩으로 dense 검색 (sparse는 HyDE에서 생성하지 않음)
        results = vdb.search(
            query_dense=hyde_embedding,
            query_sparse=None,
            limit=initial_k,
            collection_name=collection_name,
        )

        hits: list[SearchHit] = []
        for hit in results:
            payload = hit.payload
            hits.append(SearchHit(
                text=payload.get("text", ""),
                source=payload.get("source", "알 수 없음"),
                score=hit.score,
                chunk_index=payload.get("chunk_index"),
                page=payload.get("page"),
            ))

        return SearchResult(hits=hits, query="[HyDE]", mode=mode)

    # ── 결과 병합 (중복 제거) ──────────────────────────────────────────────── #

    @staticmethod
    def _merge_hits(*hit_lists: list[SearchHit]) -> list[SearchHit]:
        """여러 검색 결과를 점수 기준으로 병합하고 chunk 중복을 제거.

        같은 (source, chunk_index)를 가진 결과는 가장 높은 점수만 유지합니다.
        """
        seen: dict[tuple[str, Optional[int]], SearchHit] = {}

        for hits in hit_lists:
            if not hits:
                continue
            for hit in hits:
                # chunk_index가 없으면 text 앞부분으로 유사도 판단
                key = (hit.source, hit.chunk_index) if hit.chunk_index is not None else (hit.source, hash(hit.text[:100]))
                if key not in seen or hit.score > seen[key].score:
                    seen[key] = hit

        # 점수 내림차순 정렬
        merged = sorted(seen.values(), key=lambda h: h.score, reverse=True)
        return merged


# =========================================================================== #
# 싱글톤
# =========================================================================== #

_query_expander: Optional[QueryExpander] = None


def get_query_expander() -> QueryExpander:
    """QueryExpander 싱글톤 인스턴스 반환."""
    global _query_expander
    if _query_expander is None:
        _query_expander = QueryExpander()
    return _query_expander


def reset_query_expander() -> None:
    """싱글톤 인스턴스 초기화 (설정 변경 시 사용)."""
    global _query_expander
    _query_expander = None