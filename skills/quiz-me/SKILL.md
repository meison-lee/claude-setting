---
name: quiz-me
description: Use when the author is about to open or update an MR (including through /mr, in any repo), or wants to check they can explain a feature to a reviewer — for the current branch or a merged ticket.
---

# Quiz me

Three questions that check the author can explain the feature **the way a reviewer would ask**: what it
does, why it was designed that way, what breaks. It is not a test of whether they read the code.
Questions come from the spec; the diff only confirms the spec was implemented.

## Inputs

- Ticket key from the branch name (`GAMAPASS-\d+`), or the one the user names.
- Spec: the newest `docs/superpowers/specs/*.md` whose name or title carries that key or topic. No spec →
  say so in one line and build the questions from the MR commits (`git log origin/main..HEAD`) instead.
- Diff: `git diff origin/main..HEAD --stat` (or the range the user gives) — used only to check that each
  question's answer still holds in the code. A diff that contradicts the spec is itself question material.

## The quiz

Exactly three questions, one per row, in this order:

| # | 類型 | It asks | Answer lives in |
|---|---|---|---|
| 1 | 行為 | In situation X, what does the system do? | spec 行為／資料模型段落 |
| 2 | 決策 | Why A and not B? | spec 已確認的決策／被否決方案 |
| 3 | 失敗 | What happens when Y goes wrong, and who is affected? | spec 風險／切換語意／上線順序 |

A question is **one sentence that names a situation**, and the things it names are what a reviewer
sees in the spec or MR: an RPC, a table or column, a toggle, a client type, an environment.

- 行為 example: 「後台把一家服務商切成 V2 之後，這個 MR 合併的當下，它收到的通知會有什麼變化？」
- Not a question: 「`recordPPIDAPIChange` 比對的舊值從哪裡來？」 — a function name tests reading, not understanding.

Present it with this shape, then **stop and wait for the answers**. Nothing else happens until the user
replies — no diff reading, no lint, no push.

```
開 MR 前先考三題。憑記憶用自己的話答；答不出來寫「不知道」。

1. 行為：<question>
2. 決策：<question>
3. 失敗：<question>
```

If the user asks for the answers before attempting, give the **spec section heading** for each question,
not the answer; they answer after reading it.

## Grading

One line per question: 答對／部分／答錯, then the spec section (heading) that holds the answer and at most
two sentences of what it says. Then one verdict line:

- all three 答對／部分 → 「可以開 MR」and continue.
- any 答錯 or 不知道 → 「先讀 <spec 段落> 再答第 N 題」, re-ask only that question, then continue.

The questions, answers and grades stay in this conversation. They are not written into the MR
description, Jira, commit messages, or memory, and the MR Summary is not reshaped around weak answers.

## Common mistakes

| Mistake | Fix |
|---|---|
| 8 questions, or a 加分題 | Three. Pick the one situation per type a reviewer is most likely to raise. |
| A question with sub-cases (V1→V2、V2→V1、沒帶欄位…) | One situation per question; the other cases are what grading can mention. |
| Go identifiers, proto wrapper types, file or migration names in a question | Name the situation instead (the toggle, the RPC, the environment). |
| Generating questions from the diff | Generate from the spec; the diff only confirms the answer still holds. |
| Writing the weak spots into the MR Summary | The quiz is private to the author. |
