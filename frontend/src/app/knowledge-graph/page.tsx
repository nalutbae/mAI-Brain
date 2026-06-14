"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchKGGraph,
  fetchKGStats,
  extractKnowledgeGraph,
  searchKGEntities,
  getDocuments,
  type GraphData,
  type KGStats,
  type EntitySearchResult,
  type Document,
} from "@/lib/api";

// ── 엔티티 타입 색상 매핑 ──────────────────────────────────────────────────
const TYPE_COLORS: Record<string, string> = {
  person: "#ef4444",
  organization: "#3b82f6",
  law_article: "#f59e0b",
  concept: "#8b5cf6",
  event: "#10b981",
  location: "#06b6d4",
  document: "#6366f1",
  technology: "#ec4899",
  role: "#14b8a6",
};

const TYPE_LABELS: Record<string, string> = {
  person: "인물",
  organization: "조직",
  law_article: "법률 조문",
  concept: "개념",
  event: "사건",
  location: "장소",
  document: "문서",
  technology: "기술",
  role: "직위",
};

// ── D3.js 스타일 force 그래프 (Canvas 기반) ──────────────────────────────────

interface SimNode {
  id: string;
  label: string;
  type: string;
  description?: string;
  mention_count: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  fx?: number;
  fy?: number;
}

interface SimEdge {
  source: string | SimNode;
  target: string | SimNode;
  label: string;
  relation_type: string;
  weight: number;
}

export default function KnowledgeGraphPage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [stats, setStats] = useState<KGStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [documentId, setDocumentId] = useState("");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [docSearch, setDocSearch] = useState("");
  const [docDropdownOpen, setDocDropdownOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<EntitySearchResult[]>([]);
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set());
  const [selectedNode, setSelectedNode] = useState<SimNode | null>(null);
  const [nodeDetail, setNodeDetail] = useState<Record<string, unknown> | null>(null);

  // 시뮬레이션 상태
  const nodesRef = useRef<SimNode[]>([]);
  const edgesRef = useRef<SimEdge[]>([]);
  const animRef = useRef<number>(0);
  const dragRef = useRef<{ node: SimNode; startX: number; startY: number } | null>(null);

  // ── 데이터 로딩 ────────────────────────────────────────────────────────

  const loadGraph = useCallback(async () => {
    setLoading(true);
    try {
      const typesParam = selectedTypes.size > 0 ? Array.from(selectedTypes).join(",") : undefined;
      const data = await fetchKGGraph(documentId || undefined, typesParam);
      setGraphData(data);
    } catch (err) {
      console.error("그래프 로딩 실패:", err);
    } finally {
      setLoading(false);
    }
  }, [documentId, selectedTypes]);

  const loadStats = useCallback(async () => {
    try {
      const s = await fetchKGStats();
      setStats(s);
    } catch {
      // 컬렉션이 없을 수 있음
    }
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  // 문서 목록 로딩
  useEffect(() => {
    getDocuments()
      .then((docs) => setDocuments(docs))
      .catch(() => setDocuments([]));
  }, []);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  // ── 추출 ──────────────────────────────────────────────────────────────

  const handleExtract = async () => {
    if (!documentId) return;
    setExtracting(true);
    try {
      await extractKnowledgeGraph(documentId);
      await loadGraph();
      await loadStats();
    } catch (err) {
      console.error("엔티티 추출 실패:", err);
      alert("추출 실패: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setExtracting(false);
    }
  };

  // ── 검색 ──────────────────────────────────────────────────────────────

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    try {
      const results = await searchKGEntities(searchQuery);
      setSearchResults(results);
    } catch (err) {
      console.error("엔티티 검색 실패:", err);
    }
  };

  // ── Force 시뮬레이션 ──────────────────────────────────────────────────

  const initSimulation = useCallback(
    (data: GraphData) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const width = canvas.width;
      const height = canvas.height;
      const centerX = width / 2;
      const centerY = height / 2;

      // 노드 초기화
      const nodes: SimNode[] = data.nodes.map((n, i) => ({
        id: n.id,
        label: n.label,
        type: n.type,
        description: n.description || undefined,
        mention_count: n.mention_count,
        x: centerX + Math.cos((2 * Math.PI * i) / data.nodes.length) * 150 + Math.random() * 50,
        y: centerY + Math.sin((2 * Math.PI * i) / data.nodes.length) * 150 + Math.random() * 50,
        vx: 0,
        vy: 0,
      }));

      const edges: SimEdge[] = data.edges.map((e) => ({
        source: e.source,
        target: e.target,
        label: e.label,
        relation_type: e.relation_type,
        weight: e.weight,
      }));

      nodesRef.current = nodes;
      edgesRef.current = edges;

      // Force 시뮬레이션 파라미터
      const REPULSION = 5000;
      const ATTRACTION = 0.005;
      const CENTER_FORCE = 0.01;
      const DAMPING = 0.85;
      const MIN_DIST = 30;

      const tick = () => {
        // 노드 맵
        const nodeMap = new Map(nodes.map((n) => [n.id, n]));

        // 에지 소스/타겟을 노드 객체로 변환
        edges.forEach((e) => {
          if (typeof e.source === "string") e.source = nodeMap.get(e.source) || nodes[0];
          if (typeof e.target === "string") e.target = nodeMap.get(e.target) || nodes[0];
        });

        // 중심력
        nodes.forEach((n) => {
          n.vx += (centerX - n.x) * CENTER_FORCE;
          n.vy += (centerY - n.y) * CENTER_FORCE;
        });

        // 반발력
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const dx = nodes[j].x - nodes[i].x;
            const dy = nodes[j].y - nodes[i].y;
            const dist = Math.sqrt(dx * dx + dy * dy) || MIN_DIST;
            const force = REPULSION / (dist * dist);
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            nodes[i].vx -= fx;
            nodes[i].vy -= fy;
            nodes[j].vx += fx;
            nodes[j].vy += fy;
          }
        }

        // 인력 (에지)
        edges.forEach((e) => {
          const s = typeof e.source === "string" ? nodeMap.get(e.source) : e.source;
          const t = typeof e.target === "string" ? nodeMap.get(e.target) : e.target;
          if (!s || !t) return;
          const dx = t.x - s.x;
          const dy = t.y - s.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = dist * ATTRACTION * e.weight;
          s.vx += (dx / dist) * force;
          s.vy += (dy / dist) * force;
          t.vx -= (dx / dist) * force;
          t.vy -= (dy / dist) * force;
        });

        // 감쇠 + 업데이트
        nodes.forEach((n) => {
          if (dragRef.current?.node === n) return;
          n.vx *= DAMPING;
          n.vy *= DAMPING;
          n.x += n.vx;
          n.y += n.vy;
        });

        // ── 렌더링 ──────────────────────────────────────────────────────

        ctx.clearRect(0, 0, width, height);

        // 배경
        ctx.fillStyle = "#0f172a";
        ctx.fillRect(0, 0, width, height);

        // 에지
        edges.forEach((e) => {
          const s = typeof e.source === "string" ? nodeMap.get(e.source) : e.source;
          const t = typeof e.target === "string" ? nodeMap.get(e.target) : e.target;
          if (!s || !t) return;

          ctx.beginPath();
          ctx.moveTo(s.x, s.y);
          ctx.lineTo(t.x, t.y);
          ctx.strokeStyle = "rgba(148, 163, 184, 0.3)";
          ctx.lineWidth = Math.max(1, e.weight * 2);
          ctx.stroke();

          // 에지 라벨
          if (e.label) {
            const mx = (s.x + t.x) / 2;
            const my = (s.y + t.y) / 2;
            ctx.fillStyle = "rgba(148, 163, 184, 0.6)";
            ctx.font = "10px sans-serif";
            ctx.textAlign = "center";
            ctx.fillText(e.label, mx, my - 4);
          }
        });

        // 노드
        nodes.forEach((n) => {
          const radius = Math.max(8, 6 + Math.sqrt(n.mention_count) * 3);
          const color = TYPE_COLORS[n.type] || "#94a3b8";

          // 선택된 노드 하이라이트
          if (selectedNode?.id === n.id) {
            ctx.beginPath();
            ctx.arc(n.x, n.y, radius + 4, 0, 2 * Math.PI);
            ctx.fillStyle = "rgba(250, 204, 21, 0.3)";
            ctx.fill();
          }

          // 노드 원
          ctx.beginPath();
          ctx.arc(n.x, n.y, radius, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
          ctx.strokeStyle = "rgba(255, 255, 255, 0.3)";
          ctx.lineWidth = 1;
          ctx.stroke();

          // 라벨
          ctx.fillStyle = "#e2e8f0";
          ctx.font = "12px sans-serif";
          ctx.textAlign = "center";
          const label = n.label.length > 15 ? n.label.slice(0, 14) + "…" : n.label;
          ctx.fillText(label, n.x, n.y + radius + 14);
        });

        animRef.current = requestAnimationFrame(tick);
      };

      // 기존 애니메이션 정리
      cancelAnimationFrame(animRef.current);
      tick();
    },
    [selectedNode]
  );

  // 그래프 데이터 변경 시 시뮬레이션 재시작
  useEffect(() => {
    if (graphData) {
      initSimulation(graphData);
    }
    return () => cancelAnimationFrame(animRef.current);
  }, [graphData, initSimulation]);

  // 캔버스 리사이즈
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const resize = () => {
      canvas.width = container.clientWidth;
      canvas.height = container.clientHeight;
      if (graphData) initSimulation(graphData);
    };

    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [graphData, initSimulation]);

  // ── 캔버스 상호작용 ──────────────────────────────────────────────────

  const handleCanvasClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      // 클릭한 노드 찾기
      const clicked = nodesRef.current.find((n) => {
        const radius = Math.max(8, 6 + Math.sqrt(n.mention_count) * 3);
        const dx = x - n.x;
        const dy = y - n.y;
        return dx * dx + dy * dy <= radius * radius;
      });

      if (clicked) {
        setSelectedNode(clicked);
        // 엔티티 상세 조회
        fetch(`/api/kg/entity/${clicked.id}`)
          .then((r) => r.json())
          .then(setNodeDetail)
          .catch(() => setNodeDetail(null));
      } else {
        setSelectedNode(null);
        setNodeDetail(null);
      }
    },
    []
  );

  const handleCanvasMouseDown = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const clicked = nodesRef.current.find((n) => {
        const radius = Math.max(8, 6 + Math.sqrt(n.mention_count) * 3);
        const dx = x - n.x;
        const dy = y - n.y;
        return dx * dx + dy * dy <= (radius + 5) * (radius + 5);
      });

      if (clicked) {
        dragRef.current = { node: clicked, startX: x, startY: y };
      }
    },
    []
  );

  const handleCanvasMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!dragRef.current) return;
      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      dragRef.current.node.x = x;
      dragRef.current.node.y = y;
      dragRef.current.node.vx = 0;
      dragRef.current.node.vy = 0;
    },
    []
  );

  const handleCanvasMouseUp = useCallback(() => {
    dragRef.current = null;
  }, []);

  // ── 타입 필터 토글 ──────────────────────────────────────────────────

  const toggleType = (type: string) => {
    setSelectedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  // ── 렌더 ──────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-1 flex-col overflow-hidden min-h-0">
      {/* 헤더 */}
      <div className="border-b border-gray-700 bg-gray-900 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">지식 그래프</h1>
            <p className="text-sm text-gray-400">
              문서 간 관계를 시각적으로 탐색합니다
            </p>
          </div>
          {stats && (
            <div className="flex gap-4 text-sm">
              <span className="text-blue-400">
                엔티티 <strong>{stats.total_entities}</strong>
              </span>
              <span className="text-green-400">
                관계 <strong>{stats.total_relations}</strong>
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* 사이드바 */}
        <div className="w-80 flex-shrink-0 border-r border-gray-700 bg-gray-900 overflow-y-auto">
          {/* 추출 */}
          <div className="border-b border-gray-700 p-4">
            <h2 className="mb-2 text-sm font-semibold text-gray-300">
              엔티티 추출
            </h2>
            <div className="relative mb-2">
              <input
                type="text"
                placeholder="문서 검색 또는 ID 직접 입력"
                value={docSearch || (documentId ? documents.find((d) => d.document_id === documentId)?.filename || documentId : "")}
                onChange={(e) => {
                  setDocSearch(e.target.value);
                  setDocDropdownOpen(true);
                  // 직접 ID 입력 지원: 검색어를 documentId로 설정
                  if (e.target.value && !documents.some((d) => d.filename === e.target.value || d.document_id === e.target.value)) {
                    setDocumentId(e.target.value);
                  } else {
                    setDocumentId("");
                  }
                }}
                onFocus={() => setDocDropdownOpen(true)}
                onBlur={() => setTimeout(() => setDocDropdownOpen(false), 200)}
                className="w-full rounded border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
              />
              {/* 선택된 문서 표시 */}
              {documentId && !docSearch && (
                <button
                  onClick={() => { setDocumentId(""); setDocSearch(""); }}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                  title="선택 해제"
                >
                  ✕
                </button>
              )}
              {/* 드롭다운 목록 */}
              {docDropdownOpen && (
                <div className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded border border-gray-600 bg-gray-800 shadow-lg">
                  {(() => {
                    const filtered = documents.filter(
                      (d) =>
                        d.filename.toLowerCase().includes((docSearch || "").toLowerCase()) ||
                        d.document_id.toLowerCase().includes((docSearch || "").toLowerCase())
                    );
                    if (filtered.length === 0) {
                      return (
                        <div className="px-3 py-2 text-xs text-gray-500">
                          {docSearch ? "검색 결과 없음 — ID를 직접 입력하세요" : "인덱싱된 문서가 없습니다"}
                        </div>
                      );
                    }
                    return filtered.map((doc) => (
                      <button
                        key={doc.document_id}
                        onClick={() => {
                          setDocumentId(doc.document_id);
                          setDocSearch("");
                          setDocDropdownOpen(false);
                        }}
                        className={`w-full px-3 py-2 text-left text-xs hover:bg-gray-700 ${
                          documentId === doc.document_id ? "bg-blue-600/20 text-blue-300" : "text-gray-300"
                        }`}
                      >
                        <div className="font-medium">{doc.filename}</div>
                        <div className="text-gray-500">{doc.document_id}</div>
                      </button>
                    ));
                  })()}
                </div>
              )}
            </div>
            <button
              onClick={handleExtract}
              disabled={extracting || !documentId}
              className="w-full rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {extracting ? "추출 중…" : "추출 실행"}
            </button>
          </div>

          {/* 검색 */}
          <div className="border-b border-gray-700 p-4">
            <h2 className="mb-2 text-sm font-semibold text-gray-300">
              엔티티 검색
            </h2>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="검색어"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                className="flex-1 rounded border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
              />
              <button
                onClick={handleSearch}
                className="rounded bg-gray-700 px-3 py-2 text-sm text-white hover:bg-gray-600"
              >
                🔍
              </button>
            </div>
            {searchResults.length > 0 && (
              <div className="mt-2 max-h-40 overflow-y-auto">
                {searchResults.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => setDocumentId("")}
                    className="mb-1 w-full rounded bg-gray-800 px-3 py-1.5 text-left text-xs text-gray-300 hover:bg-gray-700"
                  >
                    <span
                      className="mr-1 inline-block h-2 w-2 rounded-full"
                      style={{ backgroundColor: TYPE_COLORS[r.type] || "#94a3b8" }}
                    />
                    {r.name}
                    <span className="float-right text-gray-500">
                      {r.score.toFixed(2)}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* 타입 필터 */}
          <div className="border-b border-gray-700 p-4">
            <h2 className="mb-2 text-sm font-semibold text-gray-300">
              엔티티 타입
            </h2>
            <div className="flex flex-wrap gap-1">
              {Object.entries(TYPE_LABELS).map(([type, label]) => (
                <button
                  key={type}
                  onClick={() => toggleType(type)}
                  className={`rounded px-2 py-1 text-xs ${
                    selectedTypes.has(type)
                      ? "bg-blue-600 text-white"
                      : "bg-gray-800 text-gray-400 hover:bg-gray-700"
                  }`}
                >
                  <span
                    className="mr-1 inline-block h-2 w-2 rounded-full"
                    style={{ backgroundColor: TYPE_COLORS[type] }}
                  />
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* 선택된 노드 상세 */}
          {selectedNode && (
            <div className="p-4">
              <h2 className="mb-2 text-sm font-semibold text-gray-300">
                엔티티 상세
              </h2>
              <div className="rounded bg-gray-800 p-3 text-sm">
                <div className="mb-1">
                  <span
                    className="mr-1 inline-block h-2 w-2 rounded-full"
                    style={{
                      backgroundColor: TYPE_COLORS[selectedNode.type] || "#94a3b8",
                    }}
                  />
                  <span className="font-medium text-white">
                    {selectedNode.label}
                  </span>
                </div>
                <div className="text-gray-400">
                  타입: {TYPE_LABELS[selectedNode.type] || selectedNode.type}
                </div>
                <div className="text-gray-400">
                  언급: {selectedNode.mention_count}회
                </div>
                {selectedNode.description && (
                  <div className="mt-1 text-gray-500">
                    {selectedNode.description}
                  </div>
                )}
                {nodeDetail && (
                  <div className="mt-2 border-t border-gray-700 pt-2">
                    <div className="text-xs text-gray-400">관련 엔티티:</div>
                    {(nodeDetail as { related_entities?: { name: string; type: string; relation_type: string }[] }).related_entities?.slice(0, 5).map((re, i) => (
                      <div key={i} className="text-xs text-gray-500">
                        → {re.name} ({re.relation_type})
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* 그래프 영역 */}
        <div ref={containerRef} className="relative flex-1 bg-gray-950">
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-gray-950/80">
              <div className="text-lg text-gray-300">그래프 로딩 중…</div>
            </div>
          )}
          <canvas
            ref={canvasRef}
            className="h-full w-full cursor-grab active:cursor-grabbing"
            onClick={handleCanvasClick}
            onMouseDown={handleCanvasMouseDown}
            onMouseMove={handleCanvasMouseMove}
            onMouseUp={handleCanvasMouseUp}
            onMouseLeave={handleCanvasMouseUp}
          />
          {!graphData?.nodes.length && !loading && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center text-gray-500">
                <p className="text-lg">지식 그래프가 비어 있습니다</p>
                <p className="text-sm">
                  문서를 선택하고 &ldquo;추출 실행&rdquo;을 클릭하세요
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}