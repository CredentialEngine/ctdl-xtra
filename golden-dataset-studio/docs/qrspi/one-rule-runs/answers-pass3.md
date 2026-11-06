# Answers, pass 3 (Eric, 2026-11-05 15:32 MST): which rules a run may change

## Decisions
- **The rules you pick are the goal, not a fence.** Picking two property rules means "improve these two". To do that,
  Claude may make **surgical edits to any other rule** (an upstream page rule or locator, a sibling) to the extent
  they're needed. No rule is off limits.
- **Every check runs the whole golden suite**: every rule in the catalog against all its golden values, so a
  surgical edit upstream can't quietly break a sibling downstream rule.
- Edits should be as focused and surgical as possible.
- Eric first considered an indented tree picker that auto-checks upstream/downstream rules, then set it aside: since
  nothing is off limits, the picker only says what to improve.
- This answers "a downstream rule you didn't pick" (P1): Claude may change it, and the whole-suite check covers it.

## Verbatim (dictated)

> You know, your design is making me realize that, and I think you've been trying to tell me this the whole time, and I just haven't understood. Uh we know that there's a dependency relationship between rules. Like there's at least one dependency relationship. Like if you change an upstream rule, there's a possible blast radius for all the downstream rules. And if you want to change a downstream rule and improve it, you may need to change the upstream rule in order to do that. So I think that the UI here with the selector should be like a tab indented tree view that with the checkboxes that automatically checks upstream rules when you check a downstream rule. And if you check an upstream rule, automatically check the downstream rules. Uh well, actually that is complicated, isn't it? Cause if we're trying to do like the leaf nodes, maybe we don't care about the upstream rule. We don't care about it until we do I guess this goes back to I guess when you're editing a rule, none of the other rules should be off limits. I think that's the key. None of the other rules should be off limits when you're editing a rule. And when you are checking your edits, you need to check against the whole golden suite to make sure you didn't regress on any of them. By making the so yeah, it should be search okay, here we go. If I select two property rules, then Claude should be allowed to make edits to the two property rules. But they should also be able to make surgical edits to any of the other rules to the extent that they're relevant to the property rules. So there's always the possibility that fixing one rule could result in changes to many rules. Because if I am if I'm trying to fix a property rule, but do that I have to fix the upstream rule, then I have to make sure I don't ruin the downstream the other downstream rules that are siblings to the property rule. And so the best test, of course, is making sure that you want we want edits to be as focused and surgical as possible. And of course we want to rerun when Claude is testing the rule changes, Claude should really just test all the rules to make sure that none of the rules have regressed because of the surgical edits.
