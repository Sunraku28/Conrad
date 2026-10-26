.PHONY: build run test

build:
	go build -o conrad .

run:
	go run .

test:
	go test ./...
