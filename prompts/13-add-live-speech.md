# Prompt 13 · Discuss a recorded decision by voice

~~~text
Read README.md and AGENTS.md. Add a two-way voice conversation about one
selected paper-trading decision. A student should be able to ask what the
agents proposed, hear an answer, and ask a follow-up in the same session.

In Vue, show the selected decision and a Start voice control. On start,
request microphone access and use WebRTC to stream speech in both directions.
Send the browser's connection offer and the selected decision ID to FastAPI.
Have FastAPI read the stored decision, agent findings, and any recorded paper
outcome from SQLite. Give the voice session read-only access to that summary.
Ask it to identify missing evidence when a question goes beyond the record.

For OpenAI GPT-Live, FastAPI exchanges the offer and session configuration
at POST /v1/live/sessions using the backend API key. Vue applies the returned
answer and plays the incoming audio track. Follow the browser connection
sequence in the provider guide. Show when the microphone is active. On End
voice, disconnect, or startup failure, release the microphone and close the
connection. Follow CHECK, TAKE ACTION, and VERIFY for any new dependency.
https://developers.openai.com/api/docs/guides/voice-webrtc?voice-api=live

Verify with a live microphone and speaker on localhost. Ask “What did the
agents decide for this symbol?” Then ask “What happened to the paper account?”
Compare both spoken answers with the selected SQLite record. If no simulated
trade occurred, check that the reply accurately describes the outcome.
End the session and confirm the browser releases the microphone. Also test
denied microphone access or a failed connection. In docs/verification.md,
record what was heard in the live session and label any mocked checks.
~~~
