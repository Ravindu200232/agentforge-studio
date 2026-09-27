# Revise the approval plan

## The plan as it stands

{{plan}}

## The interview, for context only

{{transcript}}

## What they asked you to change

{{revision}}

## Answers they gave to your open questions

{{answers}}

## Your turn

Do exactly what they asked for, and nothing else. A revision is not a re-plan: do
not rewrite wording you were not asked about, do not drop screens, records,
workflows or features that are already in the plan above, and do not re-derive
the plan from the answers — those are context for understanding the request, not
the plan.

Return the complete revised plan. Any section you leave out of your JSON is kept
exactly as it stands above, so it is safe to return only the sections you
actually changed — but a section you DO return replaces that section outright, so
return it in full, including the items you are keeping.

`open_questions` is the exception you must always return. Drop every question
their message answers — an answer that picks one of the options you offered
settles that question completely — and keep the ones it does not touch. Return
`[]` when nothing is left to ask; an empty list is a valid and expected answer,
and it is what lets them approve the plan. Do NOT raise new questions on a
revision: they came here to settle the plan, and a round that answers two
questions and asks two more never ends.

Answer in {{language}}. Return only the JSON object.
