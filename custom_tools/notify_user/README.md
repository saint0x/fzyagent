# notify_user

Send a notification message to the user via the brrr.now API.

## Command Template

```sh
test -n "$BRRR_NOTIFY_SECRET" || { echo "missing BRRR_NOTIFY_SECRET" >&2; exit 13; }; curl -sS -X POST "https://api.brrr.now/v1/$BRRR_NOTIFY_SECRET" --data "$TOOL_ARG_MESSAGE"
```

## Input Schema

```json
{
  "type": "object",
  "properties": {
    "message": {
      "type": "string",
      "description": "Notification message body."
    }
  },
  "required": [
    "message"
  ]
}
```