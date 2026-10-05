# Troubleshooting

## HTTP 401 or 403

Check that `ARGOLINK_API_KEY` is set in the same process that runs the client. Do not paste the key into a command line that will be saved in shell history. A valid key does not bypass model availability or account permissions.

## HTTP 400 validation errors

Keep the returned JSON body. The most common causes are:

- missing or empty `prompt`;
- a prompt over 20,000 characters;
- duration outside 2–30 seconds;
- an unsupported resolution or ratio;
- a non-HTTPS asset URL;
- more than 10 images, 5 videos, 5 audio tracks, or 20 total assets;
- mixing frame fields with reference lists;
- sending a fixed ratio with a frame workflow instead of `adaptive`;
- adding an unsupported option such as `seed` or `watermark`.

The Python client catches these cases before submission where they are deterministic. Server validation remains authoritative.

## Upload failures

Use the exact `Content-Type` used to create the ticket, and send the original bytes to the signed `upload_url`. A signed URL is temporary; request a new ticket after it expires. Do not add the API bearer token to the signed PUT unless the response explicitly requires it.

## Polling timeouts

A local polling deadline means the client stopped waiting; it does not mean the job failed. Save `request_id` and poll again later. Avoid automatically submitting a duplicate job after a timeout.

Terminal statuses are:

- `done`: safe to download;
- `failed`: inspect the returned `error` object and fix the input or retry intentionally;
- `expired`: the job is no longer available and must be submitted again if appropriate.

## Download errors

Only call the content endpoint after a `done` response. The client writes to a `.part` file and renames it after the stream completes, so an interrupted transfer does not look like a finished video. Remove stale `.part` files during cleanup.

## Pricing and refunds

Do not copy a price into automation from an old README. Read the live model page for current customer tiers. Billing is based on completed output seconds plus reference-video seconds; the model page explains the treatment of failed and rejected jobs.
