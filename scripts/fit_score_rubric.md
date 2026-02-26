# Fit score rubric (0–100)

Use this scoring method for every job. **Score = sum of four categories minus penalties** for explicit hard requirements the candidate does not meet. Clamp final score to 0–100.

## Point allocation

- **0–60** — Core stack + day-to-day match: frontend/backend, APIs, DBs, cloud, debugging. Only award points for technologies and responsibilities clearly on the resume.
- **0–20** — Level match: years and seniority vs candidate (~2.5 yrs). Full points only if JD level aligns (e.g. "2+ years", "mid-level"); deduct for "5+", "7+", "senior", "tech lead" when candidate doesn’t match.
- **0–10** — Domain match: product/web vs infra/data/healthcare integration/etc. How well the candidate’s domain experience matches the role’s focus.
- **0–10** — Logistics/constraints: onsite/hybrid/remote, location. No penalty if candidate is fine with it; deduct only for hard mismatches.

## Penalties (subtract from sum)

- **Hard required tech not on resume** (e.g. "C#, .NET Core required", "HL7 required", "ASP.NET/C#/Windows Server"): subtract 25–40 so those roles land in 30–45.
- **Major level mismatch** (e.g. "7+ years", "5+ years Java EE", "tech lead"): subtract 20–35 so those roles land in 25–40.
- **Expertise/nice-to-have gaps** (e.g. "Expertise in GraphQL" when not on resume, "3+ years" when candidate has ~2.5): subtract 5–15 depending on how central it is.

## Calibration examples (candidate ~2.5 yrs, full-stack product)

| Situation | Typical score |
|----------|----------------|
| Strong stack match, minor level gap (e.g. "3+ years") | 78–88 |
| Good stack + level match | 79–86 |
| Partial stack match, hard gap (e.g. required C#/.NET, HL7, or 7+ yrs) | 28–45 |
| Multiple hard gaps (7+ yrs + Java EE + lead; or HL7 + healthcare integration required) | 29–38 |
| Required stack mostly missing (ASP.NET, C#, Windows Server not on resume) | 29–35 |

**Do not cluster scores in the 80s.** Poor-fit roles (required tech or level not on resume) must score in the 20s–40s. Only roles where the candidate clearly meets most requirements should score above 70.

---

*Resume input: the fit score script reads `data/resume.txt` (plain text). Using a resume PDF instead could be added later for parity with tools that score from a PDF.*
