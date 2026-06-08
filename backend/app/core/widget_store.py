"""mAI-Brain — 위젯 설정 저장소

JSON 파일 기반 위젯 설정 영속화.
"""

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models.widget import WidgetConfig, WidgetConfigCreate, WidgetConfigUpdate

# ── 데이터 디렉토리 ──────────────────────────────────────────────────────

WIDGETS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "widgets"
WIDGETS_DIR.mkdir(parents=True, exist_ok=True)


class WidgetStore:
    """JSON 파일 기반 위젯 설정 저장소"""

    def __init__(self, data_dir: Path = WIDGETS_DIR):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._widgets: dict[str, WidgetConfig] = {}
        self._load()

    def _load(self):
        """디스크에서 위젯 설정 로드"""
        data_file = self.data_dir / "widgets.json"
        if data_file.exists():
            raw = json.loads(data_file.read_text(encoding="utf-8"))
            self._widgets = {k: WidgetConfig(**v) for k, v in raw.items()}

    def _save(self):
        """위젯 설정을 디스크에 저장"""
        data_file = self.data_dir / "widgets.json"
        raw = {k: v.model_dump() for k, v in self._widgets.items()}
        data_file.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_widgets(self) -> list[WidgetConfig]:
        return list(self._widgets.values())

    def get_widget(self, widget_id: str) -> Optional[WidgetConfig]:
        return self._widgets.get(widget_id)

    def create_widget(self, data: WidgetConfigCreate) -> WidgetConfig:
        widget_id = secrets.token_hex(8)
        widget = WidgetConfig(
            id=widget_id,
            **data.model_dump(),
        )
        self._widgets[widget_id] = widget
        self._save()
        return widget

    def update_widget(self, widget_id: str, data: WidgetConfigUpdate) -> Optional[WidgetConfig]:
        widget = self._widgets.get(widget_id)
        if not widget:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(widget, key, value)
        widget.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return widget

    def delete_widget(self, widget_id: str) -> bool:
        if widget_id in self._widgets:
            del self._widgets[widget_id]
            self._save()
            return True
        return False

    def validate_origin(self, widget_id: str, origin: str) -> bool:
        """오리진이 위젯의 allowed_origins에 있는지 확인"""
        widget = self._widgets.get(widget_id)
        if not widget:
            return False
        return origin in widget.allowed_origins


# ── 싱글턴 ──────────────────────────────────────────────────────────────

_store: Optional[WidgetStore] = None


def get_widget_store() -> WidgetStore:
    global _store
    if _store is None:
        _store = WidgetStore()
    return _store