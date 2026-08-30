# Interview data policy

`mock-interview-dataset.json` is synthetic demo data (`dataset_status: synthetic_mock`).
It is safe for development and does not represent real interview frequency, survey
results, or employer questions. The active imported dataset is
`approved-dataset.json` (`dataset_status: approved_public_transformed`).

`approved-dataset.json` currently contains 31 records from the MIT-licensed
Tech Interview Handbook. Behavioral questions retain their public source wording;
algorithm and system-design records are clearly marked as Chinese transformed
prompts. They must not be presented as official company questions or frequency
statistics. LeetCode question text and answers are deliberately not copied.

To import public data, create a separate JSON file with an `items` array. Every
`online`/`official` item must include a source URL, license, access timestamp,
`pii_redacted: true`, and a stable `content_hash`. Validate before importing:

```powershell
python backend/scripts/manage_knowledge.py validate --file data/approved-dataset.json
python backend/scripts/manage_knowledge.py import --file data/approved-dataset.json
```

Do not commit scraped page text unless redistribution is explicitly permitted by
the source license. Store a citation and a short, transformed question instead.
