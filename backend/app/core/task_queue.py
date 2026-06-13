"""mAI-Brain — 인메모리 비동기 태스크 큐

FastAPI BackgroundTasks + SSE 스트리밍을 위한 경량 태스크 관리.
Celery 없이도 업로드 즉시 응답 + 진행률 실시간 스트리밍을 제공합니다.

설계:
- TaskQueue 싱글톤이 태스크 상태/진행률을 인메모리로 관리
- asyncio.Queue 기반으로 SSE 컨슈머에게 진행률 이벤트를 브로드캐스트
- 기존 IndexingTracker와 병행 사용 (후방 호환성)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """태스크 처리 상태"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskResult:
    """태스크 결과 데이터 클래스"""
    id: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0  # 0-100
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    # 각 태스크별 SSE 구독자 큐
    _event_queue: Optional[asyncio.Queue] = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """JSON 직렬화용 dict 변환"""
        return {
            "id": self.id,
            "status": self.status.value,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class TaskQueue:
    """인메모리 태스크 큐 — 싱글톤으로 사용.

    - add_task(): 새 태스크 생성 (PENDING 상태)
    - get_task(): 태스크 상태 조회
    - update_progress(): 진행률 업데이트 (0-100)
    - complete_task(): 완료 처리
    - fail_task(): 실패 처리
    - subscribe(): SSE 스트리밍용 asyncio.Queue 구독
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskResult] = {}
        self._lock = asyncio.Lock() if __debug__ else None

    def add_task(self, task_id: Optional[str] = None) -> TaskResult:
        """새 태스크를 생성하고 PENDING 상태로 등록.

        Args:
            task_id: 명시적 ID (없으면 UUID 자동 생성)

        Returns:
            TaskResult: 생성된 태스크 객체
        """
        if task_id is None:
            task_id = f"task-{uuid.uuid4().hex[:12]}"

        task = TaskResult(
            id=task_id,
            status=TaskStatus.PENDING,
            progress=0,
            _event_queue=asyncio.Queue(maxsize=64),
        )
        self._tasks[task_id] = task
        logger.info("태스크 생성: %s", task_id)
        return task

    def get_task(self, task_id: str) -> Optional[TaskResult]:
        """태스크 상태 조회"""
        return self._tasks.get(task_id)

    def update_progress(self, task_id: str, progress: int, message: str = "") -> bool:
        """태스크 진행률 업데이트.

        Args:
            task_id: 태스크 ID
            progress: 진행률 (0-100)
            message: 진행 상태 메시지 (선택)

        Returns:
            bool: 업데이트 성공 여부
        """
        task = self._tasks.get(task_id)
        if task is None:
            return False

        task.progress = max(0, min(100, progress))
        task.status = TaskStatus.PROCESSING

        # SSE 이벤트 발행
        self._publish_event(task_id, {
            "type": "progress",
            "progress": task.progress,
            "message": message,
        })
        return True

    def complete_task(self, task_id: str, result: Optional[dict[str, Any]] = None) -> bool:
        """태스크 완료 처리.

        Args:
            task_id: 태스크 ID
            result: 완료 결과 데이터 (선택)

        Returns:
            bool: 완료 처리 성공 여부
        """
        task = self._tasks.get(task_id)
        if task is None:
            return False

        task.status = TaskStatus.COMPLETED
        task.progress = 100
        task.result = result
        task.completed_at = datetime.now(timezone.utc)

        # SSE 완료 이벤트 발행
        self._publish_event(task_id, {
            "type": "completed",
            "progress": 100,
            "result": result,
        })
        return True

    def fail_task(self, task_id: str, error: str) -> bool:
        """태스크 실패 처리.

        Args:
            task_id: 태스크 ID
            error: 에러 메시지

        Returns:
            bool: 실패 처리 성공 여부
        """
        task = self._tasks.get(task_id)
        if task is None:
            return False

        task.status = TaskStatus.FAILED
        task.error = error
        task.completed_at = datetime.now(timezone.utc)

        # SSE 실패 이벤트 발행
        self._publish_event(task_id, {
            "type": "failed",
            "progress": task.progress,
            "error": error,
        })
        return True

    def subscribe(self, task_id: str) -> Optional[asyncio.Queue]:
        """SSE 스트리밍을 위한 이벤트 큐 구독.

        Returns:
            asyncio.Queue: 이벤트를 수신할 큐. 태스크가 없으면 None.
        """
        task = self._tasks.get(task_id)
        if task is None:
            return None

        # 새 구독자 큐 생성 (각 SSE 연결마다 독립)
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)

        # 즉시 현재 상태 이벤트 발행 (초기 상태 전송)
        current_status = {
            "type": task.status.value,
            "progress": task.progress,
        }
        if task.result:
            current_status["result"] = task.result
        if task.error:
            current_status["error"] = task.error

        try:
            queue.put_nowait(current_status)
        except asyncio.QueueFull:
            pass

        # 태스크의 메인 큐에 구독자 큐를 등록하지 않고,
        # 간단하게 _event_queue를 통해 브로드캐스트
        # (단일 구독자 패턴 — SSE는 보통 1연결)
        task._event_queue = queue
        return queue

    def _publish_event(self, task_id: str, event: dict[str, Any]) -> None:
        """태스크의 이벤트 큐에 이벤트를 발행.

        현재는 단일 SSE 연결을 가정하여 태스크당 하나의 큐만 관리.
        다중 SSE 연결이 필요해지면 큐 리스트로 확장.
        """
        task = self._tasks.get(task_id)
        if task is None or task._event_queue is None:
            return

        try:
            task._event_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("태스크 %s 이벤트 큐 가득 — 이벤트 드랍", task_id)

    def list_tasks(self) -> list[TaskResult]:
        """모든 태스크 목록 반환"""
        return list(self._tasks.values())

    def cleanup_old_tasks(self, max_age_seconds: int = 3600) -> int:
        """완료/실패한 오래된 태스크 정리.

        Args:
            max_age_seconds: 최대 보관 시간 (초). 기본 1시간.

        Returns:
            int: 정리된 태스크 수
        """
        now = datetime.now(timezone.utc)
        to_remove = []

        for task_id, task in self._tasks.items():
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                if task.completed_at:
                    age = (now - task.completed_at).total_seconds()
                    if age > max_age_seconds:
                        to_remove.append(task_id)

        for task_id in to_remove:
            del self._tasks[task_id]

        if to_remove:
            logger.info("오래된 태스크 %d개 정리", len(to_remove))
        return len(to_remove)


# ── 싱글톤 ────────────────────────────────────────────────────────────────

_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    """TaskQueue 싱글톤 반환"""
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue