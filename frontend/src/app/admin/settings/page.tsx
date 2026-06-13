"use client";

import { AdminGuard } from "../../../components/AuthGuard";
import SettingsContent from "../../settings/SettingsContent";

export default function AdminSettingsPage() {
  return (
    <AdminGuard>
      <SettingsContent />
    </AdminGuard>
  );
}