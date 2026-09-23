import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import type { ExecutiveData } from '@/features/executive/executiveApi';

export function generateExecutiveReport(data: ExecutiveData) {
  const doc = new jsPDF();
  const pageWidth = doc.internal.pageSize.getWidth();
  const date = new Date(data.generatedAt).toLocaleDateString('th-TH', {
    year: 'numeric', month: 'long', day: 'numeric',
  });

  doc.setFillColor(30, 90, 170);
  doc.rect(0, 0, pageWidth, 70, 'F');
  doc.setTextColor(255, 255, 255);
  doc.setFontSize(22);
  doc.text('Executive Report', pageWidth / 2, 30, { align: 'center' });
  doc.setFontSize(14);
  doc.text('AI Portal - Citizen Services', pageWidth / 2, 45, { align: 'center' });
  doc.setFontSize(11);
  doc.text(`Generated: ${date}`, pageWidth / 2, 58, { align: 'center' });

  doc.setTextColor(0, 0, 0);
  let y = 90;

  doc.setFontSize(16);
  doc.text('Key Performance Indicators', 14, y);
  y += 8;
  doc.setDrawColor(30, 90, 170);
  doc.line(14, y, pageWidth - 14, y);
  y += 8;

  const k = data.kpis;
  autoTable(doc, {
    startY: y,
    head: [['Metric', 'Value', 'Change']],
    body: [
      ['Total Questions (Month)', k.totalQuestions.toLocaleString(), `${k.momGrowth >= 0 ? '+' : ''}${k.momGrowth}% MoM`],
      ['Year over Year Growth', `${k.yoyGrowth}%`, k.yoyGrowth >= 0 ? 'Up' : 'Down'],
      ['Unique Citizens Served', k.uniqueCitizens.toLocaleString(), '-'],
      ['Hours Saved (vs Call Center)', `${k.totalHoursSaved.toLocaleString()} hrs`, '-'],
      ['Cost Saved', `${k.costSaved.toLocaleString()} THB`, '-'],
      ['System Health Score', `${k.healthScore} / 100`, k.healthScore >= 90 ? 'Excellent' : 'Good'],
      ['System Uptime', `${k.uptime}%`, '-'],
      ['Citizen Satisfaction', `${k.satisfaction}%`, '-'],
      ['Avg Response Time', `${k.avgResponseTime}s`, '-'],
    ],
    theme: 'striped',
    headStyles: { fillColor: [30, 90, 170] },
  });

  y = (doc as any).lastAutoTable.finalY + 14;

  doc.setFontSize(16);
  doc.text('Agency Performance Scorecard', 14, y);
  y += 8;
  doc.line(14, y, pageWidth - 14, y);
  y += 4;

  autoTable(doc, {
    startY: y,
    head: [['Agency', 'Uptime', 'Latency', 'Satisfaction', 'Calls', 'Grade']],
    body: data.agencyScorecard.map(a => [
      a.shortName,
      `${a.uptime}%`,
      `${a.avgLatency}ms`,
      `${a.satisfaction}%`,
      a.calls.toLocaleString(),
      a.grade,
    ]),
    theme: 'striped',
    headStyles: { fillColor: [30, 90, 170] },
  });

  y = (doc as any).lastAutoTable.finalY + 14;

  if (y > 230) { doc.addPage(); y = 20; }
  doc.setFontSize(16);
  doc.text('Top Citizen Inquiries', 14, y);
  y += 8;
  doc.line(14, y, pageWidth - 14, y);
  y += 4;

  autoTable(doc, {
    startY: y,
    head: [['Topic (Thai)', 'Count', 'Trend']],
    body: data.topIssues.map(t => [t.topic, t.count.toLocaleString(), t.trend]),
    theme: 'striped',
    headStyles: { fillColor: [30, 90, 170] },
  });

  // AI Brief on new page
  doc.addPage();
  doc.setFontSize(16);
  doc.text('AI Weekly Executive Brief', 14, 20);
  doc.line(14, 24, pageWidth - 14, 24);
  doc.setFontSize(10);
  const briefLines = doc.splitTextToSize(
    data.weeklyBrief || 'No brief available',
    pageWidth - 28
  );
  doc.text(briefLines, 14, 34);

  const pageCount = doc.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    doc.setFontSize(8);
    doc.setTextColor(120, 120, 120);
    doc.text(
      `AI Portal Executive Report  |  Page ${i} of ${pageCount}  |  Confidential`,
      pageWidth / 2,
      doc.internal.pageSize.getHeight() - 8,
      { align: 'center' }
    );
  }

  doc.save(`executive-report-${new Date().toISOString().split('T')[0]}.pdf`);
}