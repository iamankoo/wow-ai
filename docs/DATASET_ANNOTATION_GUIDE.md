# WOW Dataset Annotation Guide

This guide is for humans annotating the WOW 33K dataset
(`training/datasets/v3_raw/wow_33k_relevant.jsonl`) using
`python -m training.pipeline.annotation.cli annotate`. It defines every
label in the current taxonomy and gives Hindi (Devanagari), Hinglish, and
English examples for each, with special attention to the label pairs
annotators most often confuse.

**The taxonomy below is closed for this annotation round.** Do not invent
new intent/context/action values. If you find an example that genuinely
does not fit anything here, label it `GENERAL_CONVERSATION` (or `UNKNOWN`
if the text itself is too broken/ambiguous to classify at all) and leave a
note - do not force a bad fit into a plausible-looking category, and do not
add a new category. `CALLBACK_REQUEST` and `REDIAL`-style requests
("call me back later", "call again") were evaluated during the taxonomy
analysis phase and are represented by `SCHEDULE_REQUEST` unless a future
phase changes that decision.

## How to read an example

Every queued example shows:
- The **primary candidate** (best guess from rule-based matching or the v1
  model) - this is a suggestion to speed you up, never a fact. It has
  already been wrong on the majority of examples where the two candidate
  sources disagree.
- Rule-based and v1 candidates shown separately when both exist, so you can
  see when they disagree - disagreement is itself a signal to look closer.

Your job: read the text, decide the correct intent/context/action from the
lists below, and Approve / Correct / Reject / Skip.

---

## Intents

| Intent | Definition | Example (English) | Example (Hindi) | Example (Hinglish) | Do NOT use for |
|---|---|---|---|---|---|
| `SET_CONTEXT` | User is telling WOW to switch into a mode (sleeping, busy, meeting, etc). | "Set me to busy for the next hour." | "मुझे अगले एक घंटे के लिए व्यस्त कर दो।" | "Mujhe ek ghante ke liye busy set kar do." | A question about someone else's status (that's `GET_CONTEXT` or `GENERAL_CONVERSATION`) |
| `CLEAR_CONTEXT` | User is telling WOW to leave the current context and return to normal. | "I'm free now, clear my status." | "अब मैं फ्री हूँ, मेरा स्टेटस हटा दो।" | "Ab main free hoon, status clear kar do." | Ending a call (`END_CALL`) or conversation (`END_CONVERSATION`) |
| `GET_CONTEXT` | User is asking WOW what context is currently active. | "What's my current status?" | "मेरा अभी क्या स्टेटस है?" | "Mera abhi kya status hai?" | Asking about a third person's status/mood in casual talk - see confusing pairs below |
| `CALL_PERSON` | User wants WOW to call/connect them to someone. | "Call Rahul for me." | "राहुल को कॉल करो।" | "Rahul ko call karo." | A caller asking to schedule a future call (`SCHEDULE_REQUEST`) |
| `HANDLE_CALLS` | User is authorizing WOW to answer/handle incoming calls. | "Handle my calls while I'm out." | "जब मैं बाहर हूँ तो मेरी कॉल्स संभालो।" | "Jab main bahar hoon tab meri calls handle karo." | Turning the assistant on/off as a system toggle (`ENABLE_CALL_ASSISTANT` action, not an intent by itself) |
| `UNKNOWN_CALLER` | The caller is not a recognized contact. | "I don't know this number." | "मैं इस नंबर को नहीं जानता।" | "Mujhe ye number pehchan nahi." | Caller explicitly says who they are - that makes them `KNOWN_CALLER` |
| `KNOWN_CALLER` | The caller is a recognized contact. | "This is Priya, Aniket's colleague." | "मैं प्रिया हूँ, अनिकेत की सहकर्मी।" | "Main Priya hoon, Aniket ki colleague." | Caller is unnamed/unclear |
| `URGENT_CALL` | The call/message is flagged as needing elevated attention. | "This is an emergency, please call me back now." | "यह एक इमरजेंसी है, कृपया अभी कॉल करें।" | "Ye emergency hai, please abhi call karo." | Text contains an urgency word but is explicitly negated ("not urgent") - see confusing pairs |
| `NON_URGENT_CALL` | The call/message is not time-sensitive. | "No rush, whenever you're free." | "कोई जल्दी नहीं है, जब फ्री हो तब बात करना।" | "Koi jaldi nahi hai, jab free ho tab baat karna." | - |
| `MESSAGE_FOR_USER` | The caller wants to leave a message. | "Please tell him I called." | "उससे कह देना कि मैंने कॉल किया था।" | "Usse keh dena ki maine call kiya tha." | This is the caller's *intent*; `COLLECT_MESSAGE` is WOW's resulting *action* - see confusing pairs |
| `SCHEDULE_REQUEST` | Requesting to schedule something (a call, meeting, callback). | "Can we schedule a call for tomorrow?" | "क्या हम कल के लिए कॉल शेड्यूल कर सकते हैं?" | "Kya hum kal ke liye call schedule kar sakte hain?" | Asking WOW to call someone *right now* (`CALL_PERSON`) |
| `CANCEL_REQUEST` | Requesting to cancel something previously scheduled. | "Cancel tomorrow's call please." | "कल की कॉल कैंसिल कर दो।" | "Kal ki call cancel kar do please." | - |
| `SUMMARIZE_CONVERSATION` | Requesting a summary of the current/past conversation. | "Can you summarize what we discussed?" | "क्या आप बता सकते हैं हमने क्या बात की?" | "Humne kya discuss kiya, summary de sakte ho?" | - |
| `END_CONVERSATION` | The conversation is being wrapped up. | "Okay, thanks, bye." | "ठीक है, धन्यवाद, अलविदा।" | "Theek hai, thanks, bye." | An explicit instruction to hang up (`END_CALL`) - see confusing pairs |
| `TRANSFER_TO_USER` | The call should be handed to the real user directly. | "Can I speak to Aniket directly?" | "क्या मैं सीधे अनिकेत से बात कर सकता हूँ?" | "Kya main directly Aniket se baat kar sakta hoon?" | - |
| `GENERAL_CONVERSATION` | Ordinary conversational content with no specific actionable intent above. | "How are you doing?" | "आप कैसे हैं?" | "Aap kaise ho?" | Small talk that turns out to actually contain a real request - read the whole sentence |
| `UNKNOWN` | Text is too broken/ambiguous/off-topic to confidently classify. | (garbled or unrelated text) | (garbled or unrelated text) | (garbled or unrelated text) | Use sparingly - only when you genuinely cannot decide, not as a default when unsure between two real options (pick the more likely one and lower your confidence rating instead) |

## Context modes

`SLEEPING`, `BUSY`, `MEETING`, `TRAVELLING`, `UNAVAILABLE`, `CUSTOM`,
`NORMAL`. Context is only set when the example is an actual `SET_CONTEXT`
(or `GET_CONTEXT` response) - most examples (e.g. `CALL_PERSON`,
`END_CONVERSATION`) legitimately have no context and should be left blank
(`None`), not forced into `NORMAL`. `CUSTOM` is for a user-defined mode that
doesn't fit the other six (e.g. "set me to do-not-disturb for gaming") -
don't reach for `CUSTOM` just because you're unsure; prefer the closest
real mode if one clearly fits.

## Actions

| Action | When it applies |
|---|---|
| `ENABLE_CALL_ASSISTANT` | User turns WOW's call handling on. |
| `DISABLE_CALL_ASSISTANT` | User turns WOW's call handling off. |
| `SET_CONTEXT` | Persisting a new context mode - pairs with intent `SET_CONTEXT`. |
| `CLEAR_CONTEXT` | Resetting context to normal - pairs with intent `CLEAR_CONTEXT`. |
| `ANSWER_CALL` | WOW answers an incoming call on the user's behalf. |
| `ASK_CALLER_REASON` | WOW asks the caller why they're calling. |
| `COLLECT_MESSAGE` | WOW takes a message from the caller - the *action* side of `MESSAGE_FOR_USER`. |
| `MARK_URGENT` | Flagging the call/message urgent - pairs with intent `URGENT_CALL`. |
| `TRANSFER_CALL` | Handing the call to the user - pairs with intent `TRANSFER_TO_USER`. |
| `END_CALL` | Ending the current call - the literal hang-up action, distinct from `END_CONVERSATION` the intent. |
| `SAVE_MEMORY` | Persisting a fact from this interaction. |
| `CREATE_SUMMARY` | Generating a summary record - pairs with `SUMMARIZE_CONVERSATION`. |
| `NO_ACTION` | Nothing needs to happen in response (most `GENERAL_CONVERSATION`/`UNKNOWN` examples land here). |

Most examples have exactly one natural action. If you genuinely can't tell
which action follows from the text, it's fine to pick `NO_ACTION` and lower
your confidence rating rather than guessing.

---

## Confusing pairs - read this before annotating

These eight pairs account for most of the disagreement between the
rule-based and v1 candidates in the taxonomy analysis. When a queued
example's tier is `ambiguous`, it is very likely one of these.

### 1. `URGENT_CALL` vs `NON_URGENT_CALL`
Look for a negation or de-escalation word attached to the urgency word in
the *same clause* - "not urgent", "nahi urgent", "koi jaldi nahi". A
sentence that merely *asks whether* something is urgent (real example from
the data: "अभी {} उपलब्ध नहीं हैं ... क्या यह एक जरूरी जानकारी के बारे में
है?" - "is this about something urgent?") is not itself declaring urgency -
read whether the speaker is stating urgency or asking about it.

### 2. `SET_CONTEXT` vs `GENERAL_CONVERSATION`
A context word alone isn't enough. "Set me to busy" is `SET_CONTEXT`,
self-declared. "Is he busy right now?" (real example: "Kya Aniket aapko
meeting ke baare mein baad mein call kare?") is a question *about* someone
else's status or a caller's small talk - that's `GENERAL_CONVERSATION`
(or `GET_CONTEXT` if it's genuinely asking WOW for the current status).

### 3. `MESSAGE_FOR_USER` (intent) vs `COLLECT_MESSAGE` (action)
These are not competing labels - they usually co-occur. `MESSAGE_FOR_USER`
describes *why the caller is talking* (they want to leave a message);
`COLLECT_MESSAGE` describes *what WOW should do about it*. Most
message-leaving examples should carry both.

### 4. `END_CALL` (action) vs `END_CONVERSATION` (intent)
A farewell ("bye", "thanks, that's all") is `END_CONVERSATION` - the talk
is wrapping up naturally. An explicit instruction to disconnect ("hang up
now", "call kaat do", "end this call immediately") is the `END_CALL`
action. A polite goodbye does not imply the caller wants the *call itself*
force-ended - most `END_CONVERSATION` examples still pair with `NO_ACTION`
or a natural close, not `END_CALL`.

### 5. `KNOWN_CALLER` vs `UNKNOWN_CALLER`
Only label `KNOWN_CALLER` when the text gives a concrete identity cue (a
name, a stated relationship - "this is Priya", "मैं राहुल का दोस्त हूँ").
A caller merely being polite or familiar-sounding in tone is not enough
evidence on its own.

### 6. `HANDLE_CALLS` (intent) vs `ENABLE_CALL_ASSISTANT` (action)
`HANDLE_CALLS` is the user's request ("handle my calls today"); it usually
*results in* the `ENABLE_CALL_ASSISTANT` action. If the text is explicitly
about turning the assistant/automation on or off as a toggle ("turn on the
call assistant"), the intent can arguably still be `HANDLE_CALLS` with that
action - don't invent a separate intent for the toggle phrasing.

### 7. `GET_CONTEXT` vs `GENERAL_CONVERSATION`
"Kaisa hai?" / "kaise ho?" on its own is small talk (`GENERAL_CONVERSATION`).
It only becomes `GET_CONTEXT` when it's clearly asking about WOW's tracked
status/mode/availability, not a person's general wellbeing.

### 8. `SCHEDULE_REQUEST` vs `CALL_PERSON`
"Call Rahul" (now, direct) is `CALL_PERSON`. "Can we schedule a call with
Rahul for tomorrow" (a future, planned call) is `SCHEDULE_REQUEST`. The
tell is immediacy: *right now* vs *at a later, specified or unspecified
time*.

---

## Hindi / Hinglish / English labeling notes

- **Never reclassify Hinglish as English based on Roman script alone.**
  `"Aniket abhi busy hai, baad mein call karna."` is Hinglish even though
  it's written in Roman characters - the grammar and vocabulary are Hindi.
  The `language` field on each record was assigned from its source file and
  is preserved as-is; you are not asked to re-judge it, only to label
  intent/context/action correctly for the text as given.
- **Never translate or rewrite the text.** If a sentence is ambiguous
  because of how it's phrased, that ambiguity is real signal - reflect it
  in a lower confidence rating and a note, don't "fix" the sentence.
- Devanagari text may contain unfilled template placeholders (literal `{}`)
  from the source data - label the surrounding sentence normally and leave
  a note if the placeholder makes the intent genuinely unclear.

---

## Annotation actions

- **Approve** - the shown candidate is correct as-is. Rate your confidence
  1-5.
- **Correct** - pick the right intent/context/action yourself. If your
  correction changes the intent from what the candidate predicted, it is
  automatically captured as a hard negative for future training.
- **Reject** - the example is unusable (garbled text, not really WOW-domain,
  duplicate of something already seen with a different obvious label). Give
  a one-line reason.
- **Skip** - come back to it later. No label is written.
