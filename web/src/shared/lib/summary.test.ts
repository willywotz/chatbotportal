import { describe, it, expect } from 'vitest';
import { stripSummaryPrefix } from './summary';

const SUMMARY = 'สรุปครับ ค่าธรรมเนียมอยู่ที่ 2% [1]';
const BODY = '## ค่าธรรมเนียมโอนที่ดิน\n\nค่าธรรมเนียมการโอนคือ 2% ของราคาประเมิน';

describe('stripSummaryPrefix', () => {
  it('removes the summary, reference list and divider', () => {
    const content = `${SUMMARY}\n\n**อ้างอิง**\n\n[1] กรมที่ดิน\n\n---\n\n${BODY}`;
    expect(stripSummaryPrefix(content, SUMMARY)).toBe(BODY);
  });

  it('returns content unchanged when there is no summary', () => {
    expect(stripSummaryPrefix(BODY, null)).toBe(BODY);
    expect(stripSummaryPrefix(BODY, '')).toBe(BODY);
    expect(stripSummaryPrefix(BODY, undefined)).toBe(BODY);
  });

  it('returns content unchanged when the summary is not the prefix', () => {
    expect(stripSummaryPrefix(BODY, 'ข้อความอื่น')).toBe(BODY);
  });

  it('splits on the first divider only, preserving rules inside agency content', () => {
    const content = `${SUMMARY}\n\n---\n\n${BODY}\n\n---\n\nเนื้อหาเพิ่มเติม`;
    expect(stripSummaryPrefix(content, SUMMARY)).toBe(`${BODY}\n\n---\n\nเนื้อหาเพิ่มเติม`);
  });

  it('drops the summary prefix even when no divider follows', () => {
    const content = `${SUMMARY}\n\n${BODY}`;
    expect(stripSummaryPrefix(content, SUMMARY)).toBe(BODY);
  });

  it('returns an empty body when the answer is summary-only', () => {
    expect(stripSummaryPrefix(SUMMARY, SUMMARY)).toBe('');
  });
});
