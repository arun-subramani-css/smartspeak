import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TimelineChart } from '../components/TimelineChart';
import { RecentReports } from '../components/RecentReports';
import { SessionCompare } from '../components/SessionCompare';
import { ImprovementPlan } from '../components/ImprovementPlan';
import { VideoUploader } from '../components/VideoUploader';
import { ReportVideoProvider } from '../components/ReportVideoPlayer';
import { InteractiveTranscript } from '../components/InteractiveTranscript';
import { humanizeMistakeDescription } from '../components/mistakeText';
import { StatusTracker, rewriteFor } from '../components/StatusTracker';
import { fireEvent } from '@testing-library/react';
import { PhonePairPanel } from '../components/PhonePairPanel';
import { PhonePair } from '../components/PhonePair';

// Capture the QR payload so tests can assert on the encoded URL.
vi.mock('qrcode.react', async () => {
  const React = await import('react');
  return {
    QRCodeSVG: (props) =>
      React.createElement('svg', { 'data-testid': 'qr-code', 'data-value': props.value }),
  };
});

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

  it('rewrites legacy compound-mistake labels into coach language', () => {
    expect(humanizeMistakeDescription(
      'Compound behavioral cue: correlated repetition: i am, looking_down',
    )).toBe("Repeated 'i am' while looking down.");
    expect(humanizeMistakeDescription(
      'Compound behavioral cue: correlated filler_word: um, looking_down',
    )).toBe("Used the filler 'um' while looking down.");
    expect(humanizeMistakeDescription('Used filler word \'um\'')).toBe('Used filler word \'um\'');
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

// ---- AI rewrite callouts (StatusTracker) -------------------------------------

describe('rewriteFor matching', () => {
  it('pairs only speech/compound mistakes with a timestamp-matched rewrite', () => {
    const rewrites = [
      { timestamp: 6.2, mistake_type: 'filler_word', original_segment: 'a', rewritten_segment: 'b' },
    ];
    expect(rewriteFor(rewrites, { timestamp: 6.2, category: 'speech' })).toBe(rewrites[0]);
    expect(rewriteFor(rewrites, { timestamp: 6.22, category: 'compound' })).toBe(rewrites[0]);
    expect(rewriteFor(rewrites, { timestamp: 6.3, category: 'speech' })).toBeNull();
    expect(rewriteFor(rewrites, { timestamp: 6.2, category: 'visual' })).toBeNull();
    expect(rewriteFor([], { timestamp: 6.2, category: 'speech' })).toBeNull();
    expect(rewriteFor(null, { timestamp: 6.2, category: 'speech' })).toBeNull();
  });
});

describe('AI rewrite callouts in StatusTracker', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const statusPayload = {
    status: 'fusion_complete',
    has_speech_analysis: true,
    has_visual_analysis: true,
    has_fusion_report: true,
  };

  const fusionWithRewrites = {
    smartspeak_index: 78.4,
    grade: 'Polished',
    verbal_score: 80,
    non_verbal_score: 75,
    ml_confidence_score: 82,
    mistakes: [
      { timestamp: 6.2, category: 'speech', description: "Used filler word 'um'", severity: 'minor', events: ['filler_word: um'] },
      { timestamp: 12.3, category: 'compound', description: 'Repeated stuff while looking down', severity: 'medium', events: ['repetition: stuff'] },
      { timestamp: 20, category: 'visual', description: 'Looking away from audience', severity: 'minor', events: ['looking_away'] },
    ],
    rewrites: [
      { original_segment: 'um so i am going there.', rewritten_segment: 'So I am going there.', mistake_type: 'filler_word', timestamp: 6.2 },
      { original_segment: 'and uh stuff.', rewritten_segment: 'And stuff.', mistake_type: 'repetition', timestamp: 12.3 },
    ],
  };

  function mockFetchByPath(payloads) {
    return vi.fn((url) => {
      const path = String(url);
      const key = Object.keys(payloads).find((k) => path.includes(k));
      return Promise.resolve({ ok: true, json: () => Promise.resolve(key ? payloads[key] : {}) });
    });
  }

  it('shows original vs rewritten text under the flagged speech mistakes', async () => {
    global.fetch = mockFetchByPath({
      '/status': statusPayload,
      '/fusion-report': { fusion_report: fusionWithRewrites },
      '/speech-analysis': { speech_analysis: speechAnalysis },
      '/visual-analysis': { visual_analysis: visualAnalysis },
      '/video/status': { available: false },
    });
    const { container } = render(<StatusTracker sessionId="t-rewrite" onReset={() => {}} />);
    expect((await screen.findAllByText('Suggested rewrite')).length).toBeGreaterThan(0);
    // Original (muted, struck through) vs rewritten (highlighted)
    expect(container.textContent).toContain('um so i am going there.');
    expect(container.textContent).toContain('So I am going there.');
    // Two callouts: the speech + compound mistakes; the visual mistake at 20s has none
    expect(screen.getAllByText('Suggested rewrite')).toHaveLength(2);
  });

  it('renders no callout when the report carries no rewrites', async () => {
    global.fetch = mockFetchByPath({
      '/status': statusPayload,
      '/fusion-report': { fusion_report: { ...fusionWithRewrites, rewrites: [] } },
      '/speech-analysis': { speech_analysis: speechAnalysis },
      '/visual-analysis': { visual_analysis: visualAnalysis },
      '/video/status': { available: false },
    });
    render(<StatusTracker sessionId="t-rewrite-none" onReset={() => {}} />);
    expect(await screen.findByText(/Key Behavioral Feedback/)).toBeInTheDocument();
    expect(screen.queryByText('Suggested rewrite')).not.toBeInTheDocument();
  });
});

// ---- Phone pairing: laptop QR panel + phone page ---------------------------

const pairFixture = {
  token: 'tok-abc123',
  phone_url: 'http://192.168.1.7:5173/pair/tok-abc123',
  expires_in: 600,
  status: 'waiting',
};

/** fetch mock covering POST /api/v1/pairing and GET /api/v1/pairing/{token}.
 *  `polls` is consumed one entry per status poll; an entry with httpStatus
 *  simulates an error response, an empty list always answers "waiting". */
function makePairingFetch({ create = pairFixture, polls = [] } = {}) {
  let pollCount = 0;
  return vi.fn((url, init) => {
    const path = String(url);
    if (path === '/api/v1/pairing' && init && init.method === 'POST') {
      return Promise.resolve({ ok: true, status: 201, json: async () => create });
    }
    if (path.startsWith('/api/v1/pairing/')) {
      const next = polls[Math.min(pollCount, Math.max(polls.length - 1, 0))];
      pollCount += 1;
      if (next && next.httpStatus) {
        return Promise.resolve({
          ok: false,
          status: next.httpStatus,
          json: async () => ({ detail: next.detail || 'gone' }),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => next || { status: 'waiting' } });
    }
    return Promise.resolve({ ok: false, status: 404, json: async () => ({}) });
  });
}

describe('PhonePairPanel (laptop QR panel)', () => {
  let savedFetch;
  beforeEach(() => { savedFetch = global.fetch; });
  afterEach(() => { global.fetch = savedFetch; });

  it('renders a QR code encoding the phone URL that contains the token', async () => {
    global.fetch = makePairingFetch();
    render(<PhonePairPanel onSessionReady={() => {}} pollIntervalMs={100000} />);
    const qr = await screen.findByTestId('qr-code');
    expect(qr.getAttribute('data-value')).toContain('/pair/tok-abc123');
    // The URL is also shown as selectable text fallback.
    expect(screen.getByText(pairFixture.phone_url)).toBeInTheDocument();
    expect(screen.getByText(/Waiting for your phone/)).toBeInTheDocument();
  });

  it('hands the session to the report flow when the phone upload lands', async () => {
    global.fetch = makePairingFetch({
      polls: [{ status: 'uploaded', session_id: 'sess-42' }],
    });
    const onSessionReady = vi.fn();
    render(<PhonePairPanel onSessionReady={onSessionReady} pollIntervalMs={15} />);
    await waitFor(() => expect(onSessionReady).toHaveBeenCalledWith('sess-42'));
    expect(await screen.findByText(/Upload received/)).toBeInTheDocument();
  });

  it('shows an expired message when the backend rejects the token (410)', async () => {
    global.fetch = makePairingFetch({ polls: [{ httpStatus: 410, detail: 'expired' }] });
    render(<PhonePairPanel onSessionReady={() => {}} pollIntervalMs={15} />);
    expect(await screen.findByText(/This pairing code expired/)).toBeInTheDocument();
  });

  it('never encodes localhost when no LAN URL exists (no QR, explains why)', async () => {
    global.fetch = makePairingFetch({ create: { ...pairFixture, phone_url: null } });
    render(<PhonePairPanel onSessionReady={() => {}} pollIntervalMs={15} />);
    expect(await screen.findByText(/isn't reachable from your phone/)).toBeInTheDocument();
    expect(screen.queryByTestId('qr-code')).not.toBeInTheDocument();
  });
});

describe('VideoUploader — phone camera fallback', () => {
  let savedFetch;
  beforeEach(() => { savedFetch = global.fetch; });
  afterEach(() => { global.fetch = savedFetch; });

  it('auto-opens the phone pairing panel in Practice mode when no camera exists', async () => {
    global.fetch = makePairingFetch(); // jsdom has no mediaDevices → auto-switch
    render(<VideoUploader onUploadSuccess={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: /practice now/i }));
    expect(await screen.findByText('Practice with your phone')).toBeInTheDocument();
    const qr = await screen.findByTestId('qr-code');
    expect(qr.getAttribute('data-value')).toContain('/pair/tok-abc123');
  });

  it('offers a manual "Use phone camera" button next to the recorder when a camera exists', async () => {
    const savedMedia = Object.getOwnPropertyDescriptor(navigator, 'mediaDevices');
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn(),
        enumerateDevices: vi.fn().mockResolvedValue([{ kind: 'videoinput', deviceId: 'cam1' }]),
      },
    });
    try {
      global.fetch = makePairingFetch();
      render(<VideoUploader onUploadSuccess={() => {}} />);
      await userEvent.click(screen.getByRole('button', { name: /practice now/i }));
      const pairButton = await screen.findByRole('button', { name: /use phone camera/i });
      await userEvent.click(pairButton);
      expect(await screen.findByText('Practice with your phone')).toBeInTheDocument();
    } finally {
      if (savedMedia) Object.defineProperty(navigator, 'mediaDevices', savedMedia);
      else delete navigator.mediaDevices;
    }
  });
});

describe('PhonePair (phone page)', () => {
  let savedFetch;
  let savedSecure;
  let savedMedia;
  let savedRecorder;

  beforeEach(() => {
    savedFetch = global.fetch;
    savedSecure = Object.getOwnPropertyDescriptor(window, 'isSecureContext');
    savedMedia = Object.getOwnPropertyDescriptor(navigator, 'mediaDevices');
    savedRecorder = Object.getOwnPropertyDescriptor(window, 'MediaRecorder');
  });

  afterEach(() => {
    global.fetch = savedFetch;
    if (savedSecure) Object.defineProperty(window, 'isSecureContext', savedSecure);
    else delete window.isSecureContext;
    if (savedMedia) Object.defineProperty(navigator, 'mediaDevices', savedMedia);
    else delete navigator.mediaDevices;
    if (savedRecorder) Object.defineProperty(window, 'MediaRecorder', savedRecorder);
    else delete window.MediaRecorder;
  });

  const waitingFetch = () =>
    vi.fn(() => Promise.resolve({ ok: true, status: 200, json: async () => ({ status: 'waiting' }) }));

  it('falls back to the OS camera button when the page is not a secure context', async () => {
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: false });
    // Even with mediaDevices present, a plain-HTTP origin can't use getUserMedia.
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn() },
    });
    global.fetch = waitingFetch();

    render(<PhonePair token="tok-abc123" />);

    expect(await screen.findByText('Record with your camera')).toBeInTheDocument();
    const input = document.getElementById('phone-capture');
    expect(input).toHaveAttribute('accept', 'video/*');
    expect(input).toHaveAttribute('capture', 'user');
  });

  it('uses the in-page recorder when the context is secure and a camera exists', async () => {
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: true });
    const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [{ stop() {} }] });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    });
    Object.defineProperty(window, 'MediaRecorder', {
      configurable: true,
      value: class { static isTypeSupported() { return false; } },
    });
    global.fetch = waitingFetch();

    render(<PhonePair token="tok-abc123" />);

    expect(await screen.findByText('Start recording')).toBeInTheDocument();
    expect(getUserMedia).toHaveBeenCalled();
    expect(document.getElementById('phone-capture')).toBeNull(); // native input not used
  });

  it('shows a clear message for an invalid pairing token (404)', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 404, json: async () => ({ detail: 'unknown pairing code' }) }));
    render(<PhonePair token="bogus" />);
    expect(await screen.findByText('This pairing code is no longer valid')).toBeInTheDocument();
  });

  it('shows a clear message for an expired pairing token (410)', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 410, json: async () => ({ detail: 'expired' }) }));
    render(<PhonePair token="tok-abc123" />);
    expect(await screen.findByText('This pairing code has expired')).toBeInTheDocument();
  });
});
