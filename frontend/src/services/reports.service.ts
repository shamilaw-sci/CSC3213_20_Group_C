import api from '@/lib/api-client';

export const ReportsService = {
  downloadFinanceSummary: async (startDate: string, endDate: string) => {
    const response = await api.get('/reports/finance/summary', {
      params: { start_date: startDate, end_date: endDate },
      responseType: 'blob',
    });

    const url = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `finance_summary_${startDate}_${endDate}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
};