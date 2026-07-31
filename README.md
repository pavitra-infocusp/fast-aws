# fast-aws

A fast TUI browser for AWS resources, built with [Textual](https://textual.textualize.io) and `boto3`, using your local `~/.aws` profiles and SSO — no web console needed.

## Install & run

```bash
uv sync
uv run fast-aws --profile my-sso-profile --region us-east-1
```

Launch without `--profile` to pick one from a menu.

## Development / hot reload

Run the app through Textual's dev runner (live CSS reload + devtools console):

```bash
uv sync                       # installs dev deps incl. textual-dev
uv run textual run --dev -c "fast-aws --profile my-sso-profile"
```

Edit `src/fast_aws/ui/app.tcss` while it runs and the change applies live.
Run `uv run textual console` in a second terminal to see `print()`/`log()`
output and Textual events.


## Features

- Browse S3, Lambda, DynamoDB, API Gateway, Cognito (user + identity pools),
  Secrets Manager, SSM Parameter Store, IAM, and CloudWatch Logs
- Jump between connected resources: Lambda → log group, API Gateway → Lambda,
  Cognito triggers → Lambda, role → policies, and back
- Readonly by default; opt into Edit mode with `Ctrl+E` (or `--edit`)
- SSO login handled interactively inside the TUI
- Filter lists with `/`, refresh with `r`, command palette with `Ctrl+P`
- Secrets/parameters are masked; reveal requires an explicit action

## Keybindings

| Key       | Action                                  |
| --------- | --------------------------------------- |
| `Enter`   | Open / drill down                        |
| `Esc`     | Back / close                            |
| `/` `f`   | Filter current list                     |
| `l`       | Linked resources (jump)                 |
| `a`       | Actions for selection                   |
| `i`       | Show / hide inspector panel             |
| `r`       | Refresh (clears cache)                  |
| `Ctrl+P`  | Command palette                         |
| `Ctrl+E`  | Toggle Readonly ↔ Edit                  |
| `Ctrl+A`  | Switch profile                          |
| `g` / `G` | Top / bottom of list                    |
| `q`       | Quit (in dialogs)                       |

## Permissions

Readonly mode never issues mutating calls; the executor layer enforces it.
Run with `--edit` or toggle `Ctrl+E` to enable invoke / mutating actions.
