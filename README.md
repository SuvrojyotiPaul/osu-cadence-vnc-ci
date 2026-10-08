# OSU Cadence VNC: cross-platform compatibility checks

This repository checks **free client-side tools** for launching a remote Linux desktop from Windows, macOS, and Linux. It runs local, disposable VNC and SSH services on each GitHub-hosted operating system. **It does not contact Oregon State University or run Cadence Virtuoso.**

## Run

Open [Actions](https://github.com/SuvrojyotiPaul/osu-cadence-vnc-ci/actions) and select **VNC + SSH cross-platform checks** → **Run workflow**. The workflow also runs when files are pushed to main.

After completion, open the run and download each **vnc-report-...** artifact. Check `summary.md` and `results.json` for pass/fail details. A green CI job demonstrates installer/CLI and localhost forwarding behavior, **not** successful OSU/Duo/Cadence access.

## Platforms

| GitHub runner | Viewer |
| --- | --- |
| Windows Server 2025 | TurboVNC (free) |
| macOS 26 (Apple Silicon) | TurboVNC (free) |
| macOS 15 Intel | TurboVNC (free) |
| Ubuntu 24.04 | TigerVNC (free) |

## Test design

1. Download/install viewer (record log).
2. Confirm executable exists and collect CLI/version information.
3. Start an ephemeral local VNC/RFB 3.8 server and SSH server, both bound to `127.0.0.1` only.
4. Establish `ssh -N -L` using the OS-native OpenSSH client, then receive a framebuffer over the forwarded connection.
5. Capture JSON, Markdown and debug logs as artifacts, even if a step fails.

No ONID password, Duo, SSH private key, or university login should ever be added as a GitHub secret. A final acceptance test still requires a real student machine connecting to OSU under the course instructions.

## Student-side manual tunnel to test separately

Using the workstation and VNC display from Lab 0.1, a tunnel patterned on your classmate's working example is:

```bash
ssh -o ExitOnForwardFailure=yes -N -L 127.0.0.1:47890:COURSE_WORKSTATION:5903 ONID@flip.engr.oregonstate.edu
```

Keep that terminal open. In TigerVNC or TurboVNC Viewer use `127.0.0.1::47890`. The `5903` example is for VNC display `:3`, not a universal course value. OSU access still must be verified separately.
