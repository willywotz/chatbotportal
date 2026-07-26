import { describe, it, expect } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { AssistantMessageContent } from './AssistantMessageContent';

const SUMMARY = 'ค่าธรรมเนียมอยู่ที่ 2% [1]';

describe('AssistantMessageContent', () => {
  it('renders the summary once and the section body', () => {
    render(
      <AssistantMessageContent
        content={`${SUMMARY}\n\n---\n\n## หัวข้อ\n\nเนื้อหาดิบ`}
        summary={SUMMARY}
        references={[{ number: 1, agency_id: 'land', agency_name: 'กรมที่ดิน', url: null }]}
      />,
    );
    expect(screen.getByText('เนื้อหาดิบ')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /สรุป/ }));
    expect(screen.getAllByText(/ค่าธรรมเนียมอยู่ที่ 2%/)).toHaveLength(1);
    expect(screen.getByText(/\[1\] กรมที่ดิน/)).toBeInTheDocument();
  });

  it('shows the thinking panel expanded by default', () => {
    render(<AssistantMessageContent content={'<think>reasoning here</think>คำตอบ'} />);
    expect(screen.getByText('Thinking')).toBeInTheDocument();
    expect(screen.getByText('reasoning here')).toBeInTheDocument();
    expect(screen.getByText('คำตอบ')).toBeInTheDocument();
  });

  it('renders no thinking panel when there is no thinking content', () => {
    render(<AssistantMessageContent content={'คำตอบธรรมดา'} />);
    expect(screen.queryByText('Thinking')).not.toBeInTheDocument();
    expect(screen.getByText('คำตอบธรรมดา')).toBeInTheDocument();
  });
});

describe('AssistantMessageContent agent steps', () => {
  it('renders the agent-steps card when steps are present', () => {
    render(
      <AssistantMessageContent
        content="คำตอบ"
        steps={{ steps: [{ name: 'discover', ms: 1000 }], agencies: [], errors: [] }}
      />,
    );
    expect(screen.getByText('กระบวนการทำงานของ AI Agent')).toBeInTheDocument();
  });

  it('renders no agent-steps card when steps is null', () => {
    render(<AssistantMessageContent content="คำตอบ" steps={null} />);
    expect(screen.queryByText('กระบวนการทำงานของ AI Agent')).not.toBeInTheDocument();
  });
});
