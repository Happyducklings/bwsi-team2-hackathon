const configuredFlags = (() => {
  try {
    return JSON.parse(process.env.CTF_FLAGS || "{}");
  } catch {
    throw new Error("CTF_FLAGS must be a JSON object keyed by challenge ID");
  }
})();

export const CHALLENGES = Object.freeze([
  {
    id: "linux-basics",
    terminalId: "terminal-alpha",
    title: "Linux Basics",
    ssh: process.env.CTF_ALPHA_SSH || "ssh player@ctf-alpha.example",
    flag: configuredFlags["linux-basics"] || "flag{demo_linux_basics}",
  },
  {
    id: "log-hunt",
    terminalId: "terminal-beta",
    title: "Log Hunt",
    ssh: process.env.CTF_BETA_SSH || "ssh player@ctf-beta.example",
    flag: configuredFlags["log-hunt"] || "flag{demo_log_hunt}",
  },
  {
    id: "permissions",
    terminalId: "terminal-gamma",
    title: "Broken Permissions",
    ssh: process.env.CTF_GAMMA_SSH || "ssh player@ctf-gamma.example",
    flag: configuredFlags.permissions || "flag{demo_permissions}",
  },
]);

export function publicChallenge(challenge) {
  const { flag: _flag, ...safe } = challenge;
  return safe;
}
