import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PageHeader } from './PageHeader';

describe('PageHeader', () => {
  it('renders the title as a single h1', () => {
    render(<PageHeader title="จัดการผู้ใช้" />);
    const heading = screen.getByRole('heading', { level: 1 });
    expect(heading).toHaveTextContent('จัดการผู้ใช้');
  });

  it('renders an optional subtitle', () => {
    render(<PageHeader title="Dashboard" subtitle="ภาพรวมการใช้งาน" />);
    expect(screen.getByText('ภาพรวมการใช้งาน')).toBeInTheDocument();
  });

  it('omits the subtitle element when none is given', () => {
    const { container } = render(<PageHeader title="จัดการผู้ใช้" />);
    expect(container.querySelector('p')).toBeNull();
  });

  it('renders an optional leading icon alongside the title', () => {
    render(<PageHeader title="Health" icon={<svg data-testid="icon" />} />);
    expect(screen.getByTestId('icon')).toBeInTheDocument();
  });

  it('renders action content on the right', () => {
    render(<PageHeader title="จัดการผู้ใช้" actions={<button>เพิ่มผู้ใช้</button>} />);
    expect(screen.getByRole('button', { name: 'เพิ่มผู้ใช้' })).toBeInTheDocument();
  });
});
