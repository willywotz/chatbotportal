import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { server } from '@/mocks/server';

import { queryAgency } from './agencyApi';

describe('queryAgency — unified chat envelope mapping', () => {
  it('falls back to summary/agency_name when answer/title are absent', async () => {
    server.use(
      http.post('*/api/v1/chat', () =>
        HttpResponse.json({
          success: true,
          data: {
            message_id: 'msg-1',
            cached: false,
            agentSteps: [],
            summary: 'revenue summary',
            references: [{ agency_name: 'Revenue Department', url: 'https://rd.go.th' }],
          },
          conversation_id: 'conv-1',
          responseTime: 5,
        })
      )
    );

    const res = await queryAgency('revenue', 'how do I pay tax?');

    expect(res.data.answer).toBe('revenue summary');
    expect(res.data.references).toEqual([{ title: 'Revenue Department', url: 'https://rd.go.th' }]);
    expect(res.agencyName).toBe('Revenue Department');
    expect(res.data.confidence).toBe(0);
  });
});
