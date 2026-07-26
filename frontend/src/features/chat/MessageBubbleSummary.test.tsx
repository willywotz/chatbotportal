import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MessageBubble } from './MessageBubble';
import type { ChatMessage } from '@/shared/types';

const SUMMARY = 'ค่าธรรมเนียมอยู่ที่ 2% [1]';

function assistantMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 'm1',
    role: 'assistant',
    content: `${SUMMARY}\n\n---\n\n## หัวข้อ\n\nเนื้อหาดิบจากหน่วยงาน`,
    timestamp: '10:00',
    rating: null,
    ...overrides,
  };
}

describe('MessageBubble v5 summary', () => {
  it('shows the summary exactly once alongside the section body', () => {
    render(
      <MessageBubble
        message={assistantMessage({
          summary: SUMMARY,
          summaryReferences: [{ number: 1, agency_id: 'land', agency_name: 'กรมที่ดิน', url: null }],
        })}
      />,
    );
    expect(screen.getByText('เนื้อหาดิบจากหน่วยงาน')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /สรุป/ }));
    expect(screen.getAllByText(/ค่าธรรมเนียมอยู่ที่ 2%/)).toHaveLength(1);
    expect(screen.getByText(/\[1\] กรมที่ดิน/)).toBeInTheDocument();
  });

  it('renders the full content unchanged when there is no summary (v4 mode)', () => {
    render(<MessageBubble message={assistantMessage({ content: 'คำตอบธรรมดา' })} />);
    expect(screen.getByText('คำตอบธรรมดา')).toBeInTheDocument();
  });
});
