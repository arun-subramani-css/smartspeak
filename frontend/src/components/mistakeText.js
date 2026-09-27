/**
 * Humanizes raw compound-mistake descriptions for display.
 *
 * Reports store machine labels joined into a sentence like
 * "Compound behavioral cue: correlated repetition: i am, looking_down"
 * — unintelligible to users. This rewrites them into coach language
 * ("Repeated 'i am' while looking down."). Applies at render time, so
 * legacy sessions stored with the old wording display correctly too and
 * the print/PDF layout inherits the same wording.
 */

const VISUAL_LABELS = {
  looking_away: 'looking away from the camera',
  looking_down: 'looking down',
  looking_up: 'looking up',
  poor_posture: 'slouching',
  excessive_head_movement: 'rapid head movement',
  head_movement: 'rapid head movement',
  gesture_flag: 'distracting hand movement',
};

/**
 * Parses "repetition: i am (x2), looking_down" style event lists into
 * { speech: string[], visual: string[] } human-readable fragments.
 */
export function parseCompoundEvents(events) {
  const speech = [];
  const visual = [];
  for (const raw of events) {
    let label = String(raw || '').trim();
    if (!label) continue;

    // Optional trailing count suffix added by the backend dedupe: " (x2)"
    let count = 1;
    const countMatch = label.match(/\s*\(x(\d+)\)$/);
    if (countMatch) {
      count = Number(countMatch[1]) || 1;
      label = label.slice(0, countMatch.index).trim();
    }

    const colon = label.indexOf(':');
    const prefix = colon >= 0 ? label.slice(0, colon).trim() : label;
    const value = colon >= 0 ? label.slice(colon + 1).trim() : '';

    if (prefix === 'filler_word') {
      speech.push(count > 1 ? `used the filler '${value}' ${count} times` : `used the filler '${value}'`);
    } else if (prefix === 'repetition') {
      speech.push(count > 1 ? `repeated '${value}' ×${count}` : `repeated '${value}'`);
    } else if (prefix === 'long_pause') {
      speech.push(count > 1 ? `long pauses (${value})` : `a ${value} pause`);
    } else if (VISUAL_LABELS[prefix]) {
      visual.push(count > 1 ? `${VISUAL_LABELS[prefix]} ×${count}` : VISUAL_LABELS[prefix]);
    } else {
      // Unknown label — show it as-is rather than dropping information.
      visual.push(label.replace(/_/g, ' '));
    }
  }
  return { speech, visual };
}

export function humanizeMistakeDescription(description, events) {
  const raw = String(description || '');
  if (!raw.includes('Compound behavioral cue')) return raw;

  // Prefer structured events when present; otherwise re-parse the raw string.
  let tokens = Array.isArray(events) ? events : [];
  if (!tokens.length) {
    const body = raw.split('correlated')[1] || '';
    tokens = body.split(',');
  }
  const { speech, visual } = parseCompoundEvents(tokens);

  let out;
  if (speech.length) {
    out = speech.join(', ');
    if (visual.length) out += ` while ${visual.join(' and ')}`;
  } else if (visual.length) {
    out = `With ${visual.join(' and ')}`;
  } else {
    return raw;
  }
  return out.charAt(0).toUpperCase() + out.slice(1) + '.';
}
