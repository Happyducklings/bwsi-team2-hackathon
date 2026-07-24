// Educational station content for the web intro layer. Everything here is
// public — there are no flags or secrets in the web game. The real CTF
// challenges live only in the downloadable terminal game.
//
// Each topic maps to one computer station on the map (terminalId). Reaching a
// station lets a player read the topic and press "Mark reviewed"; studying
// enough topics unlocks the extraction gate.

export const TOPICS = Object.freeze([
  {
    id: "crypto-stego",
    terminalId: "terminal-alpha",
    category: "CRYPTO & STEGO",
    title: "Cryptography & Steganography",
    summary: "Scramble a message so only the right people can read it — or hide that a message exists at all.",
    body: [
      "Cryptography protects information by transforming it so that only someone with the right key can recover the original. Classic ciphers are simple letter math you can often break by hand — a Caesar shift or ROT13 rotates the alphabet, and XOR combines each byte with a repeating key. Modern schemes like AES and RSA are far stronger, but the same ideas show up: encoding (Base64, hex) reshapes data without protecting it, while encryption actually locks it.",
      "Steganography is different: instead of scrambling a message, it hides the fact that a message is there at all — tucking secret text inside the least-significant bits of an image, the metadata of a file, or the noise of an audio clip. In a CTF you might spot a Base64 blob, recognize a ROT or XOR pattern, or pull a hidden payload out of a picture with a tool like OpenStego.",
    ],
    reading: [
      { label: "picoCTF Primer — Cryptography", url: "https://primer.picoctf.org/#_cryptography" },
      { label: "GeeksforGeeks — Cryptography and its types", url: "https://www.geeksforgeeks.org/cryptography-and-its-types/" },
      { label: "OpenStego (steganography tool)", url: "https://www.openstego.com/" },
    ],
  },
  {
    id: "re-binexp",
    terminalId: "terminal-beta",
    category: "RE & PWN",
    title: "Reverse Engineering & Binary Exploitation",
    summary: "Read a program you don't have the source for — then abuse its bugs to take control.",
    body: [
      "Reverse engineering is figuring out how a compiled program works without its source code. Disassemblers and decompilers like Ghidra, IDA, or objdump turn raw machine code back into readable assembly (and sometimes C-like pseudocode) so you can trace the logic, find hidden checks, or recover a password comparison.",
      "Binary exploitation takes it further: it abuses memory-safety bugs to make a program do something it was never meant to. A classic example is a buffer overflow — a function like gets() reads input with no bounds check, so writing past the end of a buffer can overwrite the saved return address. A 'ret2win' challenge exploits exactly this, redirecting execution to a hidden win() function that prints the flag.",
    ],
    reading: [
      { label: "picoCTF Primer — Reverse Engineering", url: "https://primer.picoctf.org/#_reverse_engineering" },
      { label: "picoCTF Primer — Binary Exploitation", url: "https://primer.picoctf.org/#_binary_exploitation" },
      { label: "GeeksforGeeks — Buffer overflow attack", url: "https://www.geeksforgeeks.org/buffer-overflow-attack-with-example/" },
    ],
  },
  {
    id: "network-analysis",
    terminalId: "terminal-gamma",
    category: "NETWORK",
    title: "Network Analysis",
    summary: "Reconstruct what machines said to each other by reading captured traffic.",
    body: [
      "Network analysis means inspecting captured traffic to understand what devices on a network sent to one another. A packet capture (a .pcap file) records real conversations — web requests, DNS lookups, file transfers — that you can replay and pick apart after the fact.",
      "Wireshark and tcpdump let you filter by protocol (HTTP, DNS, TCP), follow a single stream from start to finish, and even reassemble transferred files. In a CTF, the flag is often sitting in a packet payload, an HTTP request, or a file that was sent across the wire — so the skill is knowing how to filter down to the one conversation that matters.",
    ],
    reading: [
      { label: "picoCTF Primer — Forensics", url: "https://primer.picoctf.org/#_forensics" },
      { label: "Wireshark User Guide", url: "https://www.wireshark.org/docs/wsug_html_chunked/" },
      { label: "GeeksforGeeks — Introduction to Wireshark", url: "https://www.geeksforgeeks.org/introduction-to-wireshark/" },
    ],
  },
  {
    id: "osint",
    terminalId: "terminal-delta",
    category: "OSINT",
    title: "Open-Source Intelligence (OSINT)",
    summary: "Answer questions using only information that's already public.",
    body: [
      "OSINT — open-source intelligence — is gathering information from sources anyone can access: photos, file metadata, maps, public records, and social media. No hacking required; the skill is knowing where to look and how to connect the breadcrumbs.",
      "A photo alone can reveal a lot. EXIF metadata may include the exact GPS coordinates and timestamp a picture was taken. A reverse image search can identify a landmark, and from there public records tell you when a building was constructed. OSINT challenges reward patience and curiosity: start from one clue and pull the thread until the public web hands you the answer.",
    ],
    reading: [
      { label: "OSINT Framework (tool directory)", url: "https://osintframework.com/" },
      { label: "GeeksforGeeks — What is OSINT?", url: "https://www.geeksforgeeks.org/what-is-open-source-intelligence-osint/" },
      { label: "picoCTF Primer — General Skills", url: "https://primer.picoctf.org/#_general_skills" },
    ],
  },
  {
    id: "cyber-careers",
    terminalId: "terminal-epsilon",
    category: "CAREERS",
    title: "Careers in Cybersecurity",
    summary: "The skills in this game map to real, in-demand jobs.",
    body: [
      "Cybersecurity is a wide field, and the puzzles in this game each point toward a real role. Red teamers and penetration testers break into systems to find weaknesses before attackers do. Blue teamers and SOC analysts monitor, detect, and respond to threats. Digital forensics and incident responders investigate what happened after a breach, malware analysts reverse-engineer malicious code, and cryptographers design the math that keeps data safe.",
      "You don't need a special degree to start. Most people break in through hands-on practice: playing CTFs, building a home lab, earning entry certifications like CompTIA Security+, and working up to advanced ones like the OSCP. The curiosity you're using right now — decoding, investigating, connecting clues — is exactly the mindset these careers are built on.",
    ],
    reading: [
      { label: "CyberSeek — Cybersecurity Career Pathway", url: "https://www.cyberseek.org/pathway.html" },
      { label: "SANS — Cybersecurity Careers", url: "https://www.sans.org/cybersecurity-careers/" },
      { label: "NICE Cybersecurity Workforce Framework", url: "https://niccs.cisa.gov/workforce-development/nice-framework" },
    ],
  },
]);

export function publicTopic(topic) {
  return {
    id: topic.id,
    category: topic.category,
    title: topic.title,
    summary: topic.summary,
    body: topic.body,
    reading: topic.reading,
  };
}
