import { Construction } from "lucide-react";
import { Card } from "@/components/ui";

export function ComingSoon({
  title,
  phase,
}: {
  title: string;
  phase: string;
}) {
  return (
    <div className="max-w-6xl">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <Card className="mt-6 p-16 text-center">
        <Construction size={40} className="mx-auto text-outline" />
        <p className="mt-4 font-medium text-on-surface-variant">
          Раздел в разработке
        </p>
        <p className="text-sm text-outline mt-1">
          Появится на этапе {phase} согласно плану Phase 1
        </p>
      </Card>
    </div>
  );
}
