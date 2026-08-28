import ProtectedRoute from "@/components/layout/protected-route";
import FinanceSummary from "@/components/FinanceSummary";

export default function ReportsPage() {
  return (
    <ProtectedRoute requiredPermission="finance:read">
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-bold font-heading tracking-tight mb-2 text-text-primary">
            Financial Reports
          </h1>
          <p className="text-text-secondary text-sm">
            Period-based breakdowns of income, expenses, and balance.
          </p>
        </div>

        <div>
          <h2 className="text-base font-semibold font-heading text-text-primary mb-4">
            Monthly Summary
          </h2>
          <FinanceSummary />
        </div>
      </div>
    </ProtectedRoute>
  );
}
