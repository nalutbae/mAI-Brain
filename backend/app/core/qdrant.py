"""mAI-Brain AI 챗봇 — Qdrant 컬렉션 관리

Qdrant 벡터 DB와의 상호작용을 담당합니다.
- 컬렉션 생성 (dense + sparse 인덱스)
- 포인트 upsert (청크 인덱싱)
- 소스별 삭제 (재업로드 시)
- 하이브리드 검색 (dense + sparse RRF 융합)
"""

from typing import Any

from qdrant_client import QdrantClient, models


class QdrantManager:
    """Qdrant 벡터 DB 관리자

    - dense 벡터: bge-m3 임베딩 (1024차원)
    - sparse 벡터: 키워드 매칭 (BM25-like)
    """

    # 컬렉션 설정 — 임베딩 프로바이더에 따라 차원 자동 감지
    VECTOR_SIZE_LOCAL = 1024   # bge-m3 dense 차원
    VECTOR_SIZE_OPENAI = 1536  # OpenAI text-embedding-3-small 차원
    COLLECTION_NAME = "mai_brain_documents"

    @property
    def vector_size(self) -> int:
        """현재 임베딩 프로바이더에 맞는 dense 벡터 차원 반환."""
        try:
            from app.config import get_settings, EmbeddingProviderType
            settings = get_settings()
            if settings.embedding_provider == EmbeddingProviderType.API:
                # provider별 차원
                provider = settings.embedding_api_provider or "openai"
                if provider == "jina":
                    return 1024
                return self.VECTOR_SIZE_OPENAI
            elif settings.embedding_provider == EmbeddingProviderType.OLLAMA:
                return settings.ollama_embedding_dim
        except Exception:
            pass
        return self.VECTOR_SIZE_LOCAL

    def __init__(self):
        """Qdrant 클라이언트 초기화"""
        from app.config import get_settings

        settings = get_settings()
        self.client = QdrantClient(url=settings.qdrant_url)
        self.collection_name = settings.qdrant_collection_name

    def init_collection(self) -> None:
        """컬렉션 생성 (dense + sparse 인덱스)"""
        existing = self.collection_exists()

        if existing:
            print(f"Collection '{self.collection_name}' already exists")
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                "dense": models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(
                    index=models.SparseIndexParams(
                        on_disk=True,  # 대용량 데이터를 위해 디스크 인덱싱
                    )
                )
            },
            # 메타데이터 인덱싱 - 소스별 빠른 삭제
            optimizers_config=models.OptimizersConfigDiff(
                indexing_threshold=20000,  # 20,000 포인트 이상 인덱싱 시작
            ),
            replication_factor=1,
        )

        print(f"Collection '{self.collection_name}' created successfully")

    def upsert_points(self, points: list[models.PointStruct]) -> None:
        """포인트 대량 삽입/업데이트

        Args:
            points: PointStruct 리스트 (각각 dense, sparse, payload 포함)
        """
        if not points:
            return

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )

        print(f"Upserted {len(points)} points to '{self.collection_name}'")

    def delete_by_source(self, source: str) -> None:
        """소스(파일명)로 기존 문서 삭제 (재업로드 시)

        Args:
            source: 파일명 (예: "연설문1.pdf")
        """
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key="source",
                        match=models.MatchValue(value=source),
                    )
                ]
            ),
        )

        print(f"Deleted all points with source='{source}'")

    def search(
        self,
        query_dense: list[float],
        query_sparse: dict[int, float],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """하이브리드 검색 (dense + sparse RRF 융합)

        Qdrant의 FusionQuery(RRF)를 사용하여 네이티브 하이브리드 검색 수행

        Args:
            query_dense: 질문의 dense 벡터 [float]
            query_sparse: 질문의 sparse 벡터 {token_id: weight}
            limit: 반환할 결과 수

        Returns:
            결과 리스트: [{"score": float, "payload": dict}, ...]
        """
        # Prefetch 쿼리 설정 - dense와 sparse 병렬 검색
        prefetch = [
            # Dense 검색 (using 파라미터로 NamedVector 지정)
            models.Prefetch(
                query=query_dense,
                using="dense",
                limit=limit * 2,
            ),
            # Sparse 검색 (SparseVector 직접 전달)
            models.Prefetch(
                query=models.SparseVector(
                    indices=list(query_sparse.keys()),
                    values=list(query_sparse.values()),
                ),
                using="sparse",
                limit=limit * 2,
            ),
        ]

        # RRF 융합 쿼리
        fusion_query = models.FusionQuery(fusion=models.Fusion.RRF)

        # Qdrant 쿼리 실행
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=fusion_query,
            prefetch=prefetch,
            limit=limit,
            with_payload=True,
        )

        # 결과 포맷팅
        results = []
        for point in response.points:
            results.append(
                {
                    "score": point.score,
                    "payload": point.payload,
                }
            )

        return results

    def get_collection_info(self) -> dict[str, Any]:
        """컬렉션 정보 조회

        Returns:
            {"points_count": int, "status": str, "config": dict}
        """
        info = self.client.get_collection(self.collection_name)

        return {
            "points_count": info.points_count,
            "status": info.status,
            "config": info.config.params,
        }

    def collection_exists(self) -> bool:
        """컬렉션 존재 여부 확인"""
        return self.client.collection_exists(self.collection_name)

    def health_check(self) -> bool:
        """Qdrant 연결 상태 확인"""
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False

    def list_documents(self) -> list[dict[str, Any]]:
        """Qdrant에서 실제 문서 목록 조회.

        payload의 document_id와 source를 기준으로 고유 문서를 그룹화하고,
        각 문서의 청크 수를 계산합니다. IndexingTracker와 무관하게
        항상 최신 상태를 반환합니다.

        Returns:
            [{document_id, filename, status, total_chunks}, ...]
        """
        from collections import defaultdict

        # 고유 문서별 청크 수 집계
        doc_chunks: dict[str, dict] = {}  # document_id → {filename, chunks}
        offset = None

        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=250,
                with_payload=True,
                with_vectors=False,
                offset=offset,
            )
            for point in points:
                payload = point.payload or {}
                doc_id = payload.get("document_id", "")
                source = payload.get("source", "unknown")
                if not doc_id:
                    continue
                if doc_id not in doc_chunks:
                    doc_chunks[doc_id] = {
                        "document_id": doc_id,
                        "filename": source,
                        "total_chunks": 0,
                    }
                doc_chunks[doc_id]["total_chunks"] += 1

            if offset is None or len(points) == 0:
                break

        # completed 상태로 반환 (Qdrant에 있으면 인덱싱 완료된 것)
        return [
            {
                "document_id": v["document_id"],
                "filename": v["filename"],
                "status": "completed",
                "total_chunks": v["total_chunks"],
            }
            for v in sorted(doc_chunks.values(), key=lambda x: x["filename"])
        ]


# 전역 인스턴스 (싱글톤)
_qdrant_manager: QdrantManager | None = None


def get_qdrant() -> QdrantManager:
    """QdrantManager 싱글톤 인스턴스 반환"""
    global _qdrant_manager
    if _qdrant_manager is None:
        _qdrant_manager = QdrantManager()
    return _qdrant_manager