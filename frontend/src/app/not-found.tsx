import Link from "next/link";
import { Compass } from "lucide-react";
import { EmptyState } from "@/components/ui/States";
import { Button } from "@/components/ui/Button";

export default function NotFound() {
  return (
    <EmptyState
      icon={<Compass className="size-5" />}
      title="Page not found"
      description="That route doesn't exist in AInvest. Head back to the dashboard."
      action={
        <Link href="/" className="mt-2">
          <Button variant="secondary" size="sm">
            Back to dashboard
          </Button>
        </Link>
      }
    />
  );
}
