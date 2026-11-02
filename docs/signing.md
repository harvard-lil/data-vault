# Signatures on the gov-data and federal-github bags

Every bag in the Source Cooperative repositories
[harvard-lil/gov-data](https://source.coop/harvard-lil/gov-data) and
[harvard-lil/federal-github](https://source.coop/harvard-lil/federal-github)
was signed by the Library Innovation Lab with the certificate below, then
timestamped by DigiCert, using [bag-nabit](https://github.com/harvard-lil/bag-nabit).
The signature covers the bag's `tagmanifest-sha256.txt`, which holds hashes of
the other manifests and tag files, so it covers every file in the bag.

Each bag's `signatures/` directory contains:

| File | Contents |
|---|---|
| `tagmanifest-sha256.txt.p7s` | Detached CMS signature (PEM), including the signing certificate and its intermediate |
| `tagmanifest-sha256.txt.p7s.tsr` | RFC 3161 timestamp over the `.p7s` file, from DigiCert |
| `tagmanifest-sha256.txt.p7s.tsr.crt` | DigiCert Assured ID Root CA, for checking the timestamp |

## Signing certificate

| | |
|---|---|
| Subject | `CN=lil@law.harvard.edu, emailAddress=lil@law.harvard.edu, O=Library Innovation Lab, organizationIdentifier=NTRUS-166027, L=Cambridge, ST=Massachusetts, C=US` |
| Issuer | `CN=GlobalSign GCC R6 SMIME CA 2023, O=GlobalSign nv-sa, C=BE` |
| Serial | `285C9CFA45F3A9CB88BB6BC8` |
| Valid | 2024-12-05 20:10:46 UTC to 2025-12-06 20:10:46 UTC |
| Extended key usage | E-mail Protection, TLS Web Client Authentication |
| SHA-256 fingerprint | `FB:C8:FF:85:18:A9:C9:A4:CD:74:A2:D9:17:91:5D:1A:8A:45:9D:0F:CE:AF:47:C3:CC:14:F1:EE:F9:61:6E:24` |

The chain is: signing certificate → GlobalSign GCC R6 SMIME CA 2023 → GlobalSign
Root CA - R6.

| Certificate | Serial | Valid to | SHA-256 fingerprint |
|---|---|---|---|
| GlobalSign GCC R6 SMIME CA 2023 | `7E87C3092ED766EF2F21E2A8D0A798F4` | 2029-04-19 | `36:D7:31:48:48:AC:CB:3E:4C:57:92:D1:B0:71:20:B1:03:5B:FB:8B:67:E6:60:09:52:D6:74:5F:5D:6E:22:BD` |
| GlobalSign Root CA - R6 | | 2034-12-10 | `2C:AB:EA:FE:37:D0:6C:A2:2A:BA:73:91:C0:03:3D:25:98:29:52:C4:53:64:73:49:76:3A:3A:B5:AD:6C:CF:69` |

[`lil-signing-cert-2024.pem`](lil-signing-cert-2024.pem) contains the signing
certificate and the intermediate. The root is in common trust stores.

The timestamps were issued by `CN=DigiCert Timestamp 2024`, under DigiCert
Trusted G4 RSA4096 SHA256 TimeStamping CA and DigiCert Trusted Root G4.

## Dates

- gov-data bags were signed between December 2024 and February 2025, and
  federal-github bags in March 2025. That is within the certificate's validity
  period. Each signature's timestamp records when it was made.
- 96 gov-data bags were signed in 2024–2025 but not uploaded until October
  2026. Their signatures and timestamps date from when they were made, not
  from the upload.
- The certificate was obtained to sign these collections and was meant to be
  used only for them. Once signing was done it was left to expire, on
  2025-12-06, and its private key was destroyed. No further bags can be
  signed with it.

## Verifying a bag

Because the certificate has expired, a check made as of the current time fails
with `certificate has expired`. That includes `openssl cms -verify` without
`-attime`, and versions of `nabit validate` that check as of the current time.
Instead, check the signature as of its trusted timestamp. From the root of an
unzipped bag:

```bash
# 1. Check the timestamp, and read the time it attests
openssl ts -verify -data signatures/tagmanifest-sha256.txt.p7s \
  -in signatures/tagmanifest-sha256.txt.p7s.tsr \
  -CAfile signatures/tagmanifest-sha256.txt.p7s.tsr.crt
openssl ts -reply -in signatures/tagmanifest-sha256.txt.p7s.tsr -text | grep 'Time stamp'

# 2. Check the signature as of that time, given in Unix seconds
openssl cms -verify -binary -purpose any -inform PEM \
  -content tagmanifest-sha256.txt \
  -in signatures/tagmanifest-sha256.txt.p7s \
  -attime <unix_time> -out /dev/null

# 3. Check that the files match the manifests, with nabit validate or any BagIt validator
```

Step 2 needs GlobalSign Root CA - R6 in the system trust store, or passed with
`-CAfile`.

These steps were checked on 2026-10-30 with OpenSSL 4.0.3 against three bags:

| Bag | Repository | Signed |
|---|---|---|
| `1935-15-quad-199-aerial-photo-mosaic-index` | gov-data | 2024-12-17 |
| `46403-llnr-984-2-southeast-shumagin-island-186-nm-se-of-shumagin-is-ak4` | gov-data | 2025-02-06 |
| `18F/.github` | federal-github | 2025-03-08 |

All three carry this certificate, and each passed step 2 with `-attime`.
