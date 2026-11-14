# Security Policy

This policy says how to report a security flaw in Keel, which releases receive a fix, and what happens after a report.

Keel is proprietary. Permission to copy or modify it comes from the copyright holder, as [LICENSE](LICENSE) says.

## Supported versions

Security fixes land on `main` and ship in the next release published from that branch. Older tags may not be maintained. The version number comes from git tags. See [package version](docs/version.md).

## Reporting a vulnerability

Do not open a public GitHub issue, pull request, or discussion for a suspected security flaw. A public thread shows everyone how to exploit it before a fix exists.

Report it in private, in one of these ways:

- [GitHub private vulnerability reporting](https://github.com/Mathotics/Keel/security/advisories/new)
- A message to the copyright holder

Include:

- What the flaw is, and what you expect an attacker could do with it
- The steps to reproduce it, or a proof of concept if you have one
- Whether it is in the Python server, the browser pages, or the Android app
- The version or commit, if you know it
- How to reach you for a follow-up

## What happens next

The copyright holder reads the report and replies once he has confirmed whether it is a flaw in Keel. When it is, he fixes it on `main` and publishes that fix in a release before any public write-up of the details.

Do not publish the flaw, a proof of concept, or the report until that release is out. He will tell you when you can.

A report made to punish someone, or a report the reporter knows is false, is handled under the [Code of Conduct](CODE_OF_CONDUCT.md).

## In scope

- A flaw in the shipping Python server, browser scripts, or Android app that lets someone bypass sign-in, exceed their role, read or change another person's data, or run code they should not
- A known vulnerability in a library the running application installs

## Out of scope

- Leaving the first-run `keel` / `keel` password in place, exposing the server on a public address without a firewall, or any other choice an operator makes on their own host
- Development tools that are not installed with the application
- Testing a Keel server you do not have permission to test
- Volume attacks against a host you do not operate
