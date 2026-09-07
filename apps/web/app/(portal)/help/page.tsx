import type { Metadata } from "next";
import { EmployeeGuide } from "@/components/agent-platform/employee-guide";

export const metadata: Metadata = { title: "이용 방법 | Getting started" };
export default function HelpPage() { return <EmployeeGuide />; }
