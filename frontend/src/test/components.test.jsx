import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TimelineChart } from '../components/TimelineChart';
import { RecentReports } from '../components/RecentReports';

// ---- Shared fixtures -------------------------------------------------------

const speechAnalysis = {
  transcript_text: 'Hello world this is a test',
  filler_words: [{ word: 'um', timestamp: 12 }],
  long_pauses: [{ start_time: 20, end_time: 24, duration: 4 }],
  repetitions: [{ phrase: 'like', timestamp: 30, count: 2 }],
  wpm_data: {
    overall_wpm: 140,
    total_words: 26,
    total_speaking_duration_seconds: 60,
    windowed_wpm: [
      { window_start: 0, window_end: 15, wpm: 150 },
      { window_start: 15, window_end: 30, wpm: 120 },
      { window_start: 30, window_end: 45, wpm: 100 },
      { window_start: 45, window_end: 60, wpm: 140 },
    ],
  },
};

const visualAnalysis = {
  eye_contact: {
    eye_contact_percentage: 62.5,
    looking_away_count: 2,
    looking_away_ranges: [
      { start_time: 5, end_time: 9, duration: 4, category: 'looking_away' },
      { start_time: 40, end_time: 46, duration: 6, category: 'looking_down' },
    ],
  },
  posture: {
    posture_score: 88,
    poor_posture_ranges: [{ start_time: 50, end_time: 55, duration: 5 }],
    total_frames_analyzed: 60,
    good_posture_count: 53,
  },
  gesture: {
    active_hand_percentage: 44,
    gesture_usage_classification: 'average',
    gesture_active_ranges: [{ start_time: 10, end_time: 18, duration: 8 }],
  },
  head_movement: {
    head_movement_score: 80,
    excessive_movement_count: 3,
    excessive_movement_timestamps: [15, 33, 58],
  },
};

const fusionReport = {
  smartspeak_index: 78.4,
  grade: 'Polished',
  verbal_score: 80,
  non_verbal_score: 75,
  ml_confidence_score: 82,
  mistakes: [
    {
      timestamp: 42.5,
      category: 'compound',
      description: 'Looking away during a long pause',
      severity: 'medium',
    },
  ],
};

// ---- TimelineChart ----------------------------------------------------------

describe('TimelineChart', () => {
  it('renders the session timeline with a duration axis', () => {
    render(
      <TimelineChart speechAnalysis={speechAnalysis} visualAnalysis={visualAnalysis} fusionReport={fusionReport} />,
    );
    expect(screen.getByText('Session Timeline')).toBeInTheDocument();
    expect(screen.getAllByText(/1m00s/).length).toBeGreaterThan(0); // duration in header + axis
  });

  it('renders the WPM plot svg plus lucide icon svgs', () => {
    const { container } = render(
      <TimelineChart speechAnalysis={speechAnalysis} visualAnalysis={visualAnalysis} fusionReport={fusionReport} />,
    );
    // 1 chart svg + Activity legend icon = 2
    expect(container.querySelectorAll('svg')).toHaveLength(2);
  });

  it('renders a polyline per WPM window plus the baseline', () => {
    const { container } = render(
      <TimelineChart speechAnalysis={speechAnalysis} visualAnalysis={visualAnalysis} fusionReport={fusionReport} />,
    );
    expect(container.querySelectorAll('polyline')).toHaveLength(1);
    // 4 windows -> 4 data circles
    expect(container.querySelectorAll('circle')).toHaveLength(4);
  });

  it('draws the ideal WPM band', () => {
    const { container } = render(
      <TimelineChart speechAnalysis={speechAnalysis} visualAnalysis={visualAnalysis} fusionReport={fusionReport} />,
    );
    expect(container.querySelector('svg text')?.textContent).toContain('ideal');
  });

  it('renders one rect per timeline range across all lanes', () => {
    const { container } = render(
      <TimelineChart speechAnalysis={speechAnalysis} visualAnalysis={visualAnalysis} fusionReport={fusionReport} />,
    );
    // ideal band rect (1) + eye (2) + posture (1) + gesture (1) + pauses lane (1) = 6
    expect(container.querySelectorAll('rect')).toHaveLength(6);
  });

  it('renders marker shapes for fillers, repetitions and mistakes', () => {
    const { container } = render(
      <TimelineChart speechAnalysis={speechAnalysis} visualAnalysis={visualAnalysis} fusionReport={fusionReport} />,
    );
    // ideal band polygon (1) + filler (1) + repetition (1) + mistake (1) = 4
    expect(container.querySelectorAll('polygon')).toHaveLength(4);
  });

  it('hides lanes when the legend chip is toggled off', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <TimelineChart speechAnalysis={speechAnalysis} visualAnalysis={visualAnalysis} fusionReport={fusionReport} />,
    );
    expect(container.querySelectorAll('rect')).toHaveLength(6);
    await user.click(screen.getByRole('button', { name: /Looking Away/i }));
    expect(container.querySelectorAll('rect')).toHaveLength(4); // band + pauses + posture + gesture
  });
});

// ---- RecentReports ----------------------------------------------------------

describe('RecentReports', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const historyPayload = {
    sessions: [
      {
        session_id: 'abc-123',
        original_filename: 'first-talk.mp4',
        upload_timestamp: '2026-09-23T10:00:00Z',
        status: 'fusion_complete',
        file_size: 1024 * 1024,
        smartspeak_index: 72,
        grade: 'Polished',
      },
      {
        session_id: 'def-456',
        original_filename: 'second-talk.mov',
        upload_timestamp: '2026-09-23T11:00:00Z',
        status: 'fusion_complete',
        file_size: 2048 * 1024,
        smartspeak_index: 81.5,
        grade: 'Executive',
      },
    ],
    total: 2,
  };

  function mockFetchOnce(payload, ok = true) {
    return vi.fn(() =>
      Promise.resolve({ ok, json: () => Promise.resolve(payload) }),
    );
  }

  it('renders session rows returned by the history endpoint', async () => {
    global.fetch = mockFetchOnce(historyPayload);
    render(<RecentReports onOpenSession={() => {}} />);
    expect(await screen.findByText('first-talk.mp4')).toBeInTheDocument();
    expect(screen.getByText('second-talk.mov')).toBeInTheDocument();
    expect(screen.getByText(/Recent Reports/)).toBeInTheDocument();
  });

  it('shows grade badges and trend deltas vs the previous session', async () => {
    global.fetch = mockFetchOnce(historyPayload);
    render(<RecentReports onOpenSession={() => {}} />);
    await screen.findByText('second-talk.mov');
    expect(screen.getByText('Executive')).toBeInTheDocument();
    expect(screen.getByText('Polished')).toBeInTheDocument();
    // +9.5 vs prev
    expect(screen.getByText(/9\.5 vs prev/)).toBeInTheDocument();
  });

  it('invokes onOpenSession with the clicked session id', async () => {
    const onOpenSession = vi.fn();
    global.fetch = mockFetchOnce(historyPayload);
    render(<RecentReports onOpenSession={onOpenSession} />);
    await userEvent.click(await screen.findByText('first-talk.mp4'));
    await waitFor(() => expect(onOpenSession).toHaveBeenCalledWith('abc-123'));
  });

  it('renders nothing when there are no completed sessions', async () => {
    global.fetch = mockFetchOnce({ sessions: [], total: 0 });
    const { container } = render(<RecentReports onOpenSession={() => {}} />);
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('renders nothing when the history request fails', async () => {
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    global.fetch = vi.fn(() => Promise.reject(new Error('network down')));
    const { container } = render(<RecentReports onOpenSession={() => {}} />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(errSpy).toHaveBeenCalled();
    errSpy.mockRestore();
  });
});
