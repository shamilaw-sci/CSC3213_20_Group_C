import api from '@/lib/api-client';
import { FinanceReport } from '@/types';

export const ReportsService = {
  getFinanceReport: async (startDate: string, endDate: string) => {
    const response = await api.get<FinanceReport>('/reports/finance', {
      params: { start_date: startDate, end_date: endDate },
    });
    return response.data;
  },

  // The PDF renders the same report as getFinanceReport, plus the period's
  // transactions.
  downloadFinanceSummary: async (startDate: string, endDate: string) => {
    const response = await api.get('/reports/finance/summary', {
      params: { start_date: startDate, end_date: endDate },
      responseType: 'blob',
    });

    const url = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `finance_report_${startDate}_${endDate}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
};
