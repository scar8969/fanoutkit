== curl ==
# POST /api/push  -H "X-App-Key: sk_…"  {"channel":"telegram","title":"deploy failed","body":"…"}
# GET  /api/status/12
# POST /api/messages/12/retry
# CLI: pusher push "deploy failed" "…" --app my-app --key sk_… --channel telegram --channel slack

== session plan ==
# Session 1: channels (telegram+webhook vs mock) + templates → tests
# Session 2: retry + dispatch + receipts → status API
# Session 3: all channels + apps CRUD + dashboard → screenshots → README → CI/Docker/Pages → tag
