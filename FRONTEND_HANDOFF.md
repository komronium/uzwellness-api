# Frontend Handoff: Image Uploads

This file contains only the latest frontend-facing backend change.

## Uploaded Images Are Stored As WebP

Frontend can still upload JPEG, PNG, or WebP files with multipart form data.
Backend now normalizes supported image uploads to a single `.webp` file before
saving.

Affected endpoints:

```http
POST /api/sanatoriums/{sanatorium_id}/images
POST /api/rooms/{room_id}/images
POST /api/destinations/{destination_id}/hero-image
POST /api/packages/{package_id}/hero-image
POST /api/treatment-focuses/{focus_id}/image
```

Rules:

- Request format stays the same: `file: string($binary)`.
- Accepted input formats stay the same: JPEG, PNG, WebP.
- Response URLs now end with `.webp` regardless of uploaded image extension.
- Visa/passport/document uploads are not changed.
- Frontend should not infer output format from the selected local file name.
