# AcmeSync Desktop Client Guide

AcmeSync keeps a local folder in step with the company file store. This guide is for administrators who deploy and support the AcmeSync desktop client.

## Installation

The AcmeSync client is distributed as a signed installer for Windows and macOS. Administrators should deploy it through the device management console. After installation the client asks the user to sign in with single sign-on and then to choose the folder that will be synchronised. A blue cloud icon in the menu bar shows that sync is running.

## Network ports

AcmeSync communicates over TCP port 443 only, so it works on almost every network. Large uploads use parallel connections to the same port. Administrators who inspect TLS traffic must exempt the sync endpoint, because the client pins the server certificate and will refuse to connect through an inspecting proxy.

## Error codes

E4012 means the sync token has expired; the user must sign in again from the menu bar. E5003 means the file server is temporarily overloaded and the client will retry with increasing delays. E3100 means the file is locked by another process, usually an editor that still has it open. Quit the other program and the sync will resume on its own.

## Selective sync

Users with limited disk space can choose which folders are kept on the device. Folders that are not selected appear as placeholders and are downloaded on demand when opened. Administrators can set a default selection per group, but users may change it unless the policy is locked.

## Conflict resolution

When the same file is edited on two devices before either change is uploaded, AcmeSync keeps both versions. The newer edit keeps the original file name and the other copy is renamed with the device name and a timestamp. Nothing is overwritten silently and users can compare the copies side by side.

## Log files

Client logs are written to the sync folder's hidden .acmesync directory and rotate daily, keeping fourteen days. Use the Help menu to export a diagnostic bundle for support. The bundle lists file names and error codes but never file contents.

## Upgrading clients

New AcmeSync versions are released on the first Wednesday of each month. Updates download in the background and are applied the next time the client is restarted. Administrators can defer updates for up to two weeks from the device management console.
