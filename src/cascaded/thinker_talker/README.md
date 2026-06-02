# Thinker/Talker Cascaded Example

Independent cascaded voice example for the Thinker/Talker flight-booking design.

The Talker is the only user-facing LLM and only exposes `call_thinker`.
The Thinker is session-local and owns flight search, selected-flight booking,
PNR status, lifecycle markers, and abort state. In the running pipeline it
talks to the shared booking-server sidecar over HTTP as its backend database;
unit tests use a deterministic in-memory backend.

Booking is intentionally gated: the user must search flights first and select
one returned flight before the Thinker can continue booking.
