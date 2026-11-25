# Asks for Jared and Jeanne (LearningProgram)

Pending since 2026-11-24 (wave 2). Kept out of Eric's review waves; the Studio goes ahead with each working answer
until they reply.

Each ask stands alone. The Studio goes ahead with the working answer until they reply.

**1. A program page prints more than one code. Which is the program's identifier?**
- **The example:** WVU's Accountancy page prints "In-Person Major Code: 2166". Other WVU pages print both
  "In-Person Major Code: 5542" and "Online Major Code: 5545" for the same degree.
- **Option 1:** one program, identified by the first code printed.
- **Option 2:** one program per code, one in-person and one online, with the same name and requirements.
- **Option 3:** one program carrying both codes as two identifiers.
- **Working answer:** option 1.

**2. Two programs share one code.**
- **The example:** WVU's Department of English page prints "M.A. Major Code: 1442 … Ph.D. Major Code: 1442".
- **The problem:** if the code is the identifier, the English M.A. and the English Ph.D. become one record.
- **Option 1:** use the code anyway, and let the two merge.
- **Option 2:** when a code is shared, give each program the generated identifier instead, such as
  `program-english-m.a.`.
- **Working answer:** option 2.

**3. The prefix of a generated identifier.**
- **Today:** programs with no printed code get `{type}-{normalized name}` (issue #368). Jared's example was
  `program-anthropology-b.a.`.
- **The question:** should the type be `program` or the CTDL class name, `learningprogram`? Later classes such as
  Credential would follow the same pattern.
- **Working answer:** `program`, as in Jared's example.

**4. A degree page: LearningProgram, Credential, or both?**
- **The example:** WVU's "Accountancy, M.Acc." page describes a program that leads to a degree.
- **xtra-cli today:** it writes such a page as a **Credential** record, not a LearningProgram. The Studio scores
  records by class, so a program labelled here would find no LearningProgram record to match.
- **Working answer:** label it as a LearningProgram now. Label its Credential when that class comes.

**5. An emphasis page that prints only its slice.**
- **The example:** Marshall splits 155 emphases off their degree. The degree page `accountancy-ms/` says "Total Credit
  Hours 30". The emphasis page `…/tax-compliance-planning-emphasis/` says only "Select nine hours from the following
  courses: 9".
- **Agreed already:** each emphasis is its own program.
- **The question:** is its Credit Value the slice it prints (9), or the degree's total (30) from the other page?
- **Working answer:** the degree's total, 30. The emphasis is a whole path through the degree.

**6. Which credit total.**
- **The example:** AVC prints "Anthropology AA-T (Total 24 - 30)", which covers the major's courses. The description
  says "Completion of 60 semester units", which is the whole degree.
- **Option 1:** the whole program's total, 60, even when it is only in prose.
- **Option 2:** the labelled total the page prints, min 24 and max 30.
- **Working answer:** option 1, the whole program. A range goes to Min Value and Max Value. The unit is SemesterHour.

**7. Noncredit hours.**
- **The example:** AVC's noncredit certificates print "Total Hours 180.0", and CCSF's print "Total : 700.0". These are
  clock hours.
- **Option 1:** no Credit Value. Is Non-Credit is true.
- **Option 2:** a Credit Value of 180 in clock hours.
- **Working answer:** option 1.

**8. Properties no page prints.**
- **What we found:** Life Cycle Status and Language never appear on a program page.
- **Language:** only the website's `<html lang="en">` hints at it, and we don't use that, because it is the site's
  language, not the program's.
- **The Extraction Notes:** they suggest defaults, "Active" and English.
- **Option 1:** the golden value is the default.
- **Option 2:** leave them unlabelled until a page states them.
- **Working answer:** option 2, unlabelled.

**9. Required properties.**
- **The sheet:** the Learning Program tab has Phase 1 and Phase 2 columns, but no Required column.
- **The Studio:** it puts Required first.
- **The question:** are a program's required properties the same as Course's, without Coded Notation? That is
  External Identifier, Learning Type, Name, Description, Subject Webpage, Life Cycle Status and Language.
- **Also:** could the sheet get a Required column, so the Studio reads it rather than assuming?
- **Working answer:** the same, and yes to a column.

**10. The same degree on two campuses, with no printed code.**
- **The example:** WVU's "Mechanical Engineering, B.S.M.E." has one page at Morgantown and one at WVU Tech. Neither
  prints a major code.
- **Today:** both get the generated identifier `program-mechanical-engineering-b.s.m.e.`, so they merge into one record
  with two pages. About ten WVU degrees do this. Nursing's printed code 8649 already merges its two campuses the same way.
- **Option 1:** one program with two Available At values, one per campus (today).
- **Option 2:** two programs, each with a campus suffix on its generated identifier, such as
  `program-mechanical-engineering-b.s.m.e.-wvu-tech`.
- **Working answer:** option 1, as today.

---
