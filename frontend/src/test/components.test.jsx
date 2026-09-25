import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TimelineChart } from '../components/TimelineChart';
import { RecentReports } from '../components/RecentReports';
import { SessionCompare } from '../components/SessionCompare';
import { ImprovementPlan } from '../components/ImprovementPlan';
import { VideoUploader } from '../components/VideoUploader';
import { ReportVideoProvider } from '../components/ReportVideoPlayer';
import { InteractiveTranscript } from '../components/InteractiveTranscript';
import { fireEvent } from '@testing-library/react';

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

// ---- SessionCompare ---------------------------------------------------------

describe('SessionCompare', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const comparePayload = {
    older: { session_id: 'old-1', original_filename: 'old-talk.mp4', smartspeak_index: 62, grade: 'Developing' },
    newer: { session_id: 'new-1', original_filename: 'new-talk.mp4', smartspeak_index: 72, grade: 'Polished' },
    score_delta: 10,
    score_direction: 'improved',
    deltas: [
      { metric: 'filler_ratio', label: 'Filler words', unit: '%', older: 9, newer: 3, delta: -6, direction: 'improved', verdict: '-6% vs before' },
      { metric: 'wpm', label: 'Speaking pace', unit: ' WPM', older: 185, newer: 150, delta: -35, direction: 'improved', verdict: 'now in the ideal 130–160 range' },
      { metric: 'eye_contact', label: 'Eye contact', unit: '%', older: 30, newer: 22, delta: -8, direction: 'regressed', verdict: '-8% vs before' },
      { metric: 'posture', label: 'Posture', unit: '%', older: 70, newer: 70, delta: 0, direction: 'same', verdict: 'unchanged' },
    ],
    focus_goal_progress: {
      goal_metric: 'fillers', goal_label: 'Filler words', older_value: 18, newer_value: 6,
      improved: true, summary: 'Filler words improved from 18 to 6',
    },
  };

  const mockCompare = (payload, ok = true) =>
    vi.fn(() => Promise.resolve({ ok, status: ok ? 200 : 400, json: () => Promise.resolve(payload) }));

  it('renders the score delta front and center with both session cards', async () => {
    global.fetch = mockCompare(comparePayload);
    render(<SessionCompare olderId="old-1" newerId="new-1" />);
    expect(await screen.findByText('Session Comparison')).toBeInTheDocument();
    expect(screen.getByText('old-talk.mp4')).toBeInTheDocument();
    expect(screen.getByText('new-talk.mp4')).toBeInTheDocument();
    expect(screen.getByText('+10')).toBeInTheDocument();
    expect(screen.getAllByText('improved').length).toBeGreaterThan(0);
  });

  it('renders metric rows with old → new values and direction chips', async () => {
    global.fetch = mockCompare(comparePayload);
    render(<SessionCompare olderId="old-1" newerId="new-1" />);
    await screen.findByText('Session Comparison');
    expect(screen.getByText('185 WPM')).toBeInTheDocument();   // wpm band metric formatting
    expect(screen.getByText('9%')).toBeInTheDocument();
    expect(screen.getByText('3%')).toBeInTheDocument();
    expect(screen.getByText('regressed')).toBeInTheDocument();  // honest regression chip
    expect(screen.getByText('same')).toBeInTheDocument();
  });

  it('renders the focus-goal progress banner between the sessions', async () => {
    global.fetch = mockCompare(comparePayload);
    render(<SessionCompare olderId="old-1" newerId="new-1" />);
    await screen.findByText('Session Comparison');
    expect(screen.getByText(/Focus goal was filler words/i)).toBeInTheDocument();
    expect(screen.getByText(/improved from 18 to 6/)).toBeInTheDocument();
  });

  it('hides the goal banner when the older session predates focus goals', async () => {
    global.fetch = mockCompare({ ...comparePayload, focus_goal_progress: null });
    render(<SessionCompare olderId="old-1" newerId="new-1" />);
    await screen.findByText('Session Comparison');
    expect(screen.queryByText(/Focus goal was/i)).not.toBeInTheDocument();
  });

  it('shows a friendly error with a working Close button on failure', async () => {
    global.fetch = mockCompare({ detail: 'Session not found' }, false);
    const onClose = vi.fn();
    render(<SessionCompare olderId="gone" newerId="new-1" onClose={onClose} />);
    expect(await screen.findByText('Comparison unavailable')).toBeInTheDocument();
    expect(screen.getByText('Session not found')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('invokes onOpenSession when a session card is clicked', async () => {
    global.fetch = mockCompare(comparePayload);
    const onOpenSession = vi.fn();
    render(<SessionCompare olderId="old-1" newerId="new-1" onOpenSession={onOpenSession} />);
    await screen.findByText('Session Comparison');
    await userEvent.click(screen.getByText('new-talk.mp4'));
    expect(onOpenSession).toHaveBeenCalledWith('new-1');
  });

  it('explains when there are no comparable metrics', async () => {
    global.fetch = mockCompare({ ...comparePayload, deltas: [] });
    render(<SessionCompare olderId="old-1" newerId="new-1" />);
    expect(await screen.findByText(/No comparable metrics/)).toBeInTheDocument();
  });
});

// ---- ImprovementPlan --------------------------------------------------------

describe('ImprovementPlan', () => {
  it('renders nothing for a clean report with no plan and no previous goal', () => {
    const { container } = render(<ImprovementPlan fusionReport={{ smartspeak_index: 90 }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the ranked plan with real current values', () => {
    const report = {
      improvement_plan: [
        { metric: 'fillers', title: 'Cut filler words', drill: "You used 'um' 8 times — pause silently instead", current_value: 8 },
        { metric: 'posture', title: 'Reset your stance', drill: '18 of 90 frames showed slouched shoulders', current_value: 80 },
      ],
    };
    render(<ImprovementPlan fusionReport={report} />);
    expect(screen.getByText('Your improvement plan')).toBeInTheDocument();
    expect(screen.getByText('Cut filler words')).toBeInTheDocument();
    expect(screen.getByText(/pause silently instead/)).toBeInTheDocument();
    // Rank badges and per-metric labels
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getAllByText('Filler words').length).toBeGreaterThan(0);
    // "now" values formatted per metric
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getByText('80%')).toBeInTheDocument();
  });

  it("shows 'target met' when the previous goal is absent from this plan", () => {
    const report = {
      previous_focus_goal: 'fillers',
      improvement_plan: [
        { metric: 'posture', title: 'Reset your stance', drill: 'slouched shoulders', current_value: 80 },
      ],
    };
    render(<ImprovementPlan fusionReport={report} />);
    expect(screen.getByText(/Last session's focus/i)).toBeInTheDocument();
    expect(screen.getByText(/target met this session/)).toBeInTheDocument();
  });

  it('shows the remaining gap when the previous goal is still in the plan', () => {
    const report = {
      previous_focus_goal: 'eye_contact',
      improvement_plan: [
        { metric: 'eye_contact', title: 'Anchor your gaze', drill: '49% eye contact', current_value: 49 },
      ],
    };
    render(<ImprovementPlan fusionReport={report} />);
    // target min 60% -> 11 points away
    expect(screen.getByText(/~11% away/)).toBeInTheDocument();
  });

  it('uses the healthy-range wording for band goals like pace', () => {
    const report = {
      previous_focus_goal: 'wpm',
      improvement_plan: [
        { metric: 'fillers', title: 'Cut filler words', drill: 'pause silently', current_value: 4 },
      ],
    };
    render(<ImprovementPlan fusionReport={report} />);
    expect(screen.getByText(/now within the healthy range/)).toBeInTheDocument();
  });
});

// ---- VideoUploader ----------------------------------------------------------

describe('VideoUploader', () => {
  it('sends the selected file when Start Analysis is clicked (regression: click event passed as file)', async () => {
    const openCalls = [];
    class MockXHR {
      constructor() { this.upload = {}; }
      open(method, url) { openCalls.push({ method, url }); }
      send() {
        this.status = 201;
        this.responseText = JSON.stringify({ session_id: 's-regression-1' });
        this.onload?.();
      }
    }
    const originalXHR = global.XMLHttpRequest;
    global.XMLHttpRequest = MockXHR;
    try {
      const onUploadSuccess = vi.fn();
      render(<VideoUploader onUploadSuccess={onUploadSuccess} />);

      const file = new File([new Uint8Array(64)], 'take.mp4', { type: 'video/mp4' });
      fireEvent.drop(screen.getByRole('button', { name: /drag and drop/i }), { dataTransfer: { files: [file] } });

      const cta = screen.getByRole('button', { name: /start analysis/i });
      expect(cta).not.toBeDisabled();
      await userEvent.click(cta); // crashed with TypeError before the () => handleUpload() fix

      await waitFor(() => expect(openCalls[0]).toEqual({ method: 'POST', url: '/api/v1/upload' }));
      await waitFor(() => expect(onUploadSuccess).toHaveBeenCalledWith('s-regression-1'));
    } finally {
      global.XMLHttpRequest = originalXHR;
    }
  });

  it('rejects unsupported extensions with a visible alert', () => {
    render(<VideoUploader onUploadSuccess={() => {}} />);
    const file = new File([new Uint8Array(64)], 'clip.txt', { type: 'text/plain' });
    fireEvent.drop(screen.getByRole('button', { name: /drag and drop/i }), { dataTransfer: { files: [file] } });
    expect(screen.getByRole('alert')).toHaveTextContent(/unsupported file format/i);
  });
});

// ---- InteractiveTranscript --------------------------------------------------

describe('InteractiveTranscript', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    // Provider probes video availability; return "unavailable" deterministically.
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ available: false }) }));
  });

  const speechWithWordsAndPauses = {
    transcript_text: 'I think that was good',
    words: [
      { word: 'I', start: 0.0, end: 0.2 },
      { word: 'think', start: 0.3, end: 0.7 },
      { word: 'that', start: 0.8, end: 1.1 },
      { word: 'was', start: 1.2, end: 1.5 },
      { word: 'good', start: 1.6, end: 2.0 },
    ],
    filler_words: [{ word: 'I', timestamp: 0.1 }],
    repetitions: [],
    long_pauses: [{ start_time: 1.1, end_time: 5.3, duration: 4.2 }],
  };

  it('renders word-timed text with pause pills (regression: ReferenceError on p vs pause)', async () => {
    render(
      <ReportVideoProvider sessionId="t-transcript">
        <InteractiveTranscript speechAnalysis={speechWithWordsAndPauses} />
      </ReportVideoProvider>,
    );
    // Words render inline...
    expect(screen.getByText('think')).toBeInTheDocument();
    // ...and the long pause renders as a pill with its real duration
    // (crashed with "p is not defined" before the pause/p variable fix)
    expect(screen.getByTitle('Long pause (4.2s)')).toBeInTheDocument();
  });

  it('falls back to proportional highlighting when word timings are missing', () => {
    const { container } = render(
      <ReportVideoProvider sessionId="t-transcript">
        <InteractiveTranscript
          speechAnalysis={{
            transcript_text: 'um so we did the thing',
            filler_words: [{ word: 'um', timestamp: 1 }],
            repetitions: [],
            long_pauses: [],
          }}
        />
      </ReportVideoProvider>,
    );
    // Proportional mode marks an estimated slice (position, not exact word)
    expect(container.querySelectorAll('mark').length).toBeGreaterThan(0);
    expect(container.querySelector('mark')?.getAttribute('title')).toContain('um');
    expect(container.textContent).toContain('um so we did the thing');
  });
});
