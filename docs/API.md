# MooveSaathi API Documentation

Base URL: /api/v1

## Authentication
- POST /auth/register, /auth/login, /auth/refresh, /auth/logout
- POST /auth/forgot-password, /auth/reset-password, /auth/verify-email
- GET /auth/sessions and /auth/security; session revocation routes

## Users
- GET /users/me; PATCH /users/me and driver profile routes

## Rides and dispatch
- /rides: publish, search, view, update, cancel, complete, and track rides
- /dispatch: passenger requests, driver presence, nearby matching, and dispatch WebSocket

## Bookings and payments
- /bookings: create, list, update status, boarding OTP, trip sharing
- /payments: create, confirm, reconcile, list, and provider webhooks

## Realtime and notifications
- /chat: booking messages, seen state, and WS /chat/ws/{booking_id}?token=<access-jwt>
- /notifications: list, unread count, and mark read

## Other API groups
- /reviews, /incidents, /ai, /audit
- /support: requires x-support-token when support API is enabled
- /deployment and /jobs: require the same support token
- /health, /health/live, /health/ready, /metrics

See /api/v1/openapi.json for request and response schemas.
