# DocVal — 5-minute architecture walkthrough (video script)

*Companion to the eval case study. Target: confident, technical, zero fluff.
Record screen + voice; face-cam optional. Rough beats with timestamps.*

## 0:00–0:30 — Cold open on the live demo

*Screen: https://docval-yy4s.onrender.com, drag in a scanned statement.*

> "This is DocVal — it takes a bank statement, native PDF or scan, extracts
> every transaction, and then does something most extraction demos skip: it
> proves the extraction is arithmetically consistent. Opening balance plus
> every transaction has to equal the closing balance, row by row. Let me show
> you how it works and — more importantly — how I measure whether it's right."

## 0:30–1:30 — Architecture in one diagram

*Screen: architecture sketch (triage → native / vision → shared schema →
validation → report).*

> "One pipeline, two paths. A triage step checks whether the PDF has a usable
> text layer. If yes — deterministic parsing, no model at all, zero cost. If
> it's a scan, pages render to images and go to a vision model through
> OpenRouter with a strict JSON schema. Both paths land in the same Pydantic
> model, so everything downstream — validation, evals, the demo — doesn't
> care where the data came from."

> "The model returns strings exactly as printed — '₹1,54,432.10', dates in
> whatever format the bank liked. Normalization is deterministic code. Models
> copy what they see no matter what the prompt says, so I stopped asking."

## 1:30–2:30 — The validation layer

*Screen: validation report on a demo doc, green checks; then a failing doc.*

> "Every document gets validated: balance continuity, running-balance chain,
> dates inside the statement period, debit/credit consistency. These are pure
> functions — no LLM judging LLM output. When the balance chain breaks, I
> know the extraction is wrong without ever seeing ground truth. That's the
> difference between a demo and a system you can put in an ops workflow."

## 2:30–4:00 — The eval harness (the actual point)

*Screen: eval/run_eval.py output, then the README results table.*

> "Accuracy numbers: transaction-level precision, recall, F1 — matched on
> exact date and exact signed amount, because in finance a fuzzy amount match
> is just a wrong number with good vibes. Header field accuracy. Validation
> pass rate. Cost per document."

> "Held-out F1 is 0.51 — and I publish the split: 0.92 on synthetic
> statements, 0.12 on real dense scans. [TODO: update after quality round.]
> That 0.12 is the honest number. It told me exactly where the work is: the
> model blows through its output budget on 6-page, 160-transaction documents.
> The fix is structural — page-by-page extraction, merged, with the balance
> validator checking the merge."

> "And the regression gate runs in CI on every push — an offline subset
> compared against a committed baseline. If someone's refactor drops F1 by
> more than a point, the build goes red. Nobody remembers to run evals;
> pipelines remember for you."

## 4:00–4:40 — War story

*Screen: the Bankstatemently issue page.*

> "One more thing measurement bought me: I submitted to a third-party
> benchmark and every document bounced. Turned out *their* ground truth was
> broken server-side — provable because their own example submission failed
> the same way. If you can't verify a benchmark with a control payload, you
> don't have a benchmark — you have a rumor."

## 4:40–5:00 — Close

*Screen: GitHub repo README with metrics table.*

> "Everything's open: the pipeline, the eval harness, the numbers — including
> the bad one, because the worst honest number is the roadmap. Links below.
> I build document-extraction and reconciliation systems for financial
> operations — if that's your problem space, let's talk."

---

**Recording checklist**
- [ ] Warm up the Render demo first (free tier sleeps; first load ~1 min)
- [ ] Have one native + one scanned sample PDF on the desktop
- [ ] Pre-open: demo tab, GitHub README, issue #1, terminal with eval output
- [ ] Update the two [TODO] numbers before recording
