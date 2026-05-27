## Custom Tool Protocol

Custom tools live under this directory as:

- `custom_tools/<tool_id>/tool.json`

Each manifest should contain:

- `id`
- `description`
- `kind`
- `mode`
- `runner`
- `command_template`
- `input_schema`

Runtime behavior:

- the runtime exposes custom tools in `/tools`
- `POST /tools/<tool_id>/run` passes the request body to the custom tool runner
- each input field is exported as `TOOL_ARG_<field>`
- the full JSON body is exported as `TOOL_INPUT_JSON`

Recommended command template pattern:

```sh
printf 'hello %s\n' "$TOOL_ARG_name"
```
