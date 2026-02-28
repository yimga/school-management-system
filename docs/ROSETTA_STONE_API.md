# Rosetta Stone API — Frictionless Global Student Mobility

The **Rosetta Stone** API is the official cross-tenant and cross-system grade conversion service for RunMyCampus. It converts grades between scales (e.g. Francophone 16/20 → US GPA 3.2 / B+) using a **normalized 0.0–1.0 anchor**, so that student transcripts remain comparable when moving between schools or education systems.

## Endpoints

- **`GET /api/v1/rosetta/convert`** — Convert a single score between scales.
- **`GET /api/v1/rosetta/scales`** — List supported scale identifiers.

Legacy (still supported): `GET /t/<slug>/api/rosetta/convert/` and `GET /t/<slug>/api/rosetta/scales/`.

## Convert (GET /api/v1/rosetta/convert)

**Query parameters:**

| Parameter   | Required | Description |
|------------|----------|-------------|
| `score`    | Yes      | Raw score (number). |
| `from_scale` | No     | Source scale id. If omitted, uses the current tenant’s grading scale. |
| `to_scale` | No       | Target scale id. Default: `0-20`. |

**Example:**  
`/api/v1/rosetta/convert/?score=16&from_scale=0-20&to_scale=gpa`

**Response:**

```json
{
  "from_scale": "0-20",
  "to_scale": "gpa",
  "raw_score": 16,
  "converted_score": 3.2,
  "normalized_value": 0.8,
  "letter_grade": "B+"
}
```

- **normalized_value**: Score on a 0.0–1.0 scale for cross-tenant reporting and transcript portability.
- **letter_grade**: Present when the target scale supports letter grades.

## Scales (GET /api/v1/rosetta/scales)

Returns the list of scale ids that can be used for `from_scale` and `to_scale` (e.g. `0-20`, `0-100`, `0-10`, `gpa`, `a-f`).

## Stored normalized_value on grades

Evaluation records can store a **normalized_value** (0.0–1.0) for cross-tenant and cross-system use. This is computed and persisted when grades are saved (see `apps/evals/models.py`). The Rosetta Stone service uses the same normalization logic so that:

- Incoming grades from another system can be converted once and stored with `normalized_value`.
- Transcript and “transfer to new school” flows can rely on a single, comparable value across tenants.

Use this API as the single reference for **frictionless global student mobility** when integrating transfers, transcripts, and reporting across different education systems.
