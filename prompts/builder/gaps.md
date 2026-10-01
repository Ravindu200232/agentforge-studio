## Go through the recorded gaps with the customer

The application is built and its checks have run. `.agentforge/build/report.json` still records these
gaps — things the build did not do or did not prove — and the customer has not been asked about them:

{{gaps}}

What the customer already answered in this project (apply these; never ask them again):

{{answers}}

A gap is not settled by writing it down. Go through every gap above, in order, and settle each one with the
customer:

1. **Find out what would close it.** Reopen the code, the report and the runner output it is about. Either it
   needs more work from you — a check that was not written, a path no test exercises, a test that can run on
   this computer — or it needs something only the customer has or decides: a credential or a provider
   account, a choice of provider or service, a sign-in account's details, a tool or service this computer
   lacks, a business rule, or whether the limitation is acceptable.
2. **Ask the customer**, the way the build asks: write `.agentforge/build/question.json` and end your reply
   with the blocked marker. One question at a time, written yourself about this product in plain words — what
   does not work yet or was not proven, and what each option does — with two to four options, your
   recommendation first, and an `assumption` saying what you will do if they leave it to you.
   - Gaps that only need more work from you go in **one** question together: name each in plain words, with
     the options "Close them now — add and run the checks" (recommended) and "Leave them recorded".
   - A gap that needs something from the customer gets its own question, offering the real ways to close it
     and also leaving it as it is. A password, key, token, secret or connection string is asked for with
     `"variable": "NAME"` and `"secret": true`, one value per question, so it is typed into the private box.
   - Never ask for anything Supabase: this project's Supabase is connected and its values are in the
     environment.
3. **Act on the answer.** Do what it allows — read the credential from the environment and wire it in, add
   the provider, write and run the missing checks — and rerun only the checks the change touches. Then update
   `.agentforge/build/report.json`: a gap that is closed leaves `gaps`, and its evidence goes into `commands`,
   `routes`, `requirements` or `verified`; a gap the customer chose to keep stays, with `"asked"` set to the
   question exactly as you asked it and `"answer"` to what they answered.

Never write that the customer was asked unless they were asked in this project. When every gap above is
settled, reopen `{{report_template}}`, bring both report files back to its shape and finish.
