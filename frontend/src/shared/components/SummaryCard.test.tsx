import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SummaryCard } from './SummaryCard';

const REFS = [{ number: 1, agency_id: 'land', agency_name: 'กรมที่ดิน', url: null }];

describe('SummaryCard', () => {
  it('is collapsed by default, showing the header but not the summary', () => {
    render(<SummaryCard summary="ค่าธรรมเนียมอยู่ที่ 2% [1]" references={REFS} />);
    expect(screen.getByRole('button', { name: /สรุป/ })).toBeInTheDocument();
    expect(screen.queryByText(/ค่าธรรมเนียมอยู่ที่ 2%/)).not.toBeInTheDocument();
  });

  it('expands to show the summary and references on click', () => {
    render(<SummaryCard summary="ค่าธรรมเนียมอยู่ที่ 2% [1]" references={REFS} />);
    fireEvent.click(screen.getByRole('button', { name: /สรุป/ }));
    expect(screen.getByText(/ค่าธรรมเนียมอยู่ที่ 2%/)).toBeInTheDocument();
    expect(screen.getByText(/\[1\] กรมที่ดิน/)).toBeInTheDocument();
  });

  it('renders nothing without a summary', () => {
    const { container } = render(<SummaryCard summary={null} references={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing for a blank summary', () => {
    const { container } = render(<SummaryCard summary="   " />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows no reference list when expanded without references', () => {
    render(<SummaryCard summary="สรุปสั้นๆ" />);
    fireEvent.click(screen.getByRole('button', { name: /สรุป/ }));
    expect(screen.getByText('สรุปสั้นๆ')).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });
});
