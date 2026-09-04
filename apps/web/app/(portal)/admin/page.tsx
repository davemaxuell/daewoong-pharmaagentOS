import type { Metadata } from "next";
import { getAdminData } from "@/lib/api-client";
import { requirePortalRole } from "@/lib/backend-auth";
import { AdminConsole } from "@/components/admin-console";

export const metadata: Metadata = { title: "Admin | 관리자" };

export default async function AdminPage() {
  await requirePortalRole("admin");
  const { data, mode } = await getAdminData();
  return <AdminConsole data={data} mode={mode} />;
}
