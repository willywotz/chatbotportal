import type { HistoryItem } from '@/features/history/historyApi';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';

export function exportToCsv(conversations: HistoryItem[], filename = 'chat-history.csv') {
  const BOM = '\uFEFF';
  const headers = ['หัวข้อ', 'ข้อความตัวอย่าง', 'วันที่', 'หน่วยงาน', 'สถานะ', 'จำนวนข้อความ', 'เวลาตอบ'];
  const rows = conversations.map((c) => [
    c.title,
    c.preview,
    c.date,
    c.agencies.join(', '),
    c.status === 'success' ? 'สำเร็จ' : 'ล้มเหลว',
    String(c.messageCount ?? ''),
    c.responseTime ?? '',
  ]);

  const csvContent = [headers, ...rows]
    .map((row) => row.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(','))
    .join('\n');

  const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function exportToPdf(conversations: HistoryItem[], filename = 'chat-history.pdf') {
  const doc = new jsPDF({ orientation: 'landscape' });

  doc.setFontSize(16);
  doc.text('Chat History', 14, 18);
  doc.setFontSize(9);
  doc.text(`Exported: ${new Date().toLocaleString('th-TH')}  |  Total: ${conversations.length}`, 14, 25);

  autoTable(doc, {
    startY: 30,
    head: [['#', 'Title', 'Preview', 'Date', 'Agencies', 'Status', 'Messages', 'Response']],
    body: conversations.map((c, i) => [
      i + 1,
      c.title,
      c.preview.length > 60 ? c.preview.slice(0, 60) + '...' : c.preview,
      c.date,
      c.agencies.join(', '),
      c.status === 'success' ? 'OK' : 'FAIL',
      c.messageCount ?? '-',
      c.responseTime ?? '-',
    ]),
    styles: { fontSize: 8, cellPadding: 2 },
    headStyles: { fillColor: [59, 130, 246] },
    columnStyles: {
      0: { cellWidth: 10 },
      2: { cellWidth: 60 },
    },
  });

  doc.save(filename);
}
