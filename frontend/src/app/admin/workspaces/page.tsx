"use client";

import { AdminGuard } from "../../../components/AuthGuard";
import WorkspacesContent from "../../workspaces/WorkspacesContent";

export default function AdminWorkspacesPage() {
  return (
    <AdminGuard>
      <WorkspacesContent />
    </AdminGuard>
  );
}