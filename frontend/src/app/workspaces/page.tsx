"use client";

import { useState, useEffect } from "react";
import {
  listWorkspaces,
  createWorkspace,
  updateWorkspace,
  deleteWorkspace,
  assignDocuments,
  unassignDocuments,
  getDocuments,
  type Workspace,
  type WorkspaceCreate,
} from "../../lib/api";

export default function WorkspacesPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [documents, setDocuments] = useState<{ id: string; original_filename: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showDocs, setShowDocs] = useState<string | null>(null);
  const [form, setForm] = useState<WorkspaceCreate>({ name: "", description: "", system_prompt: "" });
  const [editForm, setEditForm] = useState({ name: "", description: "", system_prompt: "" });
  const [error, setError] = useState("");

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [wsRes, docs] = await Promise.all([listWorkspaces(), getDocuments()]);
      setWorkspaces(wsRes.workspaces);
      setDocuments(docs.map((d: any) => ({ id: d.id, original_filename: d.original_filename })));
    } catch (err) {
      setError("데이터를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!form.name.trim()) return;
    try {
      await createWorkspace(form);
      setShowCreate(false);
      setForm({ name: "", description: "", system_prompt: "" });
      loadData();
    } catch (err) {
      setError("워크스페이스 생성 실패");
    }
  };

  const handleUpdate = async (id: string) => {
    try {
      await updateWorkspace(id, editForm);
      setEditingId(null);
      loadData();
    } catch (err) {
      setError("수정 실패");
    }
  };

  const handleDelete = async (id: string) => {
    if (id === "default") return;
    if (!confirm("정말 삭제하시겠습니까?")) return;
    try {
      await deleteWorkspace(id);
      loadData();
    } catch (err) {
      setError("삭제 실패");
    }
  };

  const handleAssign = async (wsId: string, docId: string, assign: boolean) => {
    try {
      if (assign) {
        await assignDocuments(wsId, [docId]);
      } else {
        await unassignDocuments(wsId, [docId]);
      }
      loadData();
    } catch (err) {
      setError(assign ? "문서 할당 실패" : "문서 해제 실패");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-gray-500 dark:text-gray-400">로딩 중...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">📁 워크스페이스</h1>
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            + 새 워크스페이스
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-lg text-sm">
            {error}
            <button onClick={() => setError("")} className="ml-2 underline">닫기</button>
          </div>
        )}

        {/* 생성 모달 */}
        {showCreate && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white dark:bg-gray-800 rounded-xl p-6 w-full max-w-lg shadow-2xl">
              <h2 className="text-lg font-bold mb-4 text-gray-900 dark:text-white">새 워크스페이스</h2>
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">이름</label>
                  <input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 dark:bg-gray-700 dark:text-white"
                    placeholder="예: 북한 전문 분석"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">설명</label>
                  <textarea
                    value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 dark:bg-gray-700 dark:text-white"
                    rows={2}
                    placeholder="워크스페이스 용도 설명"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">시스템 프롬프트</label>
                  <textarea
                    value={form.system_prompt}
                    onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 dark:bg-gray-700 dark:text-white"
                    rows={4}
                    placeholder="이 워크스페이스에서 사용할 시스템 프롬프트 (선택)"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 mt-4">
                <button
                  onClick={() => { setShowCreate(false); setForm({ name: "", description: "", system_prompt: "" }); }}
                  className="px-4 py-2 bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-500"
                >
                  취소
                </button>
                <button
                  onClick={handleCreate}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  생성
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 워크스페이스 목록 */}
        <div className="space-y-4">
          {workspaces.map((ws) => (
            <div key={ws.id} className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  {editingId === ws.id ? (
                    <div className="space-y-2">
                      <input
                        value={editForm.name}
                        onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                        className="w-full rounded border border-gray-300 dark:border-gray-600 px-2 py-1 dark:bg-gray-700 dark:text-white text-sm"
                      />
                      <textarea
                        value={editForm.description}
                        onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                        className="w-full rounded border border-gray-300 dark:border-gray-600 px-2 py-1 dark:bg-gray-700 dark:text-white text-sm"
                        rows={2}
                      />
                      <textarea
                        value={editForm.system_prompt}
                        onChange={(e) => setEditForm({ ...editForm, system_prompt: e.target.value })}
                        className="w-full rounded border border-gray-300 dark:border-gray-600 px-2 py-1 dark:bg-gray-700 dark:text-white text-sm"
                        rows={3}
                        placeholder="시스템 프롬프트"
                      />
                      <div className="flex gap-2">
                        <button onClick={() => handleUpdate(ws.id)} className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700">저장</button>
                        <button onClick={() => setEditingId(null)} className="px-3 py-1 bg-gray-200 dark:bg-gray-600 text-sm rounded hover:bg-gray-300 dark:hover:bg-gray-500">취소</button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="flex items-center gap-2">
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{ws.name}</h3>
                        {ws.id === "default" && (
                          <span className="text-xs px-2 py-0.5 bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 rounded-full">기본</span>
                        )}
                      </div>
                      {ws.description && (
                        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{ws.description}</p>
                      )}
                      {ws.system_prompt && (
                        <p className="text-xs text-gray-500 dark:text-gray-500 mt-1 line-clamp-2 italic">
                          프롬프트: {ws.system_prompt.slice(0, 100)}{ws.system_prompt.length > 100 ? "..." : ""}
                        </p>
                      )}
                      <div className="flex gap-4 mt-2 text-xs text-gray-500 dark:text-gray-400">
                        <span>📄 문서 {ws.document_ids.length}개</span>
                        <span>🏷️ {ws.vector_collection}</span>
                        <span>🕐 {new Date(ws.created_at).toLocaleDateString()}</span>
                      </div>
                    </>
                  )}
                </div>

                {editingId !== ws.id && (
                  <div className="flex gap-2 ml-4">
                    <button
                      onClick={() => { setEditingId(ws.id); setEditForm({ name: ws.name, description: ws.description, system_prompt: ws.system_prompt }); }}
                      className="px-3 py-1 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-200 dark:hover:bg-gray-600"
                    >
                      ✏️ 편집
                    </button>
                    <button
                      onClick={() => setShowDocs(showDocs === ws.id ? null : ws.id)}
                      className="px-3 py-1 text-sm bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded hover:bg-green-200 dark:hover:bg-green-800/40"
                    >
                      📂 문서
                    </button>
                    {ws.id !== "default" && (
                      <button
                        onClick={() => handleDelete(ws.id)}
                        className="px-3 py-1 text-sm bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded hover:bg-red-200 dark:hover:bg-red-800/40"
                      >
                        🗑️ 삭제
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* 문서 할당 패널 */}
              {showDocs === ws.id && (
                <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                  <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">문서 할당</h4>
                  <div className="max-h-48 overflow-y-auto space-y-1">
                    {documents.map((doc) => {
                      const isAssigned = ws.document_ids.includes(doc.id);
                      return (
                        <label key={doc.id} className="flex items-center gap-2 px-2 py-1 rounded hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={isAssigned}
                            onChange={() => handleAssign(ws.id, doc.id, !isAssigned)}
                            className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          />
                          <span className="text-sm text-gray-700 dark:text-gray-300">{doc.original_filename}</span>
                        </label>
                      );
                    })}
                    {documents.length === 0 && (
                      <p className="text-sm text-gray-400 dark:text-gray-500">등록된 문서가 없습니다.</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}