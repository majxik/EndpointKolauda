# Optional cross-platform task shortcuts (requires `just`)

set shell := ["powershell.exe", "-NoProfile", "-Command"]

default:
    just --list

setup:
    .\scripts\tasks.ps1 setup

test:
    .\scripts\tasks.ps1 test

audit-example:
    .\scripts\tasks.ps1 audit-example

lint:
    .\scripts\tasks.ps1 lint

