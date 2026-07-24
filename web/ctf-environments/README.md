# CTF environment boundary

The web game does not host an SSH terminal in the browser. Each computer station
shows players the SSH command for an independently isolated, premade challenge.

Before a real match:

1. Start or reset every challenge container/VM.
2. Restrict its network and filesystem access.
3. Set its SSH command and expected flag in the game-server environment.
4. Confirm SSH works from every player's machine.
5. Start the game server.

Example configuration:

```sh
export CTF_ALPHA_SSH='ssh player@10.0.0.21 -p 2221'
export CTF_BETA_SSH='ssh player@10.0.0.22 -p 2222'
export CTF_GAMMA_SSH='ssh player@10.0.0.23 -p 2223'
export CTF_FLAGS='{"linux-basics":"flag{replace_me}","log-hunt":"flag{replace_me}","permissions":"flag{replace_me}"}'
npm start
```

`CTF_FLAGS` is read only by the server. Never put flags in `client/`, send them
in API responses, or commit production flags.

Automated provisioning/resetting is deliberately left as an infrastructure
adapter because the current repository does not include the premade CTFs or
their runtime details.
