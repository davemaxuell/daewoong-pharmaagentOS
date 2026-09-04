import type { Metadata } from "next";
import { getReviewQueue } from "@/lib/api-client";
import { requirePortalRole } from "@/lib/backend-auth";
import { ReviewConsole } from "@/components/review-console";

export const metadata: Metadata = { title: "Review | 검토" };

export default async function ReviewPage() {
  await requirePortalRole("reviewer");
  const { data, mode } = await getReviewQueue({ view: "open", pageSize: 10 });
  return <ReviewConsole initialQueue={data} mode={mode} />;
}
