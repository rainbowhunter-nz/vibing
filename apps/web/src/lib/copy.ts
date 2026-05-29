// Error copy guidance:
//  - title:  name what failed in plain words — no jargon, no blame, no codes.
//  - helper: one actionable next step.
//  - tone:   calm, factual, sentence case, no exclamation marks.
//  - empty ≠ error: empty = "nothing here yet" + how to populate;
//                   error = "something went wrong" + how to recover.
export function loadError(subject: string) {
  return {
    title: `Couldn't load ${subject}`,
    helper: 'Check that the backend is running, then reload the page.',
  }
}
