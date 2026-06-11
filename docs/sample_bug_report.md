# Sample Bug Report

## Summary

Verification requests return `504 Downstream provider timeout` when incident mode is set to `timeout`.

## Environment

- Service: API Support Lab
- Endpoint: `POST /verifications`
- Incident mode: `timeout`

## Steps to Reproduce

1. Start the API locally.
2. Run `POST /admin/incident-mode/timeout`.
3. Submit a verification request with header `x-api-key: demo-key`.
4. Review the API response and `/admin/logs` output.

## Expected Result

The API should return a controlled timeout response and log a structured `verification_error` event.

## Actual Result

The API returns `504 Downstream provider timeout` and logs the request ID with error type `timeout`.

## Support Impact

Customers may experience delayed or failed identity verification while the downstream provider is unavailable.
