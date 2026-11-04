# Original prompt

Given on 2026-11-04, in one conversation. Reproduced verbatim.

---

**1.** Some fixes. INvestigate why these are necessary and propose a spec/plan to fix them (emphasis on visuals, not text)

1. When jared tried to annotate the correct answer for ceterms:entryCondition -> ceterms:description, it didn't create one of the green annotation segments when he highlighted the correct part of the page

2. implement deep URLs so when a sample is highlighted, a link to that sample and comment can be shared

3. https://golden-rules-studio.mlops-club.org/#/c/ccsf/rules/course-page for this one, in the "one course per page" locator rule.

4. Jared clicked the "improve these 5 rules" button and I don't see any output from claude. Health check please look and investigate what's wrong there

5. default the sample to autostratify

6. default the filter to "Anyone"

do the Q in qrspi here.

**2.** consider another point. Point 8: for the one course per page rule, well some pages have multiple courses. When you show the preview in the sidebar, it looks like you're finding all the courses and separating them into indiviidual blocks, but only one has a transparent blue background, the others have no highlight. What does this mean? The reality is that there will sometimes be multiple courses per page. The UI and the rule should more intuitively account for that.

**3.** *(with a screenshot of Jared's notes: "We're gonna need to be able to add multiple Duration Profiles. How should we do that? Need to figure out how to handle an array of objects. Example: https://avc.elumenapp.com/catalog/2026-27/course/acct199 — ceterms:estimatedDuration → ceterms:DurationProfile {ceterms:description: Total Course In-Class (Contact) Hours, ceterms:timeRequired: 54.0 - 432.0}, ceterms:DurationProfile {ceterms:description: Total Course Out-of-Class Hours, ceterms:timeRequired: 0.0 - 0.0}")*
okay, this thing probably needs a new rule type. Instead of grabbing all this stuff as a value, we want it to be more structured, it'll be one of these ceterms: sets of DurationProfiles. The way to annotate this would be more structured than just highlighting a bunch of blocks of text. Technically the correct answer to this is an array of objects with ceterms description and value. We'll need to think of how scoring would work for such a complex value type. Also, list other ceterms properties that we have rules to extract that may also have more complex value types. Add this to the list of points that we discussed earlier. Begin any of the research that doesn't require my input. And surface the questions that do.
