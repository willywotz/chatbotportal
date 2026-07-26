import { describe, expect, it } from 'vitest';

import { toAgentStepsSnapshot } from './agentSteps';

describe('toAgentStepsSnapshot', () => {
  it('returns null for empty/array/nullish inputs', () => {
    expect(toAgentStepsSnapshot(null)).toBeNull();
    expect(toAgentStepsSnapshot([])).toBeNull();
    expect(toAgentStepsSnapshot(undefined)).toBeNull();
    expect(toAgentStepsSnapshot({ steps: [], agencies: [], errors: [] })).toBeNull();
  });

  it('maps snake_case persisted shape to camelCase', () => {
    const snap = toAgentStepsSnapshot({
      steps: [{ name: 'discover', ms: 1200 }],
      agencies: [{ id: 'land', name: 'กรมที่ดิน', status: 'passed',
                   error_type: null, relevance_score: 0.9, section_label: 'fees' }],
      errors: [{ agency: 'x', name: 'X', error_type: 'timeout', message: 'm' }],
    })!;
    expect(snap.steps).toEqual([{ name: 'discover', ms: 1200 }]);
    expect(snap.agencies[0]).toEqual({
      id: 'land', name: 'กรมที่ดิน', status: 'passed',
      errorType: null, relevanceScore: 0.9, sectionLabel: 'fees',
    });
    expect(snap.errors[0]).toEqual({ agency: 'x', name: 'X', errorType: 'timeout', message: 'm' });
  });
});
