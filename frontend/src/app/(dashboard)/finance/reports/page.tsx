import ProtectedRoute from "@/components/layout/protected-route";
import { FinanceReportView } from "@/components/finance/reports/FinanceReportView";

export default function ReportsPage() {
  return (
    <ProtectedRoute requiredPermission="finance:read">
      <FinanceReportView />
    </ProtectedRoute>
  );
}
