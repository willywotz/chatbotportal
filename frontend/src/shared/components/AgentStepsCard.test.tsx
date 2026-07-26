import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AgentStepsCard } from './AgentStepsCard';

const snap = {
  steps: [
    { name: 'discover', ms: 1200 },
    { name: 'invoke', ms: 3400 },
  ],
  agencies: [
    { id: 'land', name: 'กรมที่ดิน', status: 'passed' as const, sectionLabel: 'ค่าธรรมเนียม' },
    { id: 'rev', name: 'กรมสรรพากร', status: 'rejected' as const },
  ],
  errors: [],
};

describe('AgentStepsCard', () => {
  it('renders nothing when steps is null', () => {
    const { container } = render(<AgentStepsCard steps={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('is collapsed by default and expands on click', () => {
    render(<AgentStepsCard steps={snap} />);
    expect(screen.queryByText('กรมที่ดิน')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText('กรมที่ดิน')).toBeInTheDocument();
  });

  it('shows the step timeline with labels and descriptions when expanded', () => {
    render(<AgentStepsCard steps={snap} />);
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText('ค้นหาหน่วยงาน')).toBeInTheDocument();
    expect(screen.getByText('ค้นหารายชื่อหน่วยงานที่ให้บริการ')).toBeInTheDocument();
  });

  it('shows pass/reject summary chips when expanded', () => {
    render(<AgentStepsCard steps={snap} />);
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText('ผ่าน 1')).toBeInTheDocument();
    expect(screen.getByText('ไม่ผ่าน 1')).toBeInTheDocument();
  });

  it('shows the agency section label when expanded', () => {
    render(<AgentStepsCard steps={snap} />);
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText('[ค่าธรรมเนียม]')).toBeInTheDocument();
  });

  it('renders expanded when defaultOpen is set', () => {
    render(<AgentStepsCard steps={snap} defaultOpen />);
    expect(screen.getByText('กรมที่ดิน')).toBeInTheDocument();
  });
});
