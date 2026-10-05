# Public method to REST mapping

| Client method | Mode | Primary fields | Ratio rule |
| --- | --- | --- | --- |
| `text_to_video` | prompt only | `prompt`, `duration`, `resolution`, `aspect_ratio`, `generate_audio` | Caller selects a supported ratio. |
| `image_to_video` | first frame or first/last frame | `start_image`, optional `end_image` | Always sends `aspect_ratio: adaptive`. |
| `reference_to_video` | reference assets | `reference_images`, `reference_videos`, `reference_audios` | Caller selects a supported ratio. |
| `upload_file` | signed media upload | `type`, `content_type`, `size_bytes` | Returns a temporary media URL. |
| `get_result` | asynchronous status | `request_id` | Reads the server status without mutation. |
| `wait_for_completion` | bounded polling | repeated `get_result` | Stops at `done`, `failed`, `expired`, or a local deadline. |
| `download` | completed content | `request_id` | Streams to a `.part` file before rename. |

No method exposes credentials, implementation-specific fields, or a guessed model alias. The canonical model ID is sent on every submit and upload-ticket request.
