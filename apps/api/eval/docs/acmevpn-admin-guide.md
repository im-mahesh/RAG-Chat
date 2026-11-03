# AcmeVPN Administrator Guide

AcmeVPN is the company's remote-access service. This guide covers deployment and day-to-day administration of the AcmeVPN gateway and its desktop clients.

## Installation

The AcmeVPN client is distributed as a signed installer for Windows, macOS and Linux. Administrators should deploy it through the device management console rather than asking employees to download it. After installation the client registers with the nearest gateway and shows a green shield icon in the system tray. The first connection requires the user to sign in with their single sign-on account.

## Network ports

The gateway listens on UDP port 51820 for the primary WireGuard-based tunnel. If UDP is blocked by a hotel or airport network, the client falls back to TCP port 443 and wraps the tunnel in TLS. Administrators must allow outbound traffic on both ports from the corporate firewall to the gateway address range. Port 8443 is reserved for the admin console and must never be exposed to the internet.

## Error codes

E4012 means the client certificate has expired; reissue it from the admin console and push the new profile to the device. E5003 means the gateway rejected the handshake because the device clock is more than five minutes out of sync. E2201 means the user's account has been suspended by the identity provider. For any other code, collect the client log bundle before opening a ticket with the networking team.

## Split tunneling

By default all traffic goes through the tunnel. Split tunneling lets administrators send only traffic for internal subnets through AcmeVPN while streaming and general web browsing use the local connection. Enable it per group under Policies, then list the internal CIDR ranges. Split tunneling is disabled for the finance group because of audit requirements.

## Multi-factor authentication

Every AcmeVPN sign-in requires a second factor. Users can approve a push notification in the authenticator app or enter a six-digit code. Hardware security keys are required for administrators. If a user loses their second factor, the helpdesk can issue a one-time bypass code that expires after 15 minutes.

## Log files

Client logs are stored in the user's application data folder under acmevpn/logs and rotate daily, keeping seven days. Gateway logs are shipped to the central logging platform. To collect a support bundle, right-click the tray icon and choose Export diagnostics; the bundle contains the connection log but never the user's traffic.

## Upgrading clients

New client versions are released on the first Tuesday of every month. The console can stage a rollout to ten percent of devices first, then widen it after 48 hours without new error reports. Clients older than two major versions are blocked from connecting and show a prompt to update.
