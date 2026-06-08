"""mAI-Brain — 벡터 DB 추상 인터페이스

VectorDBProvider 추상 인터페이스 기반:
- QdrantVectorDB: Qdrant 벡터 DB (dense + sparse RRF 하이브리드 검색)
- ChromaVectorDB: ChromaDB 벡터 DB (dense 검색, sparse 미지원)
- PGVectorDB: PostgreSQL + pgvector (dense 검색, sparse 미지원)

팩토리 함수 get_vector_db()가 config.vector_db에 따라
적절한 인스턴스를 반환.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import VectorDBType, get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass
class SearchHit:
    """벡터 DB 검색 결과 항목.

    모든 벡터 DB 프로바이더가 공통으로 반환하는 형태.
    """
    score: float
    payload: dict[str, Any]


@dataclass
class VectorDBInfo:
    """벡터 DB 컬렉션 정보."""
    points_count: int
    status: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class UpsertResult:
    """Upsert 작업 결과."""
    inserted_count: int


# ---------------------------------------------------------------------------
# 추상 인터페이스
# ---------------------------------------------------------------------------

class VectorDBProvider(ABC):
    """벡터 DB 제공자 추상 인터페이스.

    Qdrant/Chroma/PGVector 전환을 위한 추상화 계층.
    create_collection, upsert, search, delete, health_check 등의
    핵심 CRUD + 검색 오퍼레이션을 정의.
    """

    @abstractmethod
    def create_collection(self, dim: int) -> None:
        """컬렉션 생성 (존재하지 않을 때만).

        Args:
            dim: dense 벡터 차원 수
        """
        ...

    @abstractmethod
    def upsert(self, points: list[dict[str, Any]]) -> UpsertResult:
        """포인트 대량 삽입/업데이트.

        Args:
            points: 포인트 딕셔너리 리스트.
                각 딕셔너리는 최소 다음 키를 포함:
                - "id": str — 포인트 고유 ID
                - "vector": dict — {"dense": list[float], 선택 "sparse": dict}
                - "payload": dict — 메타데이터

        Returns:
            UpsertResult: 삽입된 포인트 수
        """
        ...

    @abstractmethod
    def search(
        self,
        query_dense: list[float],
        query_sparse: Optional[dict[str, float]] = None,
        limit: int = 5,
        collection_name: Optional[str] = None,
    ) -> list[SearchHit]:
        """벡터 검색.

        Args:
            query_dense: 질의 dense 벡터
            query_sparse: 질의 sparse 벡터 (지원 시, {토큰: 가중치})
            limit: 반환할 결과 수
            collection_name: 검색 대상 컬렉션 이름 (None이면 기본 컬렉션)

        Returns:
            검색 결과 리스트
        """
        ...

    @abstractmethod
    def delete_by_source(self, source: str) -> int:
        """소스(파일명)로 기존 문서 삭제 (재업로드 시).

        Args:
            source: 파일명 (예: "연설문1.pdf")

        Returns:
            삭제된 포인트 수 (지원하지 않는 DB는 0)
        """
        ...

    @abstractmethod
    def collection_exists(self) -> bool:
        """컬렉션 존재 여부 확인."""
        ...

    @abstractmethod
    def get_info(self) -> VectorDBInfo:
        """컬렉션 정보 조회."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """DB 연결 상태 확인."""
        ...

    @abstractmethod
    def list_documents(self) -> list[dict[str, Any]]:
        """컬렉션 내 고유 문서 목록 조회.

        Returns:
            [{document_id, filename, status, total_chunks}, ...]
        """
        ...

    @abstractmethod
    def supports_sparse(self) -> bool:
        """sparse 벡터 검색 지원 여부."""
        ...


# ---------------------------------------------------------------------------
# Qdrant 구현체
# ---------------------------------------------------------------------------

class QdrantVectorDB(VectorDBProvider):
    """Qdrant 벡터 DB 관리자.

    - dense 벡터: 임베딩 프로바이더에 따라 차원 결정
    - sparse 벡터: 키워드 매칭 (BM25-like)
    - RRF 하이브리드 검색 지원
    """

    def __init__(self) -> None:
        from qdrant_client import QdrantClient, models  # noqa: PLC0415

        settings = get_settings()
        self._client = QdrantClient(url=settings.qdrant_url)
        self._collection_name = settings.qdrant_collection_name
        self._models = models
        logger.info(
            "QdrantVectorDB 초기화: url=%s, collection=%s",
            settings.qdrant_url, self._collection_name,
        )

    @property
    def client(self):
        """Qdrant 클라이언트 직접 접근 (하위 호환성)."""
        return self._client

    @property
    def collection_name(self) -> str:
        """컬렉션 이름 직접 접근 (하위 호환성)."""
        return self._collection_name

    def _collection(self, override: Optional[str] = None) -> str:
        """실제 사용할 컬렉션 이름 반환."""
        return override or self._collection_name

    def _vector_size(self) -> int:
        """현재 임베딩 프로바이더에 맞는 dense 벡터 차원 반환."""
        from app.config import EmbeddingProviderType  # noqa: PLC0415

        settings = get_settings()
        if settings.embedding_provider == EmbeddingProviderType.API:
            provider = settings.embedding_api_provider or "openai"
            if provider == "jina":
                return 1024
            return 1536  # OpenAI text-embedding-3-small
        elif settings.embedding_provider == EmbeddingProviderType.OLLAMA:
            return settings.ollama_embedding_dim
        return 1024  # bge-m3

    def create_collection(self, dim: int = 0) -> None:
        """컬렉션 생성 (dense + sparse 인덱스)."""
        if self.collection_exists():
            logger.info("컬렉션 '%s' 이미 존재", self._collection_name)
            return

        vector_size = dim or self._vector_size()
        self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config={
                "dense": self._models.VectorParams(
                    size=vector_size,
                    distance=self._models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                "sparse": self._models.SparseVectorParams(
                    index=self._models.SparseIndexParams(
                        on_disk=True,
                    )
                )
            },
            optimizers_config=self._models.OptimizersConfigDiff(
                indexing_threshold=20000,
            ),
            replication_factor=1,
        )
        logger.info("컬렉션 '%s' 생성 완료 (dim=%d)", self._collection_name, vector_size)

    def upsert(self, points: list[dict[str, Any]]) -> UpsertResult:
        """포인트 대량 삽입/업데이트."""
        if not points:
            return UpsertResult(inserted_count=0)

        # dict → Qdrant PointStruct 변환
        from app.ingestion.indexer import _token_to_index  # noqa: PLC0415

        qdrant_points = []
        for p in points:
            vector_data = p["vector"]
            dense_vec = vector_data["dense"]

            # sparse 벡터 변환 (있는 경우)
            if "sparse" in vector_data and vector_data["sparse"]:
                sparse_dict = vector_data["sparse"]
                sparse_vec = self._models.SparseVector(
                    indices=[_token_to_index(k) for k in sparse_dict.keys()],
                    values=list(sparse_dict.values()),
                )
                vector = {"dense": dense_vec, "sparse": sparse_vec}
            else:
                vector = {"dense": dense_vec}

            qdrant_points.append(self._models.PointStruct(
                id=p["id"],
                vector=vector,
                payload=p.get("payload", {}),
            ))

        self._client.upsert(
            collection_name=self._collection_name,
            points=qdrant_points,
        )
        logger.info("Upsert: %d 포인트 → '%s'", len(qdrant_points), self._collection_name)
        return UpsertResult(inserted_count=len(qdrant_points))

    def search(
        self,
        query_dense: list[float],
        query_sparse: Optional[dict[str, float]] = None,
        limit: int = 5,
        collection_name: Optional[str] = None,
    ) -> list[SearchHit]:
        """하이브리드 검색 (dense + sparse RRF 융합).

        sparse가 제공되면 RRF 하이브리드, 아니면 dense-only 검색.

        Args:
            collection_name: 검색 대상 컬렉션 이름 (None이면 기본 컬렉션)
        """
        from app.ingestion.indexer import _token_to_index  # noqa: PLC0415

        coll = self._collection(collection_name)
        has_sparse = query_sparse is not None

        if has_sparse:
            # 하이브리드 검색 (dense + sparse RRF 융합)
            sparse_vec = self._models.SparseVector(
                indices=[_token_to_index(k) for k in query_sparse.keys()],
                values=list(query_sparse.values()),
            )
            prefetch = [
                self._models.Prefetch(
                    query=query_dense,
                    using="dense",
                    limit=limit * 2,
                ),
                self._models.Prefetch(
                    query=sparse_vec,
                    using="sparse",
                    limit=limit * 2,
                ),
            ]
            fusion_query = self._models.FusionQuery(fusion=self._models.Fusion.RRF)
            response = self._client.query_points(
                collection_name=coll,
                query=fusion_query,
                prefetch=prefetch,
                limit=limit,
                with_payload=True,
            )
        else:
            # dense-only 검색
            response = self._client.query_points(
                collection_name=coll,
                query=query_dense,
                using="dense",
                limit=limit,
                with_payload=True,
            )

        return [
            SearchHit(score=point.score, payload=point.payload or {})
            for point in response.points
        ]

    def delete_by_source(self, source: str) -> int:
        """소스(파일명)로 기존 문서 삭제."""
        # 삭제 전 포인트 수 조회 (정확한 카운트용)
        count_result = self._client.count(
            collection_name=self._collection_name,
            count_filter=self._models.Filter(
                must=[
                    self._models.FieldCondition(
                        key="source",
                        match=self._models.MatchValue(value=source),
                    )
                ]
            ),
        )
        deleted_count = count_result.count

        self._client.delete(
            collection_name=self._collection_name,
            points_selector=self._models.Filter(
                must=[
                    self._models.FieldCondition(
                        key="source",
                        match=self._models.MatchValue(value=source),
                    )
                ]
            ),
        )
        logger.info("소스 '%s' 포인트 %d개 삭제", source, deleted_count)
        return deleted_count

    def collection_exists(self) -> bool:
        """컬렉션 존재 여부 확인."""
        return self._client.collection_exists(self._collection_name)

    def get_info(self) -> VectorDBInfo:
        """컬렉션 정보 조회."""
        info = self._client.get_collection(self._collection_name)
        return VectorDBInfo(
            points_count=info.points_count,
            status=info.status,
            config=info.config.params if hasattr(info, 'config') else {},
        )

    def health_check(self) -> bool:
        """Qdrant 연결 상태 확인."""
        try:
            self._client.get_collections()
            return True
        except Exception:
            return False

    def list_documents(self) -> list[dict[str, Any]]:
        """Qdrant에서 실제 문서 목록 조회."""
        from collections import defaultdict  # noqa: PLC0415

        doc_chunks: dict[str, dict] = {}
        offset = None

        while True:
            points, offset = self._client.scroll(
                collection_name=self._collection_name,
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

        return [
            {
                "document_id": v["document_id"],
                "filename": v["filename"],
                "status": "completed",
                "total_chunks": v["total_chunks"],
            }
            for v in sorted(doc_chunks.values(), key=lambda x: x["filename"])
        ]

    def supports_sparse(self) -> bool:
        """Qdrant는 sparse 벡터 검색을 지원합니다."""
        return True


# ---------------------------------------------------------------------------
# ChromaDB 구현체
# ---------------------------------------------------------------------------

class ChromaVectorDB(VectorDBProvider):
    """ChromaDB 벡터 DB 관리자.

    - dense 벡터만 지원 (sparse 미지원)
    - 로컬 실행 (기본) 또는 Chroma 서버 모드
    - 경량 벡터 DB — 개발/소규모 배포에 적합
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._collection_name = settings.qdrant_collection_name  # 동일 설정 재사용
        self._chroma_dir = settings.chroma_persist_dir
        self._client = None
        self._collection = None
        logger.info(
            "ChromaVectorDB 초기화: persist_dir=%s, collection=%s",
            self._chroma_dir, self._collection_name,
        )

    def _get_client(self):
        """지연 초기화 — ChromaDB는 선택 의존성."""
        if self._client is not None:
            return self._client

        try:
            import chromadb  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "chromadb 패키지가 필요합니다: pip install chromadb"
            ) from exc

        settings = get_settings()
        if settings.chroma_host:
            # 서버 모드
            self._client = chromadb.HttpClient(
                host=settings.chroma_host,
                port=settings.chroma_port,
            )
        else:
            # 로컬 모드
            self._client = chromadb.PersistentClient(path=self._chroma_dir)
        return self._client

    def _get_collection(self, collection_name: Optional[str] = None):
        """컬렉션 지연 로드."""
        coll_name = collection_name or self._collection_name
        if self._collection is not None and collection_name is None:
            return self._collection

        client = self._get_client()
        self._collection = client.get_or_create_collection(
            name=coll_name,
            metadata={"hnsw:space": "cosine"},
        )
        return self._collection

    def _get_dim(self) -> int:
        """임베딩 프로바이더에서 차원 수 결정."""
        from app.config import EmbeddingProviderType  # noqa: PLC0415

        settings = get_settings()
        if settings.embedding_provider == EmbeddingProviderType.API:
            provider = settings.embedding_api_provider or "openai"
            if provider == "jina":
                return 1024
            return 1536
        elif settings.embedding_provider == EmbeddingProviderType.OLLAMA:
            return settings.ollama_embedding_dim
        return 1024  # bge-m3

    def create_collection(self, dim: int = 0) -> None:
        """컬렉션 생성 (ChromaDB는 get_or_create이므로 항상 성공)."""
        # ChromaDB는 get_or_create이므로 _get_collection()에서 처리
        self._get_collection()
        logger.info("ChromaDB 컬렉션 '%s' 준비 완료", self._collection_name)

    def upsert(self, points: list[dict[str, Any]]) -> UpsertResult:
        """포인트 대량 삽입/업데이트."""
        if not points:
            return UpsertResult(inserted_count=0)

        collection = self._get_collection()

        ids = [p["id"] for p in points]
        embeddings = [p["vector"]["dense"] for p in points]
        metadatas = [p.get("payload", {}) for p in points]
        documents = [p.get("payload", {}).get("text", "") for p in points]

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )
        logger.info("ChromaDB upsert: %d 포인트 → '%s'", len(ids), self._collection_name)
        return UpsertResult(inserted_count=len(ids))

    def search(
        self,
        query_dense: list[float],
        query_sparse: Optional[dict[str, float]] = None,
        limit: int = 5,
        collection_name: Optional[str] = None,
    ) -> list[SearchHit]:
        """dense 검색 (ChromaDB는 sparse 미지원).

        Args:
            collection_name: 검색 대상 컬렉션 이름 (None이면 기본 컬렉션)
        """
        collection = self._get_collection(collection_name)
        results = collection.query(
            query_embeddings=[query_dense],
            n_results=limit,
            include=["metadatas", "distances", "documents"],
        )

        hits = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                # Cosine distance → similarity score (1 - distance)
                distance = results["distances"][0][i] if results["distances"] else 0.0
                score = max(0.0, 1.0 - distance)
                payload = results["metadatas"][0][i] if results["metadatas"] else {}
                # text를 payload에 추가 (ChromaDB는 documents에 별도 저장)
                if results["documents"] and results["documents"][0]:
                    payload["text"] = results["documents"][0][i]
                hits.append(SearchHit(score=score, payload=payload))

        return hits

    def delete_by_source(self, source: str) -> int:
        """소스(파일명)로 기존 문서 삭제."""
        collection = self._get_collection()

        # 소스 필터로 조회
        results = collection.get(
            where={"source": source},
            include=["metadatas"],
        )
        if not results["ids"]:
            return 0

        count = len(results["ids"])
        collection.delete(ids=results["ids"])
        logger.info("ChromaDB: 소스 '%s' 포인트 %d개 삭제", source, count)
        return count

    def collection_exists(self) -> bool:
        """컬렉션 존재 여부 확인."""
        try:
            self._get_collection()
            return True
        except Exception:
            return False

    def get_info(self) -> VectorDBInfo:
        """컬렉션 정보 조회."""
        collection = self._get_collection()
        count = collection.count()
        return VectorDBInfo(
            points_count=count,
            status="green",
            config={"engine": "chroma", "space": "cosine"},
        )

    def health_check(self) -> bool:
        """ChromaDB 연결 상태 확인."""
        try:
            self._get_client()
            return True
        except Exception:
            return False

    def list_documents(self) -> list[dict[str, Any]]:
        """ChromaDB에서 문서 목록 조회."""
        collection = self._get_collection()
        results = collection.get(include=["metadatas"])

        doc_chunks: dict[str, dict] = {}
        for i, meta in enumerate(results["metadatas"]):
            if not meta:
                continue
            doc_id = meta.get("document_id", "")
            source = meta.get("source", "unknown")
            if not doc_id:
                continue
            if doc_id not in doc_chunks:
                doc_chunks[doc_id] = {
                    "document_id": doc_id,
                    "filename": source,
                    "total_chunks": 0,
                }
            doc_chunks[doc_id]["total_chunks"] += 1

        return [
            {
                "document_id": v["document_id"],
                "filename": v["filename"],
                "status": "completed",
                "total_chunks": v["total_chunks"],
            }
            for v in sorted(doc_chunks.values(), key=lambda x: x["filename"])
        ]

    def supports_sparse(self) -> bool:
        """ChromaDB는 sparse 벡터를 지원하지 않습니다."""
        return False


# ---------------------------------------------------------------------------
# PGVector 구현체
# ---------------------------------------------------------------------------

class PGVectorDB(VectorDBProvider):
    """PostgreSQL + pgvector 벡터 DB 관리자.

    - dense 벡터만 지원 (sparse 미지원)
    - PostgreSQL 16+ 필요 (pgvector 확장)
    - 운영 환경에 적합 — ACID 트랜잭션, 백업/복구 용이
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._collection_name = settings.qdrant_collection_name  # 동일 설정 재사용
        self._pool = None
        logger.info(
            "PGVectorDB 초기화: dsn=%s, collection=%s",
            "***" if settings.pg_dsn else "(미설정)",
            self._collection_name,
        )

    def _coll(self, override: Optional[str] = None) -> str:
        """실제 사용할 컬렉션(테이블) 이름 반환."""
        return override or self._collection_name

    async def _get_pool(self):
        """비동기 커넥션 풀 지연 초기화."""
        if self._pool is not None:
            return self._pool

        try:
            import asyncpg  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "asyncpg 패키지가 필요합니다: pip install asyncpg"
            ) from exc

        settings = get_settings()
        self._pool = await asyncpg.create_pool(settings.pg_dsn, min_size=2, max_size=10)
        return self._pool

    def _get_conn_params(self) -> tuple:
        """psycopg2용 동기 연결 파라미터 파싱."""
        import re  # noqa: PLC0415

        settings = get_settings()
        dsn = settings.pg_dsn
        # DSN: postgresql://user:***@host:port/dbname
        match = re.match(
            r"postgresql://([^:***@]+)@([^:]+):(\d+)/(.+)",
            dsn,
        )
        if match:
            return match.groups()
        # Fallback: 키워드 파싱
        return ("postgres", "", "localhost", "5432", "mai_brain")

    def _get_sync_conn(self):
        """psycopg2 동기 연결 (인덱싱용)."""
        try:
            import psycopg2  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "psycopg2 패키지가 필요합니다: pip install psycopg2-binary"
            ) from exc

        settings = get_settings()
        return psycopg2.connect(settings.pg_dsn)

    def _ensure_table(self, cur, dim: int, collection_name: Optional[str] = None) -> None:
        """테이블 + 인덱스 생성 (존재하지 않을 때만)."""
        coll = self._coll(collection_name)
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {coll} (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                source TEXT NOT NULL,
                text TEXT NOT NULL,
                chunk_index INTEGER,
                page INTEGER,
                embedding vector({dim}),
                payload JSONB DEFAULT '{{}}'::jsonb
            );
        """)
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{coll}_source
            ON {coll} (source);
        """)
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{coll}_document_id
            ON {coll} (document_id);
        """)
        # HNSW 인덱스 — 코사인 거리
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{coll}_embedding
            ON {coll} USING hnsw (embedding vector_cosine_ops);
        """)

    def create_collection(self, dim: int = 0) -> None:
        """컬렉션(테이블) 생성."""
        vector_dim = dim or self._get_dim()
        conn = self._get_sync_conn()
        try:
            conn.autocommit = True
            cur = conn.cursor()
            self._ensure_table(cur, vector_dim)
            cur.close()
            logger.info("PGVector 테이블 '%s' 준비 완료 (dim=%d)", self._collection_name, vector_dim)
        finally:
            conn.close()

    def upsert(self, points: list[dict[str, Any]]) -> UpsertResult:
        """포인트 대량 삽입/업데이트."""
        if not points:
            return UpsertResult(inserted_count=0)

        conn = self._get_sync_conn()
        try:
            cur = conn.cursor()
            for p in points:
                payload = p.get("payload", {})
                dense_vec = p["vector"]["dense"]
                vec_str = "[" + ",".join(str(v) for v in dense_vec) + "]"

                cur.execute(
                    f"""
                    INSERT INTO {self._collection_name}
                        (id, document_id, source, text, chunk_index, page, embedding, payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        source = EXCLUDED.source,
                        text = EXCLUDED.text,
                        chunk_index = EXCLUDED.chunk_index,
                        page = EXCLUDED.page,
                        embedding = EXCLUDED.embedding,
                        payload = EXCLUDED.payload;
                    """,
                    (
                        p["id"],
                        payload.get("document_id", ""),
                        payload.get("source", ""),
                        payload.get("text", ""),
                        payload.get("chunk_index"),
                        payload.get("page"),
                        vec_str,
                        psycopg2.extras.Json(payload) if payload else "{}",
                    ),
                )
            conn.commit()
            logger.info("PGVector upsert: %d 포인트 → '%s'", len(points), self._collection_name)
            return UpsertResult(inserted_count=len(points))
        finally:
            conn.close()

    def search(
        self,
        query_dense: list[float],
        query_sparse: Optional[dict[str, float]] = None,
        limit: int = 5,
        collection_name: Optional[str] = None,
    ) -> list[SearchHit]:
        """dense 검색 (PGVector는 sparse 미지원, 코사인 유사도).

        Args:
            collection_name: 검색 대상 컬렉션(테이블) 이름 (None이면 기본)
        """
        coll = self._coll(collection_name)
        conn = self._get_sync_conn()
        try:
            vec_str = "[" + ",".join(str(v) for v in query_dense) + "]"
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT id, document_id, source, text, chunk_index, page,
                       1 - (embedding <=> %s::vector) AS score,
                       payload
                FROM {coll}
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
                """,
                (vec_str, vec_str, limit),
            )
            rows = cur.fetchall()

            hits = []
            for row in rows:
                payload = row[7] if row[7] else {}
                payload["document_id"] = row[1]
                payload["source"] = row[2]
                payload["text"] = row[3]
                if row[4] is not None:
                    payload["chunk_index"] = row[4]
                if row[5] is not None:
                    payload["page"] = row[5]
                hits.append(SearchHit(score=float(row[6]), payload=payload))

            return hits
        finally:
            conn.close()

    def delete_by_source(self, source: str) -> int:
        """소스(파일명)로 기존 문서 삭제."""
        conn = self._get_sync_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                f"SELECT COUNT(*) FROM {self._collection_name} WHERE source = %s;",
                (source,),
            )
            count = cur.fetchone()[0]
            cur.execute(
                f"DELETE FROM {self._collection_name} WHERE source = %s;",
                (source,),
            )
            conn.commit()
            logger.info("PGVector: 소스 '%s' 포인트 %d개 삭제", source, count)
            return count
        finally:
            conn.close()

    def collection_exists(self) -> bool:
        """테이블 존재 여부 확인."""
        conn = self._get_sync_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT EXISTS ("
                "SELECT FROM information_schema.tables "
                f"WHERE table_name = '{self._collection_name}'"
                ");"
            )
            return cur.fetchone()[0]
        finally:
            conn.close()

    def _get_dim(self) -> int:
        """임베딩 프로바이더에서 차원 수 결정."""
        from app.config import EmbeddingProviderType  # noqa: PLC0415

        settings = get_settings()
        if settings.embedding_provider == EmbeddingProviderType.API:
            provider = settings.embedding_api_provider or "openai"
            if provider == "jina":
                return 1024
            return 1536
        elif settings.embedding_provider == EmbeddingProviderType.OLLAMA:
            return settings.ollama_embedding_dim
        return 1024

    def get_info(self) -> VectorDBInfo:
        """컬렉션 정보 조회."""
        conn = self._get_sync_conn()
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {self._collection_name};")
            count = cur.fetchone()[0]
            return VectorDBInfo(
                points_count=count,
                status="green",
                config={"engine": "pgvector"},
            )
        finally:
            conn.close()

    def health_check(self) -> bool:
        """PostgreSQL 연결 상태 확인."""
        try:
            conn = self._get_sync_conn()
            conn.close()
            return True
        except Exception:
            return False

    def list_documents(self) -> list[dict[str, Any]]:
        """PGVector에서 문서 목록 조회."""
        conn = self._get_sync_conn()
        try:
            cur = conn.cursor()
            cur.execute(f"""
                SELECT document_id, source, COUNT(*) as chunk_count
                FROM {self._collection_name}
                GROUP BY document_id, source
                ORDER BY source;
            """)
            rows = cur.fetchall()
            return [
                {
                    "document_id": row[0],
                    "filename": row[1],
                    "status": "completed",
                    "total_chunks": row[2],
                }
                for row in rows
            ]
        finally:
            conn.close()

    def supports_sparse(self) -> bool:
        """PGVector는 sparse 벡터를 지원하지 않습니다."""
        return False


# ---------------------------------------------------------------------------
# 팩토리
# ---------------------------------------------------------------------------

_vdb_instance: Optional[VectorDBProvider] = None


def get_vector_db(force_new: bool = False) -> VectorDBProvider:
    """설정에 따라 적절한 VectorDBProvider 인스턴스 반환 (싱글톤).

    Args:
        force_new: True면 기존 인스턴스 무시하고 새로 생성 (테스트용).

    Returns:
        QdrantVectorDB, ChromaVectorDB, 또는 PGVectorDB 인스턴스.
    """
    global _vdb_instance

    if _vdb_instance is not None and not force_new:
        return _vdb_instance

    settings = get_settings()
    vdb_type = settings.vector_db

    if vdb_type == VectorDBType.QDRANT:
        _vdb_instance = QdrantVectorDB()
    elif vdb_type == VectorDBType.CHROMA:
        _vdb_instance = ChromaVectorDB()
    elif vdb_type == VectorDBType.PGVECTOR:
        _vdb_instance = PGVectorDB()
    else:
        raise ValueError(
            f"알 수 없는 VECTOR_DB: {vdb_type!r}  "
            "('qdrant', 'chroma', 'pgvector' 중 하나)"
        )

    return _vdb_instance


def reset_vector_db() -> None:
    """싱글톤 인스턴스 초기화 (테스트/설정 변경 시 사용)."""
    global _vdb_instance
    _vdb_instance = None
