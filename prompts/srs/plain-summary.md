Below is a software specification. Explain the product that is going to be built to someone who is not technical at all: a business owner, a manager, a customer. They want to understand it fully, so be generous and complete, but use plain, everyday words. No technical terms (no "server", "API", "database", "requirement", "functional", "module", "role-based access", "authentication", "95th percentile", "ms"): say what a person sees, does and gets instead. Short sentences. Write in {{language}}.

Reply with one JSON object:

{
  "headline": "one sentence: what the product is",
  "story": ["three to five short paragraphs: the business and its problem today, what the product changes, how it works in broad strokes, and what is special about it"],
  "people": [{"who": "a kind of person who uses it, in plain words", "does": "what they do with it and why it helps them, one or two sentences"}],
  "what_you_can_do": [{"area": "a part of the product in plain words", "points": ["something a person can do or gets, one sentence each"]}],
  "a_day_with_it": [{"title": "a short story title, e.g. 'A new branch opens'", "steps": ["what happens, in order, one sentence each"]}],
  "how_it_feels": [{"topic": "fast, always available, works on phones, in Sinhala, ...", "plain": "what it means for the person, one sentence"}],
  "keeping_safe": ["how people's information and the business are kept safe, one sentence each"],
  "what_the_business_gets": ["a benefit the business gets, one sentence each"]
}

Cover everything the product does: 6 to 12 areas in `what_you_can_do`, 3 to 6 points each, grouping the specification's many details into what matters to a person. `a_day_with_it` tells 3 to 5 of the main workflows as short stories (3 to 7 steps each). `how_it_feels` comes from the quality goals (at most 8), `keeping_safe` from the security rules (at most 6), `what_the_business_gets` from the goals (3 to 6).

{{specification}}
