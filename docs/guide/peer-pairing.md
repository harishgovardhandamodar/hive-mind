---
description: Share hives between HiveMind instances over the internet
icon: globe
---

# Peer-to-Peer Hive Sharing

HiveMind supports sharing hives between instances over the internet through a **peer-to-peer pairing** system. Instances can discover each other, establish secure pairing, and synchronize hives.

## Overview

Each HiveMind instance has a persistent identity (`instance_id` and `instance_secret` stored in `data/peers.json`). Peers are other HiveMind instances you've connected to. Once paired, you can pull hives from a peer and they can pull from you.

```
┌─────────────────┐          ┌─────────────────┐
│  HiveMind A     │          │  HiveMind B     │
│  instance_id: a │◄────────►│  instance_id: b │
│  hives: gnns    │  pair    │  hives: llms    │
│  peers: [b]     │  sync    │  peers: [a]     │
└─────────────────┘          └─────────────────┘
```

## Instance Identity

Every HiveMind instance automatically generates a unique identity on first launch:

```bash
python -m hivemind peers info
```

Output:
```
HiveMind Instance Info
  Instance ID: a1b2c3d4-e5f6-...
  Name:        my-server
  URL:         http://192.168.1.100:9090
  Hives:       3
  Peers:       0
```

The identity is stored in `data/peers.json` and persists across restarts.

### Public URL

For a peer to reach your instance, your **public URL** must be set. By default it's derived from the host and port. Override it with the `HIVEMIND_PUBLIC_URL` environment variable:

```bash
HIVEMIND_PUBLIC_URL=https://my-hivemind.example.com python -m hivemind serve
```

## Pairing Instances

### 1. Secure Pairing (Recommended)

Use a **one-time pairing token** signed with HMAC-SHA256 by the remote instance's secret. This works even over plain HTTP without TLS.

**On the remote instance** (the one you want to connect TO), generate an invite:

```bash
python -m hivemind peers invite
```

Output:
```
HiveMind Pairing Invite
  Token:       550e8400-e29b-...:1700000000:a1b2c3d4e5f6
  Expires at:  2025-11-15T12:00:00Z
  URL:         http://192.168.1.100:9090
```

Share the token string with the party that wants to pair. The token expires after 600 seconds by default (use `--ttl` to change).

**On the local instance**, pair using the token:

```bash
python -m hivemind peers pair http://192.168.1.100:9090 --token "550e8400-e29b-...:1700000000:a1b2c3d4e5f6"
```

The pairing is **bidirectional** — both instances register each other as peers.

### 2. TLS Pairing

When both instances use HTTPS, no token is needed — TLS provides transport security. Enable TLS with `--cert` and `--key`:

```bash
python -m hivemind serve --cert /path/to/cert.pem --key /path/to/key.pem
```

Then pair directly:

```bash
python -m hivemind peers pair https://my-hivemind.example.com
```

The pairing flow automatically detects TLS and skips the token requirement.

### 3. Insecure Pairing (Not Recommended)

Pairing over plain HTTP without a token is **rejected** by default with an error message instructing you to use a token.

## Syncing Hives

Once paired, you can pull all hives from a peer:

```bash
python -m hivemind peers sync <peer-id>
```

Or pull a specific hive:

```bash
python -m hivemind peers pull <peer-id> <hive-id>
```

### Similarity-Based Merging

When pulling hives, concepts are **merged by similarity** (Jaccard coefficient ≥ 0.5 on word sets). Matching concepts get cross-graph edges rather than duplicates, preserving the identity of each hive while building links between them.

## Managing Peers

```bash
# List known peers
python -m hivemind peers list

# Add a peer manually (one-directional, no handshake)
python -m hivemind peers add http://192.168.1.101:9090 --name "Server B"

# Remove a peer
python -m hivemind peers remove <peer-id>
```

## Dashboard

The web dashboard has a **Peers** tab in the sidebar where you can:

- View instance info (ID, fingerprint, URL, hive/peer counts)
- Generate an invite token with one click
- Add, pair, and remove peers
- Sync hives from individual peers
- See peer status and fingerprint at a glance

## Security Model

| Concern | Mechanism |
|---|---|
| Identity spoofing | HMAC-SHA256 token signed with per-instance secret |
| Token reuse | One-time tokens tracked in memory after use |
| Token expiry | Configurable TTL (default 600s) |
| Transport security | Optional TLS (HTTPS) |
| Self-pairing | Rejected by `instance_id` comparison |
| Duplicate detection | `find_peer_by_url()` prevents re-registration |

The `instance_secret` is a random 256-bit value generated once and stored in `data/peers.json`. Never share it — share only one-time invite tokens derived from it.

## API Reference

### Peer Management (client-side)

| Method | Path | Description |
|---|---|---|
| GET | `/api/peers` | List known peers |
| POST | `/api/peers` | Add a peer manually |
| POST | `/api/peers/pair` | Bidirectional pairing |
| DELETE | `/api/peers/<id>` | Remove a peer |
| POST | `/api/peers/<id>/sync` | Pull all hives from peer |
| POST | `/api/peers/<id>/pull/<hive_id>` | Pull specific hive |

### Peering Endpoints (server-side, called by peers)

| Method | Path | Description |
|---|---|---|
| GET | `/api/peering/info` | Return instance identity and fingerprint |
| GET | `/api/peering/hives` | List this instance's hives |
| GET | `/api/peering/hive/<id>` | Export a hive (returns node-link JSON) |
| POST | `/api/peering/invite` | Generate a one-time pairing token |
| POST | `/api/peering/pair` | Accept a pairing request from a peer |

### Pair Request Body

POST `/api/peers/pair`:
```json
{
  "url": "http://192.168.1.100:9090",
  "token": "optional-invite-token"
}
```

POST `/api/peering/pair` (called by the remote):
```json
{
  "peer_url": "http://192.168.1.101:9090",
  "peer_name": "my-instance",
  "instance_id": "...",
  "fingerprint": "abcd:1234:...",
  "token": "optional-invite-token"
}
```

### Invite Response

POST `/api/peering/invite` returns:
```json
{
  "token": "uuid:timestamp:hmac_sig",
  "expires_at": "2025-11-15T12:00:00Z",
  "url": "http://192.168.1.100:9090"
}
```
