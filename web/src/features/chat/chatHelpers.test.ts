import { describe, it, expect } from 'vitest';
import {
  INITIAL_STREAMING_STATE,
  STEP_LABELS,
  buildAgentStepsFromStreaming,
  buildAgentStepsSnapshot,
  applyStepEvent,
  applyAgenciesEvent,
  applyIntentEvent,
  applyRoutingEvent,
  applyAgencyStartEvent,
  applyAgencyRespondedEvent,
  applyAgencyVerifiedEvent,
  applyAnswerEvent,
  applyDoneEvent,
  applyErrorEvent,
  buildAiMessageFromState,
  buildConnectionLostMessage,
  buildGenericErrorMessage,
} from './chatHelpers';
import type { StreamingState } from '@/shared/types';

function baseState(): StreamingState {
  return { ...INITIAL_STREAMING_STATE };
}

describe('STEP_LABELS', () => {
  it('has entries for all five pipeline steps', () => {
    const steps = ['discover', 'classify', 'invoke', 'verify', 'synthesize'];
    for (const step of steps) {
      expect(STEP_LABELS[step]).toBeDefined();
      expect(STEP_LABELS[step].icon).toBeTruthy();
      expect(STEP_LABELS[step].label).toBeTruthy();
    }
  });
});

describe('buildAgentStepsFromStreaming', () => {
  it('returns empty array for empty state', () => {
    expect(buildAgentStepsFromStreaming(baseState())).toEqual([]);
  });

  it('maps a running pipeline step to active status', () => {
    const state: StreamingState = {
      ...baseState(),
      pipelineSteps: [{ name: 'discover', status: 'running', ms: null }],
    };
    const steps = buildAgentStepsFromStreaming(state);
    expect(steps).toHaveLength(1);
    expect(steps[0].status).toBe('active');
    expect(steps[0].icon).toBe(STEP_LABELS.discover.icon);
  });

  it('maps a done pipeline step and includes duration', () => {
    const state: StreamingState = {
      ...baseState(),
      pipelineSteps: [{ name: 'classify', status: 'done', ms: 1500 }],
    };
    const [step] = buildAgentStepsFromStreaming(state);
    expect(step.status).toBe('done');
    expect(step.label).toContain('1.5s');
  });

  it('falls back to gear icon and raw name for unknown step', () => {
    const state: StreamingState = {
      ...baseState(),
      // Cast to satisfy the type while still testing unknown names
      pipelineSteps: [{ name: 'unknown_step' as 'discover', status: 'done', ms: null }],
    };
    const [step] = buildAgentStepsFromStreaming(state);
    expect(step.icon).toBe('⚙️');
    expect(step.label).toContain('unknown_step');
  });

  it('appends agency statuses as steps', () => {
    const state: StreamingState = {
      ...baseState(),
      agencyStatuses: {
        dbd: {
          agencyId: 'dbd',
          agencyName: 'DBD',
          query: 'test',
          sectionLabel: null,
          status: 'passed',
        },
      },
    };
    const steps = buildAgentStepsFromStreaming(state);
    expect(steps).toHaveLength(1);
    expect(steps[0].label).toBe('DBD');
    expect(steps[0].icon).toBe('✅');
    expect(steps[0].status).toBe('done');
  });

  it('uses agencyId as label fallback when agencyName is null', () => {
    const state: StreamingState = {
      ...baseState(),
      agencyStatuses: {
        rd: {
          agencyId: 'rd',
          agencyName: null,
          query: '',
          sectionLabel: null,
          status: 'running',
        },
      },
    };
    const [step] = buildAgentStepsFromStreaming(state);
    expect(step.label).toBe('rd');
    expect(step.status).toBe('active');
  });
});

describe('applyStepEvent', () => {
  it('adds a new running step', () => {
    const next = applyStepEvent(baseState(), { name: 'discover', status: 'running', ms: null });
    expect(next.pipelineSteps).toHaveLength(1);
    expect(next.pipelineSteps[0]).toEqual({ name: 'discover', status: 'running', ms: null });
    expect(next.currentStep).toBe('discover');
  });

  it('updates existing running step to done', () => {
    const state = applyStepEvent(baseState(), { name: 'discover', status: 'running', ms: null });
    const next = applyStepEvent(state, { name: 'discover', status: 'done', ms: 800 });
    expect(next.pipelineSteps).toHaveLength(1);
    expect(next.pipelineSteps[0]).toEqual({ name: 'discover', status: 'done', ms: 800 });
    expect(next.currentStep).toBe('discover');
  });

  it('adds a done step directly when no matching running step exists', () => {
    const next = applyStepEvent(baseState(), { name: 'classify', status: 'done', ms: 200 });
    expect(next.pipelineSteps).toHaveLength(1);
    expect(next.pipelineSteps[0].status).toBe('done');
  });

  it('does not mutate the previous state', () => {
    const prev = baseState();
    applyStepEvent(prev, { name: 'discover', status: 'running', ms: null });
    expect(prev.pipelineSteps).toHaveLength(0);
  });
});

describe('applyAgenciesEvent', () => {
  it('sets the agencies list', () => {
    const agencies = [{ id: 'dbd', name: 'DBD', description: null, data_scope: [] }];
    const next = applyAgenciesEvent(baseState(), { agencies, count: 1 });
    expect(next.agencies).toEqual(agencies);
  });
});

describe('applyIntentEvent', () => {
  it('stores the intent event', () => {
    const event = { intent: 'search' as const, normalized_query: 'tax', reasoning: null };
    const next = applyIntentEvent(baseState(), event);
    expect(next.intent).toEqual(event);
  });
});

describe('applyRoutingEvent', () => {
  it('stores the routing event', () => {
    const event = { sub_questions: [] };
    const next = applyRoutingEvent(baseState(), event);
    expect(next.routing).toEqual(event);
  });
});

describe('applyAgencyStartEvent', () => {
  it('adds agency with running status', () => {
    const event = {
      agency_id: 'rd',
      agency_name: 'Revenue Dept',
      query: 'tax refund',
      section_label: 'Tax',
    };
    const next = applyAgencyStartEvent(baseState(), event);
    expect(next.agencyStatuses['rd']).toMatchObject({
      agencyId: 'rd',
      agencyName: 'Revenue Dept',
      status: 'running',
    });
  });
});

describe('applyAgencyRespondedEvent', () => {
  it('updates existing agency status to ok', () => {
    const start = applyAgencyStartEvent(baseState(), {
      agency_id: 'dbd',
      agency_name: 'DBD',
      query: 'business',
      section_label: null,
    });
    const next = applyAgencyRespondedEvent(start, {
      agency_id: 'dbd',
      agency_name: 'DBD',
      status: 'ok',
      section_label: null,
      error_type: null,
    });
    expect(next.agencyStatuses['dbd'].status).toBe('ok');
  });

  it('sets status to error for error response', () => {
    const next = applyAgencyRespondedEvent(baseState(), {
      agency_id: 'rd',
      agency_name: null,
      status: 'error',
      section_label: null,
      error_type: 'timeout',
    });
    expect(next.agencyStatuses['rd'].status).toBe('error');
    expect(next.agencyStatuses['rd'].errorType).toBe('timeout');
  });

  it('creates an entry from scratch when agency_start was not received', () => {
    const next = applyAgencyRespondedEvent(baseState(), {
      agency_id: 'new',
      agency_name: 'New Agency',
      status: 'ok',
      section_label: null,
      error_type: null,
    });
    expect(next.agencyStatuses['new']).toBeDefined();
    expect(next.agencyStatuses['new'].status).toBe('ok');
  });
});

describe('applyAgencyVerifiedEvent', () => {
  it('updates agency to passed with relevance score', () => {
    const state = applyAgencyStartEvent(baseState(), {
      agency_id: 'dbd',
      agency_name: 'DBD',
      query: '',
      section_label: null,
    });
    const next = applyAgencyVerifiedEvent(state, {
      agency_id: 'dbd',
      agency_name: 'DBD',
      status: 'passed',
      relevance_score: 0.9,
      section_label: null,
    });
    expect(next.agencyStatuses['dbd'].status).toBe('passed');
    expect(next.agencyStatuses['dbd'].relevanceScore).toBe(0.9);
  });

  it('is a no-op when agency does not exist in state', () => {
    const next = applyAgencyVerifiedEvent(baseState(), {
      agency_id: 'missing',
      agency_name: null,
      status: 'rejected',
      relevance_score: null,
      section_label: null,
    });
    expect(next.agencyStatuses['missing']).toBeUndefined();
  });
});

describe('applyAnswerEvent', () => {
  it('stores answer, sections, and errors', () => {
    const event = {
      answer: 'Here is your answer.',
      sections: [{ title: 'Tax', agencies: [{ id: 'rd', name: 'RD', query: 'q', content: 'c' }] }],
      errors: [],
      debug: null,
    };
    const next = applyAnswerEvent(baseState(), event);
    expect(next.answer).toBe('Here is your answer.');
    expect(next.sections).toHaveLength(1);
    expect(next.errors).toHaveLength(0);
  });
});

describe('applyDoneEvent', () => {
  it('marks state as done and stores session_id + total_ms', () => {
    const next = applyDoneEvent(baseState(), { session_id: 'sess-123', total_ms: 4200 });
    expect(next.done).toBe(true);
    expect(next.sessionId).toBe('sess-123');
    expect(next.totalMs).toBe(4200);
  });

  it('stores message_id when the done event includes it', () => {
    const next = applyDoneEvent(baseState(), { session_id: 'sess-1', total_ms: 1, message_id: 'db-msg-1' });
    expect(next.messageId).toBe('db-msg-1');
  });
});

describe('applyErrorEvent', () => {
  it('appends an SSE error and marks done', () => {
    const next = applyErrorEvent(baseState(), { message: 'stream failed', code: 500 });
    expect(next.done).toBe(true);
    expect(next.errors).toHaveLength(1);
    expect(next.errors[0].errorType).toBe('SSE');
    expect(next.errors[0].message).toBe('stream failed');
  });

  it('accumulates multiple errors', () => {
    const s1 = applyErrorEvent(baseState(), { message: 'err1', code: 500 });
    const s2 = applyErrorEvent(s1, { message: 'err2', code: 503 });
    expect(s2.errors).toHaveLength(2);
  });
});

describe('buildAiMessageFromState', () => {
  it('returns null when there is no answer', () => {
    expect(buildAiMessageFromState(baseState())).toBeNull();
  });

  it('builds a ChatMessage from a complete state', () => {
    const state = applyAnswerEvent(
      applyDoneEvent(
        applyStepEvent(baseState(), { name: 'synthesize', status: 'done', ms: 500 }),
        { session_id: 'sess-1', total_ms: 1000 },
      ),
      {
        answer: 'The answer is 42.',
        sections: [{ title: 'General', agencies: [{ id: 'nso', name: 'NSO', query: 'q', content: 'c' }] }],
        errors: [],
        debug: null,
      },
    );
    const msg = buildAiMessageFromState(state);
    expect(msg).not.toBeNull();
    expect(msg!.role).toBe('assistant');
    expect(msg!.content).toBe('The answer is 42.');
    expect(msg!.agentSteps).toHaveLength(1);
    expect(msg!.sources).toHaveLength(1);
    expect(msg!.sources![0].agency).toBe('NSO');
    expect(msg!.sources![0].title).toBe('General');
    expect(msg!.rating).toBeNull();
  });

  it('uses the DB messageId as the message id when present', () => {
    const state = applyAnswerEvent(
      applyDoneEvent(baseState(), { session_id: 'sess-1', total_ms: 1, message_id: 'db-msg-1' }),
      { answer: 'hi', sections: [], errors: [], debug: null },
    );
    const msg = buildAiMessageFromState(state);
    expect(msg!.id).toBe('db-msg-1');
  });
});

describe('buildAgentStepsSnapshot', () => {
  it('returns null when nothing was captured', () => {
    expect(buildAgentStepsSnapshot(INITIAL_STREAMING_STATE)).toBeNull();
  });

  it('tolerates a partial state missing agencyStatuses and errors', () => {
    expect(buildAgentStepsSnapshot({ pipelineSteps: [] } as never)).toBeNull();
  });

  it('captures done steps, agency statuses, and errors', () => {
    const state = {
      ...INITIAL_STREAMING_STATE,
      pipelineSteps: [
        { name: 'discover', status: 'done', ms: 1200 },
        { name: 'invoke', status: 'running', ms: null },
      ],
      agencyStatuses: {
        land: { agencyId: 'land', agencyName: 'กรมที่ดิน', query: 'q',
                sectionLabel: 'fees', status: 'passed', relevanceScore: 0.9 },
      },
      errors: [{ agency: 'x', name: 'X', errorType: 'timeout', message: 'm' }],
    } as never;
    const snap = buildAgentStepsSnapshot(state)!;
    expect(snap.steps).toEqual([{ name: 'discover', ms: 1200 }]);
    expect(snap.agencies[0]).toMatchObject({ id: 'land', status: 'passed', relevanceScore: 0.9 });
    expect(snap.errors[0]).toMatchObject({ errorType: 'timeout' });
  });
});

describe('buildConnectionLostMessage', () => {
  it('returns an assistant message with the connection-lost text', () => {
    const msg = buildConnectionLostMessage();
    expect(msg.role).toBe('assistant');
    expect(msg.content).toContain('การเชื่อมต่อถูกตัด');
    expect(msg.rating).toBeNull();
  });
});

describe('buildGenericErrorMessage', () => {
  it('returns an assistant message with the generic error text', () => {
    const msg = buildGenericErrorMessage();
    expect(msg.role).toBe('assistant');
    expect(msg.content).toContain('ไม่สามารถตอบคำถาม');
    expect(msg.rating).toBeNull();
  });
});

describe('v5 streaming fields', () => {
  it('records the summarize step with a Thai label', () => {
    const state = applyStepEvent(baseState(), { name: 'summarize', status: 'running', ms: null });
    expect(state.currentStep).toBe('summarize');
    expect(buildAgentStepsFromStreaming(state)[0].label).toBe('สรุปภาพรวม');
  });

  it('stores summary and references from the answer event', () => {
    const state = applyAnswerEvent(baseState(), {
      answer: 'สรุป [1]\n\n---\n\n## หัวข้อ\n\nเนื้อหา',
      summary: 'สรุป [1]',
      references: [{ number: 1, agency_id: 'land', agency_name: 'กรมที่ดิน', url: null }],
      sections: [],
      errors: [],
      debug: null,
    });
    expect(state.summary).toBe('สรุป [1]');
    expect(state.summaryReferences[0].agency_name).toBe('กรมที่ดิน');
  });

  it('defaults summary and references when the upstream omits them (v4 mode)', () => {
    const state = applyAnswerEvent(baseState(), {
      answer: 'คำตอบ', sections: [], errors: [], debug: null,
    } as never);
    expect(state.summary).toBeNull();
    expect(state.summaryReferences).toEqual([]);
  });

  it('records thread_name from the done event', () => {
    const state = applyDoneEvent(baseState(), {
      session_id: 's', total_ms: 1, thread_name: 'ค่าธรรมเนียมโอนที่ดิน',
    });
    expect(state.threadName).toBe('ค่าธรรมเนียมโอนที่ดิน');
  });

  it('carries summary onto the built assistant message', () => {
    const withAnswer = {
      ...baseState(),
      answer: 'สรุป [1]\n\n---\n\nเนื้อหา',
      summary: 'สรุป [1]',
      summaryReferences: [{ number: 1, agency_id: 'land', agency_name: 'กรมที่ดิน', url: null }],
    };
    const msg = buildAiMessageFromState(withAnswer);
    expect(msg?.summary).toBe('สรุป [1]');
    expect(msg?.summaryReferences).toHaveLength(1);
  });
});

describe('full pipeline state simulation', () => {
  it('processes a realistic SSE event sequence end-to-end', () => {
    let state = baseState();

    state = applyStepEvent(state, { name: 'discover', status: 'running', ms: null });
    expect(state.currentStep).toBe('discover');

    state = applyAgenciesEvent(state, {
      agencies: [{ id: 'dbd', name: 'DBD', description: null, data_scope: [] }],
      count: 1,
    });
    expect(state.agencies).toHaveLength(1);

    state = applyStepEvent(state, { name: 'discover', status: 'done', ms: 300 });
    expect(state.pipelineSteps[0].status).toBe('done');

    state = applyIntentEvent(state, { intent: 'search', normalized_query: 'company registration', reasoning: null });
    expect(state.intent?.intent).toBe('search');

    state = applyRoutingEvent(state, {
      sub_questions: [{ section_label: 'Registration', broadcast: false, agencies: [{ id: 'dbd', name: 'DBD', query: 'reg' }] }],
    });
    expect(state.routing?.sub_questions).toHaveLength(1);

    state = applyAgencyStartEvent(state, { agency_id: 'dbd', agency_name: 'DBD', query: 'reg', section_label: 'Registration' });
    expect(state.agencyStatuses['dbd'].status).toBe('running');

    state = applyAgencyRespondedEvent(state, { agency_id: 'dbd', agency_name: 'DBD', status: 'ok', section_label: null, error_type: null });
    expect(state.agencyStatuses['dbd'].status).toBe('ok');

    state = applyAgencyVerifiedEvent(state, { agency_id: 'dbd', agency_name: 'DBD', status: 'passed', relevance_score: 0.95, section_label: null });
    expect(state.agencyStatuses['dbd'].status).toBe('passed');

    state = applyAnswerEvent(state, {
      answer: 'You can register a company at DBD.',
      sections: [{ title: 'Registration', agencies: [{ id: 'dbd', name: 'DBD', query: 'reg', content: 'details' }] }],
      errors: [],
      debug: null,
    });
    expect(state.answer).toBeTruthy();

    state = applyDoneEvent(state, { session_id: 'sess-abc', total_ms: 2500 });
    expect(state.done).toBe(true);
    expect(state.sessionId).toBe('sess-abc');

    const msg = buildAiMessageFromState(state);
    expect(msg).not.toBeNull();
    expect(msg!.content).toBe('You can register a company at DBD.');
    expect(msg!.agentSteps!.length).toBeGreaterThan(0);
  });
});
