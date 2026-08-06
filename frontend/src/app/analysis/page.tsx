import { Suspense } from "react";
import { LoadingState } from "@/components/ui/States";
import { AnalysisPageContent } from "./AnalysisPageContent";

export const metadata = { title: "AI Analysis" };

export default function AnalysisPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading…" />}>
      <AnalysisPageContent />
    </Suspense>
  );
}
