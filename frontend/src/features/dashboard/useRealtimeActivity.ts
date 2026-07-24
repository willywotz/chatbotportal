import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/shared/lib/apiClient';

export interface RealtimeEvent {
  id: string;
  title: string;
  agencies: string[];
  status: string;
  timestamp: Date;
}

const MAX_EVENTS = 50;
const BUCKET_SECONDS = 10;
const MAX_BUCKETS = 30; // 5 minutes of data
const POLL_INTERVAL_MS = 5_000;

export interface ActivityBucket {
  time: string;
  count: number;
}

export function useRealtimeActivity() {
  const [events, setEvents] = useState<RealtimeEvent[]>([]);
  const [buckets, setBuckets] = useState<ActivityBucket[]>(() => initBuckets());
  const bucketsRef = useRef(buckets);
  bucketsRef.current = buckets;

  // Track which conversation IDs we've already seen
  const seenIdsRef = useRef<Set<string>>(new Set());

  function initBuckets(): ActivityBucket[] {
    const now = Date.now();
    return Array.from({ length: MAX_BUCKETS }, (_, i) => ({
      time: formatTime(new Date(now - (MAX_BUCKETS - 1 - i) * BUCKET_SECONDS * 1000)),
      count: 0,
    }));
  }

  function formatTime(d: Date) {
    return d.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  // Shift buckets every BUCKET_SECONDS
  useEffect(() => {
    const interval = setInterval(() => {
      setBuckets((prev) => {
        const newBucket: ActivityBucket = { time: formatTime(new Date()), count: 0 };
        return [...prev.slice(1), newBucket];
      });
    }, BUCKET_SECONDS * 1000);
    return () => clearInterval(interval);
  }, []);

  const handleInsert = useCallback((row: { id: string; title?: string; agencies?: string[]; status?: string }) => {
    const event: RealtimeEvent = {
      id: row.id,
      title: row.title || 'สนทนาใหม่',
      agencies: row.agencies || [],
      status: row.status || 'success',
      timestamp: new Date(),
    };

    setEvents((prev) => [event, ...prev].slice(0, MAX_EVENTS));

    // Increment the last activity bucket
    setBuckets((prev) => {
      const updated = [...prev];
      updated[updated.length - 1] = {
        ...updated[updated.length - 1],
        count: updated[updated.length - 1].count + 1,
      };
      return updated;
    });
  }, []);

  // Poll for new conversations every POLL_INTERVAL_MS
  useEffect(() => {
    let isFirstPoll = true;

    const poll = async () => {
      try {
        const result = await api.get<{ data: Array<{ id: string; title: string; agencies: string[]; status: string }> }>(
          '/api/v1/history?limit=20'
        );
        const conversations = result?.data ?? [];

        const newOnes: typeof conversations = [];
        for (const conv of conversations) {
          if (!seenIdsRef.current.has(conv.id)) {
            seenIdsRef.current.add(conv.id);
            if (!isFirstPoll) newOnes.push(conv);
          }
        }

        newOnes.forEach(handleInsert);
        isFirstPoll = false;
      } catch {
        // Silently ignore polling errors (e.g. when not logged in)
      }
    };

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [handleInsert]);

  return { events, buckets, totalLive: events.length };
}
