# GodsHand-Conrad

GodsHand-Conrad provides the terminal launcher and local LLM sandbox agent.

## Run

Build the `conrad` launcher, then start it from the repository root:

```bash
go mod tidy
make build
./conrad
```

Select **Conrad** in the TUI to start `GodsHand.src.conrad`. Set
`GODSHAND_CONRAD_PYTHON` to choose a Python interpreter, or
`GODSHAND_CONRAD_ROOT` when launching the binary from outside this repository.
