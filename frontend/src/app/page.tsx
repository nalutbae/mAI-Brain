"use client";

import { useState, useEffect } from "react";
import ChatInterface from "../components/ChatInterface";
import SessionList from "../components/SessionList";
import { Session, getSessions, createSession } from "../lib/api";

export default function Home() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadSessions();
  }, []);

  const loadSessions = async () => {
    try {
      const data = await getSessions();
      setSessions(data);
    } catch (error) {
      console.error("Failed to load sessions:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSessionSelect = (sessionId: string) => {
    setCurrentSessionId(sessionId);
  };

  const handleNewSession = async () => {
    try {
      const newSession = await createSession("새 대화");
      setSessions((prev) => [newSession, ...prev]);
      setCurrentSessionId(newSession.id);
    } catch (error) {
      console.error("Failed to create session:", error);
    }
  };

  const handleSessionStart = (sessionId: string) => {
    setCurrentSessionId(sessionId);
    // 세션이 시작되면 세션 목록 새로고침
    loadSessions();
  };

  return (
    <div className="flex h-full bg-gray-50 dark:bg-black">
      <SessionList
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSessionSelect={handleSessionSelect}
        onNewSession={handleNewSession}
      />
      <div className="flex-1 flex flex-col">
        <header className="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6 py-4">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            mAI-Brain
          </h1>
          {currentSessionId && (
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              세션 ID: {currentSessionId}
            </p>
          )}
        </header>
        <ChatInterface
          sessionId={currentSessionId || undefined}
          onSessionStart={handleSessionStart}
        />
      </div>
    </div>
  );
}