"""Every regex, keyword list, and threshold discovery uses.

Discovery is deterministic: no model decides what a page is. When a page is
labelled wrong, the fix is a rule in this file and a fixture next to the
others that proves it. Nothing else in the discovery code carries a literal
pattern or a cut-off, so tuning is one file to read and one file to review.

Four entities are recognised, and they are the four `lib/mapping.py` can
write CTDL for:

    Course               ceterms:Course          one course, or a page of them
    LearningOpportunity  ceterms:LearningProgram instruction with no award named
    Credential           ceterms:Credential      the degree, certificate, or
                                                 certification a page grants
    Competency           ceasn:Competency        a learning outcome list

Credential and LearningOpportunity are exclusive on purpose. A college
program page almost always names the award it leads to, and the award is
the thing that gets published, so a page that names one is a Credential
page and a program page that names none is a LearningOpportunity. Course is
decided before either, because a credential page prints the courses it
requires and that list is not a page of course descriptions.

Both are read from the page's own content, never from its furniture. Every
page of a catalog carries a menu called "Degrees & Certificates" and a
sidebar linking "Degree Requirements", so the menus, sidebars and footers
are dropped before any program or award rule looks at the text. What is
left has to show two things: that the page prints a program's requirements,
and where it names the award, which is in one of five places a catalog
puts it (the page's name, the badge beside the name, a section heading, a
"Degrees Conferred" line, or the first paragraph).

Every pattern below carries a comment saying what it matches and, where the
obvious pattern was wrong, what it refuses to match and which page taught
us that. The regexes read normalized visible text, so they have to survive
a normalizer that glues a label to its value ("Lab Hours3") and catalogs
that print non-breaking spaces inside course codes.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

# --- thresholds -------------------------------------------------------------

# A label printed on nearly every page is the site's furniture, not a field.
CHROME_SHARE = 0.90
# Within one page type, a label or marker this uncommon is worth looking at.
RARE_LABEL_SHARE = 0.05
RARE_MARKER_SHARE = 0.20
# A pattern covering this little of its page type is a special case.
RARE_PATTERN_SHARE = 0.05

EMPTY_PAGE_CHARS = 500
# How far a credits value may sit from the course code it belongs to.
COURSE_BLOCK_WINDOW = 400
# "Near the top" for deciding the page is about one course, and the same
# window for deciding the page names the award it is about. Both questions
# are about the heading area, not the body.
COURSE_CODE_HEAD_CHARS = 300
MAX_FIELD_LABEL_CHARS = 40
MARKER_EVIDENCE_CHARS = 80
PATTERN_ID_LENGTH = 8
MIN_OUTCOME_ITEMS = 2
# How many distinct course codes make a page under a /courses/ path a run
# of course descriptions. Two codes are a course and its prerequisite.
# The same count makes a requirements heading a program's own list.
MIN_COURSE_LIST_CODES = 3

# The heading area of a page's content: the short lines before its first
# paragraph, which is where a catalog prints the badge naming a program's
# award ("Associate in Science") beside the program's name.
HEAD_MAX_LINES = 8
HEAD_LINE_CHARS = 80
# Longer than this is a sentence, not a heading or a label.
SECTION_HEADING_CHARS = 120
SHORT_LINE_CHARS = 60
# How much of the first paragraph may name the program's award, and how
# far past the page's own name, when the paragraph opens with it.
INTRO_CHARS = 600
INTRO_NAME_REACH_CHARS = 60
# How far past "Degrees Conferred:" the awards it confers may be printed.
DECLARATION_REACH_LINES = 3
DECLARATION_REACH_CHARS = 200
# A plan of study with no total and no requirements heading: term headings
# ("First Year", "Fall Semester") over a list of courses.
MIN_TERM_HEADINGS = 2
MIN_PLAN_CODES = 6

DEFAULT_SAMPLE_SIZE = 30
DEFAULT_SAMPLE_LABEL = "Course"

# --- labels -----------------------------------------------------------------

LABEL_COURSE = "Course"
LABEL_LEARNING_OPPORTUNITY = "LearningOpportunity"
LABEL_CREDENTIAL = "Credential"
LABEL_COMPETENCY = "Competency"
PAGE_TYPE_MULTIPLE = "Multiple"
PAGE_TYPE_UNKNOWN = "Unknown"

# --- course codes ------------------------------------------------------------

# The subject prefix: two to six capitals. Five was too few and dropped
# every Pitt page, where the subject is spelled out (AFRCNA 1415).
_CODE_SUBJECT = r"[A-Z]{2,6}"

# What sits between the subject and the number. A plain space or hyphen is
# the common case; Acalog and CourseLeaf print a non-breaking space or a
# non-breaking hyphen, and the normalizer keeps them, so ALAN 0100 has
# to read as one code instead of as a bare number.
_CODE_SEPARATOR = r"[  ‑–-]?"

# The number, in the three shapes catalogs print:
#   ENGL 101, AFRCNA 1415, CIS114DE - three or four digits
#   ACCT A101                       - a letter, then two digits
#   ACTG 1A, ACTG 1BH               - one or two digits, then a letter
# The third shape has to end in a letter. Without that, "GOAL 1", "SLO 3",
# "OSHA 10" and "LEVEL 1" all read as course codes, and a page of learning
# outcomes counted six courses.
_CODE_NUMBER = (
    r"(?:[A-Z]?\d{3,4}[A-Z]{0,2}|[A-Z]\d{2}[A-Z]{0,2}|\d{1,2}[A-Z]{1,2})"
)

# The fourth shape, kept apart because it needs a longer subject: five
# digits, which is how a CourseLeaf graduate catalog numbers its courses
# (ASTR 50303, ISYS 50103). Without it, 104 of the 303 course listings at
# the University of Arkansas held no course code at all, so none of them
# could be a Course page, and COURSE_TITLE_RE below already read five
# digits and so disagreed with this rule about the same line.
#
# Three letters at least, and never a ZIP+4, because two capitals and five
# digits is the last line of every address a catalog prints
# ("Fayetteville, AR 72701").
_CODE_SUBJECT_LONG = r"[A-Z]{3,6}"
_CODE_NUMBER_LONG = r"\d{5}[A-Z]{0,2}(?!-\d{4}\b)"

COURSE_CODE_RE = re.compile(
    rf"\b(?:{_CODE_SUBJECT_LONG}{_CODE_SEPARATOR}{_CODE_NUMBER_LONG}"
    rf"|{_CODE_SUBJECT}{_CODE_SEPARATOR}{_CODE_NUMBER})\b"
)

# Every separator the code regex accepts, so ACCT 130, ACCT-130,
# ACCT 130 and ACCT130 collapse to one key.
_CODE_SPACING_RE = re.compile(r"[\s ‑–-]+")

# --- credits -----------------------------------------------------------------

# The noun itself. The leading boundary matters: without it "accredited"
# reads as a credit value and every page looks like it prints credits. "cr"
# needs the lookahead for the same reason one letter down: it is the start
# of "crop", "crew" and "criminal", so "3 crop sciences" read as a value.
_CREDIT_NOUN = r"(?:credits?|units?|hours?|hrs?|cr(?![A-Za-z]))\.?"

# Words a catalog prints between the noun and the number. Coursedog writes
# "Credit Hours Min: 3" and Acalog writes "Credit Hour(s): 3"; with the noun
# alone both read as no value at all, which left four Ivy Tech course pages
# with zero course blocks and no Course label. Two are enough for every form
# seen, and more would let a match run on into the next sentence.
_CREDIT_QUALIFIER = (
    r"(?:\s*(?:\(s\)|hours?|hrs?|units?|credits?|semester|quarter|contact|"
    r"clock|lecture|lab|min|max|minimum|maximum|required|earned|awarded|"
    r"low|high)\.?)"
)

# No word boundary after the qualifier, on purpose: the normalizer the
# extractors share glues a term to its value, so a definition list reads as
# "Credits3".
_CREDIT_WORDS = rf"\b(?:{_CREDIT_NOUN}{_CREDIT_QUALIFIER}{{0,2}})"

# Words between the number and the noun, for the other print order:
# "1 Course Unit" at Penn, "3 semester hours", "4 quarter units".
_CREDIT_PREFIX = (
    r"(?:(?:semester|quarter|course|contact|clock|lecture|lab|credit)\s+){0,2}"
)

_NUMBER = r"\d+(?:\.\d+)?"
# "3", "3.0", "1-3" and "1 to 3" are all one printed value.
_RANGE = rf"{_NUMBER}(?:\s*(?:-|to)\s*{_NUMBER})?"

# A credits value in either print order: value then noun, or noun then value
# with an optional colon, equals, or dash between them.
CREDIT_VALUE_RE = re.compile(
    rf"(?:{_RANGE}\s*{_CREDIT_PREFIX}{_CREDIT_WORDS}"
    rf"|{_CREDIT_WORDS}\s*[:=-]?\s*{_RANGE})",
    re.IGNORECASE,
)

# 3-2-4 or 3/2/4 printed next to a course: lecture, lab, credit. Two digits
# each at most, so a catalog year (2026-2027) is not three hour counts.
LECTURE_LAB_CREDIT_RE = re.compile(
    r"\b\d{1,2}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{1,2}\b"
)

# Contact-hour labels, printed beside credits and easily read as credits.
# No boundary after "hours" for the glued-value reason above, so a
# definition list reads as "Lab Hours3". The optional "/ word" covers the
# Clean Catalog spelling "Lab/Clinical/Field Study Hours".
LAB_CLINICAL_HOURS_RE = re.compile(
    r"\b(?:lab(?:oratory)?|clinical|field\s+study|practicum|externship|studio)"
    r"\s*(?:/\s*\w+\s*)?hours?",
    re.IGNORECASE,
)

# A printed zero, in both print orders. It is a real value, and a different
# thing from a value the page never printed.
PRINTED_ZERO_HOURS_RE = re.compile(
    rf"(?:\b0(?:\.0)?\s*{_CREDIT_PREFIX}{_CREDIT_WORDS}"
    rf"|{_CREDIT_WORDS}\s*[:=-]?\s*0(?:\.0)?\b)",
    re.IGNORECASE,
)

# Continuing education units, dotted and undotted. Not academic credits,
# and not the same CTDL property.
CEU_RE = re.compile(r"\bC\.?E\.?U\.?s?\b|\bcontinuing\s+education\s+units?\b")

# --- relationships between courses ------------------------------------------

# "Prerequisite", "Pre-requisite", "Pre requisite", singular or plural.
PREREQUISITE_RE = re.compile(r"\bpre[\s-]?requisites?\b", re.IGNORECASE)
COREQUISITE_RE = re.compile(r"\bco[\s-]?requisites?\b", re.IGNORECASE)

# One heading covering both relations, in the four spellings catalogs use to
# join them: a slash, an ampersand, "and", or "or".
PREREQ_COREQ_COMBINED_RE = re.compile(
    r"\bpre[\s-]?requisites?\s*(?:/|&|\band\b|\bor\b)\s*co[\s-]?requisites?\b",
    re.IGNORECASE,
)

# "Recommended" on its own, and the three things it is usually
# recommending. A recommendation is not a requirement, so it needs its own
# marker rather than joining the prerequisite list.
RECOMMENDED_RE = re.compile(
    r"\brecommended\b(?:\s+(?:pre[\s-]?requisites?|preparation|background))?",
    re.IGNORECASE,
)

# --- outcomes and competencies -----------------------------------------------

# A competency list is a lead-in and the statements right after it, read
# from the page's own content lines. Matching the word "outcome" anywhere
# fired on "(satisfies General Education Outcome 1.1)" beside every course
# at the University of Arkansas and on course titles like "Psychotherapy
# Outcomes", then counted every <li> after them, the footer's included,
# while missing Atlantic Cape's 85 lists, whose lead-in is a <div>.
#
# The lead-in comes in two shapes:
#
#   the heading  - the whole line names the list: "Student Learning
#                  Outcomes", "Learning Outcomes:", "Program Competencies",
#                  "School of Law Learning Outcomes", "Goals and Objectives
#                  for the M.S.", and the vendor spelling "Skills measured".
#                  The noun is plural, because "Technological Competency" is
#                  a general education category, not a list.
#   the sentence - a line ending in a colon that introduces the list:
#                  "Upon completion of this program students will be able
#                  to:", "...provides graduates with the following learning
#                  outcomes:"
#
# Either way the list has to be about what a learner will know or do.
# "Objectives" on their own belong to whoever wrote them: "The objectives
# of the center are to: Provide professional development" and "the
# following program objectives: To educate practitioners" are what a
# center and a program do, so only course, learning, and student
# objectives count.
_OUTCOMES_TAIL = r"(?:\s+(?:for|of|in)\s+.{1,80})?\s*[:.]?\s*$"
OUTCOMES_HEADING_RE = re.compile(
    rf"^(?:[\w&'’.-]+\s+){{0,6}}?(?:learning\s+)?(?:outcomes|competencies)"
    rf"{_OUTCOMES_TAIL}"
    r"|^(?:[\w&'’.-]+\s+){0,4}?"
    r"(?:course|learning|student|instructional|performance)\s+objectives"
    rf"{_OUTCOMES_TAIL}"
    rf"|^(?:[\w&'’.-]+\s+){{0,4}}?goals\s+and\s+objectives{_OUTCOMES_TAIL}"
    r"|^skills\s+measured\s*:?\s*$"
    r"|^what\s+you(?:['’]?ll|\s+will)\s+learn\b.{0,40}$",
    re.IGNORECASE,
)
OUTCOMES_LEAD_IN_RE = re.compile(
    r"\b(?:students?|graduates?|learners?|participants?|you)\s+"
    r"(?:will|should|shall)\s+(?:be\s+able\s+to|have\s+the\s+ability\s+to)\b"
    r"|\bthe\s+following\s+(?:[\w-]+\s+){0,3}"
    r"(?:outcomes|competencies|skills)\b"
    # "These student learning outcomes are linked to the program goals.
    # They are:"
    r"|\blearning\s+(?:outcomes|objectives)\b|\bcompetencies\b"
    r"|\bcourse\s+objectives\b",
    re.IGNORECASE,
)
# Lists that look like competencies and are not: a college's mission, the
# ABET program educational objectives (what graduates do years later), the
# technical standards a student must meet to be admitted, and regulations.
OUTCOMES_EXCLUDED_RE = re.compile(
    r"\bmission\b|\bvision\b|\beducational\s+objectives\b|\bregulations?\b"
    r"|\bpolic(?:y|ies)\b|\bassessment\b|\bsatisf(?:y|ies)\b"
    r"|\badmi(?:ssion|tted)\b|\bapplicants?\b|\btechnical\s+standards\b"
    r"|\bmust\s+(?:be\s+met|possess)\b",
    re.IGNORECASE,
)

# The verbs an outcome is written with, in the base form that follows "will
# be able to": "Demonstrate", "Apply", "Communicate effectively". A course
# description opens with the third person ("Examines", "Introduces"), which
# keeps a course title ending in "Outcomes" from reading as a list.
_OUTCOME_VERBS = (
    "accept|access|achieve|acquire|adapt|address|administer|advocate|analy[sz]e"
    "|anticipate|apply|appraise|appreciate|articulate|assemble|assess|assist"
    "|build|calculate|categorize|choose|classify|collaborate|collect"
    "|communicate|compare|compile|complete|compose|compute|conduct|configure"
    "|connect|construct|contrast|contribute|convert|coordinate|create"
    "|critique|debate|define|deliver|demonstrate|describe|design|detect"
    "|determine|develop|diagnose|differentiate|discuss|distinguish|document"
    "|draft|draw|earn|edit|employ|engage|estimate|evaluate|examine|execute"
    "|exhibit|explain|explore|express|facilitate|formulate|foster|function"
    "|generate|identify|illustrate|implement|improve|incorporate|infer"
    "|integrate|interpret|investigate|justify|know|lead|locate|maintain"
    "|make|manage|measure|monitor|navigate|negotiate|operate|organi[sz]e"
    "|outline|participate|perform|plan|practi[cs]e|predict|prepare|present"
    "|prioritize|produce|promote|propose|provide|read|recall|recogni[sz]e"
    "|recommend|reflect|relate|report|research|respond|review|revise|select"
    "|solve|speak|summari[sz]e|support|synthesi[sz]e|teach|think|translate"
    "|troubleshoot|understand|use|utili[sz]e|value|verify|work|write"
)
# What may open an outcome before its verb: a number or bullet ("CE1.",
# "2)", "SLO 3:"), a short label ("Thesis: Students will..."), and the
# adverb some lists lead with ("Correctly explain", "Safely execute").
_OUTCOME_ENUMERATOR = (
    r"(?:(?:[A-Z]{1,4}\s?)?\d{1,2}[.):\]]?\s+|\(?[a-z]\)\s+|[a-z]\.\s+"
    r"|[•·▪◦*–-]\s*)?"
    r"(?:[A-Z][\w-]{1,15}:\s+)?"
)
OUTCOME_STATEMENT_RE = re.compile(
    rf"^{_OUTCOME_ENUMERATOR}"
    r"(?:(?:correctly|effectively|critically|clearly|safely|accurately"
    r"|ethically|independently|professionally|responsibly|successfully"
    r"|appropriately|competently|creatively|collaboratively)\s+)?"
    rf"(?:{_OUTCOME_VERBS})\b"
    rf"|^{_OUTCOME_ENUMERATOR}(?:an?\s+)?(?:ability|abilities|capacity"
    r"|knowledge|understanding|awareness|proficiency|competence|skills?)"
    r"\s+(?:to|of|in)\b"
    rf"|^{_OUTCOME_ENUMERATOR}(?:(?:our\s+)?graduates?|students?|learners?)"
    r"\s+(?:will|should|can|shall)\b",
    re.IGNORECASE,
)
# An outcome is a sentence, not a word and not a paragraph.
OUTCOME_ITEM_MIN_CHARS = 15
OUTCOME_ITEM_MAX_CHARS = 400
# Lines between a lead-in and its first item: the sentence that sometimes
# introduces the list under its heading. A new heading ends the search.
OUTCOME_LEAD_GAP_LINES = 2

# --- credentials --------------------------------------------------------------

# Degree names as a catalog writes them out. "Associate" on its own is a job
# title ("Associate Dean"), so it has to be followed by of, in, or degree.
# "Master" on its own is "master syllabus" and "master schedule", so it gets
# the same treatment. "Bachelor" and "doctorate" stand alone safely.
_AWARD_DEGREE_WORDS = (
    r"\bdegrees?\b"
    r"|\bassociate\s+(?:of|in|degree)\b"
    r"|\bbachelor(?:['’]?s)?\b"
    r"|\bmaster(?:['’]?s)?\s+(?:of|in|degree)\b"
    r"|\bdoctor(?:ate|al)\b"
)

# Dotted abbreviations only for the ones that are also ordinary words.
# Case-insensitively, a bare A.S. without its dots is the word "as", and a
# bare M.A. is a parent; both appear on every page ever written.
_AWARD_DOTTED = (
    r"\bA\.A\.S\.|\bA\.A\.T\.|\bA\.G\.S\.|\bA\.F\.A\.|\bA\.A\.|\bA\.S\."
    r"|\bB\.A\.|\bB\.S\.N\.|\bB\.F\.A\.|\bB\.S\."
    r"|\bM\.B\.A\.|\bM\.F\.A\.|\bM\.S\.N\.|\bM\.A\.|\bM\.S\."
    r"|\bEd\.D\.|\bD\.N\.P\.|\bPh\.D\."
)

# The undotted abbreviations that are not English words, so they are safe
# bare. AA, AS, BA, BS, MA and MS are missing for the reason above.
_AWARD_UNDOTTED = (
    r"\bAAS\b|\bAAT\b|\bAGS\b|\bAFA\b|\bBFA\b|\bBSN\b|\bMBA\b|\bMFA\b"
    r"|\bMSN\b|\bDNP\b|\bEdD\b|\bPhD\b|\bCCL\b"
)

# Everything awarded that is not a degree. "Certified" is here because a
# certification names itself that way in a heading ("Microsoft 365
# Certified: Endpoint Administrator Associate") and never prints the noun.
# "Microcertificate" is one word in CourseLeaf graduate catalogs, so the
# boundary in front of "certificate" never matched it and every University
# of Arkansas microcertificate read as a program with no award.
# "Professional Series" is an award type with no award noun in it: Atlantic
# Cape badges 23 programs with it and defines it as a group of courses that
# earns a certificate of achievement.
_AWARD_NON_DEGREE = (
    r"\bcertificates?\b|\bcertifications?\b|\bcertified\b|\bdiplomas?\b"
    r"|\bmicro-?(?:credentials?|certificates?)\b|\bcredentials?\b"
    r"|\bdigital\s+badges?\b"
    r"|\blicen[sc]e\b|\blicensure\b|\bendorsements?\b"
    r"|\bapprenticeships?\b|\bjourney(?:man|worker)\b"
    r"|\bprofessional\s+series\b"
)

CREDENTIAL_AWARD_RE = re.compile(
    rf"{_AWARD_NON_DEGREE}|{_AWARD_DEGREE_WORDS}|{_AWARD_DOTTED}"
    rf"|{_AWARD_UNDOTTED}",
    re.IGNORECASE,
)

# Dotted degree abbreviations as a family rather than a list: B.S.E.,
# B.H.R.D., B.S.Ch.E., M.Ed., Ed.S., Pharm.D. CourseLeaf names a degree this
# way ("Human Resource Development B.H.R.D.") and a fixed list never keeps
# up. Case-sensitive, so "e.g." and "a.m." stay words, and the three that
# are also a time or a place are refused outright. J and LL start only the
# law degrees: as a family they read the "J.B." of "J.B. Hunt Center" as a
# degree on every engineering page.
DOTTED_DEGREE_RE = re.compile(
    r"(?<![A-Za-z.])(?!A\.M\.|D\.C\.|B\.C\.)"
    r"(?:(?:A|B|M|D|Ph|Ed|Pharm|Psy)\.(?:[A-Z][a-z]{0,3}\.){1,4}"
    r"|J\.D\.|LL\.[BMD]\.)"
)

# Nouns that say a page is about some award without saying which: "the
# degree requirements", "Degree Program Criteria", "Initial Teacher
# Licensure". None of them names an award a page could be about.
GENERIC_AWARD_RE = re.compile(
    r"^(?:degrees?|credentials?|licensure)$", re.IGNORECASE
)

# A level with no field after it: "Bachelor", "Master of", "Associate
# degree", "Doctorate". It says a degree of that level exists without
# saying which one, so it is not a second award beside "B.S.N." - see
# distinct_awards.
BARE_AWARD_LEVEL_RE = re.compile(
    r"^(?:the\s+)?(?:associate|bachelor|master|doctor)(?:['’]?s)?"
    r"(?:\s+(?:of|in|degree))?$"
    r"|^(?:doctorate|doctoral|degrees?|credentials?|licensure)$",
    re.IGNORECASE,
)

# An award the page says it is not. Atlantic Cape badges its English
# language program "Program (not a degree)", and the word degree alone read
# that page as a degree.
NEGATED_AWARD_RE = re.compile(
    r"\bnot\s+an?\s+(?:degree|certificate|credential)\b"
    r"|\bnon[\s-]?(?:degree|credential)(?:[\s-]seeking)?\b"
    r"|\bdoes\s+not\s+(?:lead\s+to|award|grant)\s+an?\s+"
    r"(?:degree|certificate|credential)\b",
    re.IGNORECASE,
)

# Awards in a list: "B.S.E. or B.S. or B.S.N.", "Master of Arts, Master of
# Science". A heading like that is about a college's rules for all of
# them, not about one credential.
AWARD_LIST_SEPARATOR_RE = re.compile(r"\bor\b|[,;]", re.IGNORECASE)

# The family an award belongs to. One page name can say "Bachelor of
# Science in Nursing (BSN)" and still name one award, but "Associate Degree
# and Certificate Requirements" names two kinds and is a policy page.
_CERTIFICATE_FAMILY_RE = re.compile(
    r"certif|diploma|micro|series|badge|endorse|apprentice|journey",
    re.IGNORECASE,
)
_LICENSE_FAMILY_RE = re.compile(r"licen[sc]", re.IGNORECASE)

# A page name that lists: an award noun, or programs, in the plural, or a
# noun that says outright that the page is a list. "Degrees and
# Certificates", "Academic Degrees", "Degree Programs", "General Education
# Courses at Atlantic Cape", "Accelerated Bachelor to Master Program
# Listing". A credential page names its award in the singular, and does
# not call itself a listing.
LISTING_NAME_RE = re.compile(
    r"\b(?:degrees|certificates|certifications|credentials|diplomas"
    r"|micro-?(?:certificates|credentials)"
    r"|programs|majors|minors|options|pathways|awards|courses"
    r"|listings?|indexe?s?|directory|offerings|catalogs?|catalogues?"
    r"|(?:fields|areas)\s+of\s+study)\b",
    re.IGNORECASE,
)
# An award named in the plural is a list of them: "Graduate Certificates
# and Microcertificates Offered" heads the page that lists every one.
PLURAL_AWARD_RE = re.compile(
    r"^(?:micro-?)?(?:certificates|credentials)|certifications|diplomas"
    r"|badges|licenses|degrees$",
    re.IGNORECASE,
)

# A page name about rules: "Graduation Requirements", "Degree Program
# Criteria", "Objectives and Regulations". Only the last word counts, so a
# heading that reads "Requirements for the B.S." is still about one award.
POLICY_NAME_RE = re.compile(
    r"\b(?:requirements?|polic(?:y|ies)|criteria|procedures?|regulations?"
    r"|guidelines?|agreements?|appeals?|residency)\W*$",
    re.IGNORECASE,
)

# A page name that is an award type and nothing else: "Associate in
# Applied Science", "Certificate", "Professional Series". Atlantic Cape
# keeps one such page per award type, and it lists every program of that
# type rather than describing one.
AWARD_TYPE_ONLY_RE = re.compile(
    r"^\s*(?:(?:the\s+)?(?:associate|bachelor|master|doctor)(?:'?s)?"
    r"(?:\s+(?:degree|of|in))?"
    r"(?:\s+(?:applied|fine|general|liberal|occupational|arts?|science"
    r"|sciences|studies|technology|business|education|and|in|of))*"
    r"|certificates?|diplomas?|degrees?|credentials?|certifications?"
    r"|professional\s+series)"
    r"(?:\s*\((?:[A-Z]\.?){2,5}\))?\s*$",
    re.IGNORECASE,
)

# An organization's name: a college, a school, a department. Its page
# prints college-wide requirements and lists every program under it, and
# is neither a program nor a credential. "Honors College" and "Walton
# College of Business" both count; "Nursing" does not.
ORG_NAME_RE = re.compile(
    r"^(?:the\s+)?(?:[\w&.'-]+\s+){0,4}"
    r"(?:college|school|department|division|faculty|institute|center"
    r"|centre|academy|office)\s+(?:of|for)\s+"
    r"|^(?:the\s+)?(?:[\w&.'-]+\s+){0,4}(?:college|school)"
    r"(?:\s*\([^)]*\))?\s*$",
    re.IGNORECASE,
)

# The badge beside a program's name: a line that is an award's name and
# nothing else. "Associate in Science", "Certificate", "Professional
# Series", "Graduate Microcertificate in Regression", "Master of Science in
# Environmental Resiliency (ENREMS)", "M.S., Ph.D. (CSES)". Taking any award
# word from the lines around the name took CourseLeaf's contact block
# instead: "Ph.D. Program Director", "504 J.B. Hunt Building", "J.D.
# Willson", "Christopher Nelson, Ph.D.".
_BADGE_DOTTED = (
    r"(?:(?:A|B|M|D|Ph|Ed|Pharm|Psy)\.(?:[A-Z][a-z]{0,3}\.){1,4}"
    r"|J\.D\.|LL\.[BMD]\.)"
)
# Words match in any case; the capitals of a field name ("in Applied
# Science") and of an abbreviation do not, so a sentence is never a badge.
_BADGE_AWARD = (
    r"(?:(?i:graduate|undergraduate|online|professional|technical|advanced"
    r"|post-?(?:master|baccalaureate)['’]?s?)\s+)?"
    r"(?:(?i:associate|bachelor|master|doctor)(?:['’]?s)?\s+(?i:of|in)\s+"
    r"(?:(?i:applied|fine|general|liberal)\s+)?"
    r"[A-Z][\w&'’-]*(?:\s+(?:and\s+)?[A-Z][\w&'’-]*){0,3}"
    r"|(?i:(?:micro-?)?certificate(?:\s+of\s+(?:achievement|completion"
    r"|proficiency))?|certification|diploma|professional\s+series"
    r"|micro-?credential|digital\s+badge)"
    rf"|{_BADGE_DOTTED}(?:\s*(?:,|/|and|or)\s*{_BADGE_DOTTED})*"
    r"|AAS|AAT|AGS|AFA|BFA|BSN|MBA|MFA|MSN|DNP|EdD|PhD)"
)
AWARD_NAME_LINE_RE = re.compile(
    # The award, then only its subject or its code.
    rf"^{_BADGE_AWARD}(?:\s+(?i:in|of)\s+[^,;]{{1,80}})?"
    r"(?:\s*\([^)]*\))?\s*[:.]?\s*$"
    # A plan of study named for its degree: "Human Resources Management
    # B.S.B.A.". No comma before the degree, which is how a person with a
    # doctorate is written.
    rf"|^[A-Z][\w&'’-]*(?:\s+[\w&'’-]+){{0,8}}\s+{_BADGE_DOTTED}\s*$"
)
# A line about a person or an office, however it starts.
CONTACT_LINE_RE = re.compile(
    r"\b(?:director|coordinator|chair(?:person)?|dean|advis[eo]r|manager"
    r"|professor|lecturer|website|web\s+site|e-?mail|phone|office|contact)\b",
    re.IGNORECASE,
)
# How to reach the person, which is what makes a line naming one a contact
# block rather than a sentence about them. "Students should speak with an
# advisor before registering" names a role and is the page's own prose;
# "Dr. David Welky, Chair, Department of History, Irby 105B, (501)
# 450-5624" is the contact block a bulletin opens with, and reading it as
# the page's first paragraph gave a minor a description made of telephone
# numbers.
PHONE_OR_EMAIL_RE = re.compile(
    r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b|[\w.+-]+@[\w-]+\.\w{2,}"
)

# The program talking about itself in its first sentence. The award has to
# be in the sentence's subject, the words before its verb: "This degree can
# lead to", "The Practical Nursing Certificate program is designed", "The
# graduate microcertificate in Regression provides", "Program Description:
# The post master's Advanced ... Certificate is designed". "The Academic
# English Language program is designed for students who want to earn a
# certificate or degree" names awards only after its verb, as a goal of
# the students it serves, and names none of its own.
_INTRO_ARTICLE_RE = re.compile(
    r"^(?:[A-Z][\w-]*(?:\s+[A-Z][\w-]*){0,2}:\s*)?(?:the|this|our|a|an)\s",
    re.IGNORECASE,
)
_INTRO_VERB_RE = re.compile(
    r"\s(?:is|are|was|were|provides?|prepares?|offers?|allows?|combines?"
    r"|focuses|leads?|can|will|may|requires?|consists|includes?|gives?"
    r"|trains?|equips?|introduces?|builds?|develops?|serves?|emphasizes?"
    r"|enables?|helps?|has|have|meets?|addresses|examines?|explores?)\b",
    re.IGNORECASE,
)
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
# The award noun a subject ends on, when it names the award generically:
# "This degree", "The certificate program".
_SUBJECT_AWARD_NOUN_RE = re.compile(
    r"\b(degree|certificate|microcertificate|micro-certificate|diploma"
    r"|certification|credential)(?:\s+program)?\s*$",
    re.IGNORECASE,
)
# "This certificate is designed for working professionals", anywhere in
# the paragraph.
_THIS_AWARD_RE = re.compile(
    r"\bthis\s+(?:[\w-]+\s+){0,3}(degree|certificate|microcertificate"
    r"|diploma|certification|credential)\b",
    re.IGNORECASE,
)
INTRO_SUBJECT_WORDS = 16

# An award followed by the page's own name: "the Graduate Certificate
# Program in Building-Level Administration" on the page of that name.
_OWN_AWARD_WORDS = (
    r"(?:certificate|microcertificate|degree|diploma|certification"
    r"|associate|bachelor|master|doctorate)\b(?:\s+program)?\s+(?:in|of)\s+"
)

# The page's own name, then its award: "Special Education Transition
# Services Graduate Certificate is designed to".
_NAME_THEN_AWARD_RE = re.compile(
    r"^\s*(?:graduate|undergraduate|professional|technical)?\s*"
    r"(?:certificate|microcertificate|micro-certificate|degree|diploma"
    r"|associate|bachelor|master|doctorate)\b",
    re.IGNORECASE,
)

# A trailing "(OMOA)" or "(AAS)" after a page's name, dropped before the
# name is looked for in the first paragraph.
_TRAILING_CODE_RE = re.compile(r"\s*\([^)]*\)\s*$")

# --- programs -----------------------------------------------------------------

# What a page mentions, anywhere in its content. Too loose to say a page is
# a program: a policy page says "degree requirements" and a refund schedule
# says "Fall semester". It answers one narrower question, below, and the
# program rules use the stricter evidence after it.
PROGRAM_TERM_RES = {
    # The award vocabulary again, counted as a term so a reviewer can see
    # which page said what. On its own it proves nothing.
    "degree": re.compile(
        rf"{_AWARD_DEGREE_WORDS}|{_AWARD_DOTTED}|\bAAS\b", re.IGNORECASE
    ),
    "certificate": re.compile(r"\bcertificates?\b|\bdiploma\b", re.IGNORECASE),
    # A heading only a page describing its own requirements prints.
    "program_requirements": re.compile(
        r"\bprogram\s+requirements?\b|\bdegree\s+requirements?\b"
        r"|\brequirements?\s+for\s+(?:the\s+)?(?:degree|certificate|major)\b",
        re.IGNORECASE,
    ),
    # The total for the whole credential, not the credits of one course.
    "total_credits": re.compile(
        r"\btotal\s+(?:program\s+|degree\s+|required\s+)?"
        r"(?:credits?|credit\s+hours?)\b",
        re.IGNORECASE,
    ),
    # The five names a catalog gives the term-by-term course list.
    "plan_of_study": re.compile(
        r"\bplan\s+of\s+study\b|\bcurriculum\s+(?:plan|map|guide)\b"
        r"|\bprogram\s+map\b|\bsuggested\s+sequence\b|\bcourse\s+sequence\b",
        re.IGNORECASE,
    ),
    # Term headings inside that list. The weakest of the six: a course
    # description that says "offered Fall semester" prints one too, which
    # is why it is left out of PROGRAM_STRUCTURE_TERMS.
    "term_sequence": re.compile(
        r"\b(?:first|second|third|fourth|1st|2nd|3rd|4th)\s+"
        r"(?:semester|term|year)\b"
        r"|\b(?:fall|spring|summer|winter)\s+(?:semester|term)\b",
        re.IGNORECASE,
    ),
}

# The subset that says the page talks about requirements. Used for one
# question: when a page holds many course codes, is that list the page's
# own requirements, or is the page a run of course descriptions? A term
# sequence does not answer it, so it is left out here.
PROGRAM_STRUCTURE_TERMS = frozenset(
    {"program_requirements", "total_credits", "plan_of_study"}
)

# The evidence that a page prints a program's own requirements. Each of
# these reads the page's content only, never its menus.

# The credit total for the whole program, with its number: "Total Credits
# 60", "Total Hours: 18", "60 total credits", "Credits Required: 64". The
# number is what separates a program's total from a policy sentence about
# the total credits a student has attempted.
#
# Read a line at a time, and only lines short enough to be a heading or a
# table row - see total_credits_line below. A catalog prints the total as
# its own line or the last row of the requirement table; every one of the
# 67 program totals at Atlantic Cape is on a line of 40 characters or
# less. Searched over the whole page it matched inside a course's
# prerequisite sentence ("Prerequisites: FILM 2310 and 2666 and 45 total
# credit hours completed"), which turned a page of film course
# descriptions into a learning opportunity.
TOTAL_CREDITS_RE = re.compile(
    r"\btotal\s+(?:program\s+|degree\s+|required\s+|certificate\s+|major\s+)?"
    r"(?:credits?|credit\s+hours?|semester\s+hours?|units?|hours)"
    r"(?:\s+required)?\s*[:=-]?\s*\d"
    r"|\b\d+(?:\.\d+)?\s*(?:-\s*\d+\s*)?total\s+"
    r"(?:credits?|credit\s+hours?|units?)\b"
    r"|\b(?:minimum\s+)?(?:credits?|credit\s+hours?|units?)\s+required"
    r"(?:\s+for\s+(?:the\s+)?(?:degree|certificate|program|major))?"
    r"\s*[:=]\s*\d",
    re.IGNORECASE,
)

# A section heading over the program's own requirements. The whole line has
# to be the heading, so a fee table row that opens "Curriculum Instruction
# Education Internship Fee" is not one. The words in front of
# "requirements" are the kinds of program, so "Admission Requirements" and
# "Graduation Requirements", which every policy page prints, are not either.
#
# The word on its own counts too. A page headed just "Requirements" over a
# list of courses is printing its own, and the words that make the other
# spellings unsafe - admission, graduation - are absent by definition when
# there is no word in front of it. Two pre-professional programmes at
# Central Arkansas head their course lists exactly that way and were read
# as neither a programme nor anything else.
REQUIREMENTS_HEADING_RE = re.compile(
    r"^(?:requirements?"
    r"|(?:program|degree|certificate|major|minor|concentration|option"
    r"|track|emphasis|core|curriculum|course|departmental"
    r"|general\s+education)\s+(?:requirements?|courses?)"
    r"|requirements?\s+for\s+(?:the\s+|a\s+|an\s+)?"
    r"(?:graduate\s+|undergraduate\s+)?"
    r"(?:degree|certificate|major|minor|program|concentration)s?"
    r"(?:\s+in\s+.+)?"
    r"|required\s+courses?|major\s+courses?|core\s+courses?"
    r"|courses?\s+required"
    r"|plan\s+of\s+study|program\s+of\s+study"
    r"|curriculum(?:\s+(?:plan|map|guide|outline))?"
    r"|program\s+map|degree\s+map|degree\s+plan"
    r"|(?:suggested|recommended)\s+(?:course\s+)?sequence|course\s+sequence"
    r"|sample\s+(?:plan|schedule)|program\s+(?:outline|curriculum)"
    r"|(?:eight|four|two)[\s-](?:semester|year)\s+plan|semester\s+plan)"
    r"(?:\s*\([^)]*\))?\s*[:.]?\s*$",
    re.IGNORECASE,
)

# "Requirements" in a heading that also names one award: "Requirements for
# the Master of Science (M.S.) Degree", "Requirements for B.S.E. in
# Childhood Education". The strongest evidence a page prints, because it
# says both that these are a program's requirements and whose.
REQUIREMENT_WORD_RE = re.compile(r"\brequirements?\b", re.IGNORECASE)

# The page stating which awards it confers: "Degrees Conferred:", "Degree
# Offered", "Graduate Certificate Offered (non-degree):", "Award Type:
# Certificate". It has to be a label, alone on its line or ending in a
# colon, not a sentence that opens with those words, and it counts only
# when it or the lines after it name an award, because a college overview
# prints "Degrees Offered" over a paragraph about itself.
AWARD_DECLARATION_RE = re.compile(
    r"^(?:(?:graduate|undergraduate|online)\s+)?"
    r"(?:(?:micro-?)?(?:degrees?|certificates?|credentials?|awards?"
    r"|microcertificates?)\s+(?:conferred|offered|awarded|granted|earned)"
    r"|(?:degree|award|credential|certificate)\s+(?:types?|levels?))"
    r"(?:\s*\([^)]*\))?\s*(?::|$)",
    re.IGNORECASE,
)

# A term heading inside a plan of study: "First Year", "Fall Semester",
# "Semester 2". A refund schedule prints Fall, Spring and Summer too, so
# these count only over a list of courses (MIN_PLAN_CODES).
TERM_HEADING_RE = re.compile(
    r"^(?:(?:first|second|third|fourth|fifth|sixth|1st|2nd|3rd|4th)\s+"
    r"(?:semester|term|year|quarter)"
    r"|(?:semester|term|year|quarter)\s+(?:one|two|three|four|[1-8])"
    r"|(?:fall|spring|summer|winter)\s+(?:semester|term|quarter)?\s*"
    r"(?:(?:year\s+)?[1-4]|i{1,3}|iv)?)\b",
    re.IGNORECASE,
)

# A heading that opens with a course code is a course's title. CourseLeaf
# titles read "FREN 30603. Ph.D. Reading Requirement I. 3 Hours.", which
# otherwise reads as a heading over a Ph.D.'s requirements. Five digits,
# because graduate course numbers there are five digits long.
COURSE_TITLE_RE = re.compile(
    r"^\s*[A-Z]{2,6}[\s ‑–-]?[A-Z]?\d{3,5}[A-Z]{0,2}\b"
)

# The outline number a catalog prints in front of a heading, which is not
# part of the heading. The University of Central Arkansas numbers every
# one of them - "[2] Baccalaureate Degree: Bachelor of Science", "[2.2]
# Biology Track (50 hours)" - and every heading rule above is anchored at
# the start of the line, so none of them matched and a whole bulletin's
# programs went unlabelled.
#
# A bracketed number or a plain numbered prefix, each followed by a space.
# A lettered prefix would eat the award out of "B. S. in Nursing", and
# digits with only a space after them are a year, not an outline number.
OUTLINE_NUMBER_RE = re.compile(
    r"^\s*(?:\[\d+(?:\.\d+)*\]|\d+(?:\.\d+)*[.)])\s+"
)


def heading_body(line: str) -> str:
    """A heading without the outline number printed in front of it."""
    return OUTLINE_NUMBER_RE.sub("", line or "").strip()


# --- the page's own content ---------------------------------------------------

# Site furniture: the menus, sidebars and footers every page repeats, found
# by tag and by ARIA landmark. A <header> is furniture only when it is the
# site's banner, because Clean Catalog prints a program's h1 and award badge
# inside a <header> of the program's own.
CHROME_TAGS = frozenset({"nav", "aside", "footer"})
CHROME_ROLES = frozenset(
    {
        "navigation",
        "banner",
        "contentinfo",
        "complementary",
        "search",
        "menu",
        "menubar",
    }
)
MAIN_TAG = "main"
MAIN_ROLE = "main"

# Furniture a site names rather than marks up. A breadcrumb repeats the
# page's own name and its course code one line above the heading, and a
# skip link prints "Skip to Content" as the first line of every page.
#
# Matched against one whole class or id at a time, with at most one word
# of prefix and one of the layout suffixes after it. Anything looser
# swallows content: ".*breadcrumb.*" reads "course-breadcrumb-free" as a
# menu, and a rule that matched anywhere in the attribute would drop a
# program's own "course-menu" section.
_CHROME_WORDS = (
    r"breadcrumbs?|skip-?(?:link|to-?content|nav)?|site-?header|site-?footer"
    r"|navbar|nav-?(?:bar|menu|list|wrapper)|mega-?menu|sidebar|side-?nav"
    r"|utility-?nav|toolbar|cookie-?(?:banner|notice|bar)?|social-?links?"
)
CHROME_CLASS_RE = re.compile(
    rf"^(?:[a-z]+[-_])?(?:{_CHROME_WORDS})"
    r"(?:[-_](?:wrapper|container|list|inner|outer|region|nav|menu|bar|area))?$",
    re.IGNORECASE,
)

# Where a page keeps its own content when it marks up no <main> and sets no
# role. Coursedog writes <div id="main-content" role="main">, Drupal writes
# <div class="region-content">, and WordPress themes write <div id="content">.
# Read in this order, most explicit first.
MAIN_CONTAINER_IDS = (
    "main-content",
    "maincontent",
    "main",
    "content",
    "page-content",
    "content-main",
)
MAIN_CONTAINER_CLASSES = (
    "main-content",
    "region-content",
    "page-content",
    "content-main",
    "main-container",
)

# --- markup shapes ------------------------------------------------------------
#
# What a catalog platform marks up rather than prints. These say, in the
# markup itself, what a flattened page can only be guessed at: which runs
# of text are course descriptions, and which lists of course codes are a
# program's requirements rather than descriptions of those courses.

# One course, described. CourseLeaf writes <div class="courseblock">,
# Acalog <div class="courseblock" | "acalog-course">, Clean Catalog gives
# each course its own node, and Coursedog names the panel after the course.
COURSE_BLOCK_CLASS_RE = re.compile(
    r"\bcourse-?block\b|\bsc_courseblock\b|\bacalog-course\b"
    r"|\bcourse-?description\b|\bcourse-?detail\b|\bcourse-?card\b"
    r"|\bnode--type-(?:class|course)\b",
    re.IGNORECASE,
)

# A table of course codes: CourseLeaf's <table class="sc_courselist">,
# Acalog's cores. Whatever the table is for, the codes in it are
# references to courses described elsewhere, never descriptions.
COURSE_LIST_CLASS_RE = re.compile(
    r"\bsc_courselist\b|\bcourse-?list\b|\bacalog-core\b",
    re.IGNORECASE,
)

# A list whose class says outright that it is a program's requirements.
REQUIREMENT_LIST_CLASS_RE = re.compile(
    r"\bplan-?grid\b|\bprogram-?requirements?\b"
    r"|\brequirements?-?(?:table|list|grid)\b"
    r"|\bcurriculum-?(?:table|list|grid)\b|\bdegree-?plan\b",
    re.IGNORECASE,
)

# The column that turns a course list into a program's requirements: the
# one printing what each course is worth. A requirement list says how many
# credits each of its courses carries; an index of courses and a transfer
# equivalency table do not, and reading either as a program's own
# requirements made a transfer-of-credit policy at the University of
# Arkansas a LearningOpportunity with 167 courses in it.
CREDIT_COLUMN_CLASS_RE = re.compile(
    r"\b(?:hours?|credits?|units?|sh|ch)-?col(?:umn)?\b"
    r"|\bcol-?(?:hours?|credits?|units?)\b",
    re.IGNORECASE,
)

# The class a platform puts on a link to another course, so a cross
# reference inside a description is not a second course. CourseLeaf writes
# <a class="bubblelink code">.
COURSE_REFERENCE_CLASS_RE = re.compile(
    r"\bbubblelink\b|\bcodecol\b|\bcourse-?link\b|\bcourse-?ref\b",
    re.IGNORECASE,
)

# The page type a CMS publishes under, from the class it stamps on the
# node: Drupal's "node--type-degree", WordPress's "type-course" and
# "post-type-program", Coursedog's "page-type-program". Read for the
# report and for grouping patterns, never mapped straight to a CTDL label:
# the taxonomy is the college's own, so "degree" on one site is a
# credential and on the next is the department that grants it.
CMS_NODE_TYPE_RE = re.compile(
    r"\bnode--type-([a-z0-9-]+)\b|\b(?:post|page)-type-([a-z0-9-]+)\b",
    re.IGNORECASE,
)
# The view a CMS rendered the node in. Only a full node is the page's own
# subject; a teaser is one row of a listing.
CMS_FULL_VIEW_RE = re.compile(r"\bview-mode-full\b|\bnode--view-mode-full\b")

# --- printed fields ----------------------------------------------------------
#
# How a catalog platform marks up a label and the value beside it. Every
# one of them wraps the pair, names the label, and names the value:
# Drupal writes field__label and field__item inside a field--name-* div,
# Coursedog writes field-label and field-value inside a .field, and the
# rest of the web writes <dt>/<dd> or <th>/<td>. Extraction reads these
# rather than looking for "Credits" in a wall of text, where the
# normalizer has already glued the label to its value ("Credits3").
#
# Matched against one whole class word at a time, never the whole class
# string. Coursedog wraps three fields in a `field-row`, and a pattern
# that matched "field" inside it took the row for one field and read the
# first label with the first value, losing the two fields after it.
FIELD_WRAPPER_CLASS_RE = re.compile(
    r"^(?:field|field-component|field--name-[\w-]+)$",
    re.IGNORECASE,
)
FIELD_LABEL_CLASS_RE = re.compile(
    r"^(?:field__label|field-label|field-name)$", re.IGNORECASE
)
FIELD_VALUE_CLASS_RE = re.compile(
    r"^(?:field__items?|field-value|field-content)$", re.IGNORECASE
)
# The platform's own name for a field, when the label is not printed:
# Clean Catalog gives the description div "field--name-field-description"
# and prints no label over it.
FIELD_NAME_RE = re.compile(r"field--name-(?:field-)?([\w-]+)", re.IGNORECASE)

# The newer CourseLeaf theme names each part of a course block instead of
# printing them on one line: `detail-code`, `detail-title`,
# `detail-prerequisites`, `detail-coreq`. The value carries its own label
# inside a `span.label` ("Prerequisite: Junior standing"), which is not
# part of the value.
DETAIL_FIELD_CLASS_RE = re.compile(r"^detail-([\w-]+)$", re.IGNORECASE)
DETAIL_LABEL_CLASS_RE = re.compile(r"^label$", re.IGNORECASE)

# The two halves of a CourseLeaf course block: the title line, which
# carries the code, the name and the credits in one string, and the
# description under it.
COURSE_BLOCK_TITLE_CLASS_RE = re.compile(
    r"\bcourseblocktitle\b|\bcourse-?title\b|\bdetail-title\b",
    re.IGNORECASE,
)
COURSE_BLOCK_DESC_CLASS_RE = re.compile(
    r"\bcourseblockdesc\b|\bcourseblockextra\b"
    r"|\bcourse-?description-?text\b|\bdetail-description\b",
    re.IGNORECASE,
)
# The trailing credits of a CourseLeaf course-block title:
# "ASTR 50303.  Astrophysics I: Stars and Planetary Systems.  3 Hours."
# ends "3 Hours."; a variable-credit course ends "1-6 Hour.". A course
# with no credits printed ends with its name, so this has to be optional.
COURSE_BLOCK_CREDITS_RE = re.compile(
    r"(?P<credits>\d+(?:\.\d+)?)(?:\s*-\s*(?P<maximum>\d+(?:\.\d+)?))?"
    r"\s*(?:credit|hour|unit)s?\s*\.?\s*$",
    re.IGNORECASE,
)
# What separates the code, the name and the credits on that one line.
COURSE_TITLE_SPLIT_RE = re.compile(r"\s*[.:–-]\s+|\s*\.\s*")

# What a printed label means, as one canonical field name per label. The
# keys are what normalize_field_label returns, so "Credit Hour(s):" and
# "CREDIT HOURS" are one key. Only labels that map onto a canonical field
# in lib/FIELD_INVENTORY.csv are here; anything else a page prints is
# kept in the report but is not a field.
COURSE_FIELD_LABELS = {
    "credits": "course_credits",
    "credit": "course_credits",
    "credit hours": "course_credits",
    "credit hour": "course_credits",
    "credit hours min": "course_credits",
    "units": "course_credits",
    "unit": "course_credits",
    "semester hours": "course_credits",
    "description": "course_description",
    "course description": "course_description",
    "catalog description": "course_description",
    "prerequisite": "course_prerequisites",
    "prerequisites": "course_prerequisites",
    "pre-requisite": "course_prerequisites",
    "pre-requisites": "course_prerequisites",
    "prereq": "course_prerequisites",
    "corequisite": "course_corequisites",
    "corequisites": "course_corequisites",
    "co-requisite": "course_corequisites",
    "co-requisites": "course_corequisites",
    "coreq": "course_corequisites",
    "code": "course_id",
    "course code": "course_id",
    "course id": "course_id",
    "lecture hours": "course_lecture_hours",
    "lecture": "course_lecture_hours",
    "lab hours": "course_lab_hours",
    "laboratory hours": "course_lab_hours",
    "lab/clinical/field study": "course_lab_hours",
    "lab/clinical/field study hours": "course_lab_hours",
    "program": "course_program",
    "department": "course_department",
    "school": "course_school",
    "division": "course_division",
    "subject code": "course_subject_code",
    "subject": "course_subject_code",
    "course number": "course_number",
    "number": "course_number",
    "course long title": "course_long_title",
    "long title": "course_long_title",
    "title": "course_name",
    "course title": "course_name",
    "course name": "course_name",
    "academic level": "course_academic_level",
    "level": "course_academic_level",
    "general education": "course_general_education",
}
# Which record a page carrying each label should produce. The names on
# the right are what lib/mapping.py maps to a CTDL class, and they are
# not all spelled the way discovery spells its labels: the page discovery
# calls a LearningOpportunity becomes a ceterms:LearningProgram.
#
# In order. A page can carry two labels, and then the first of these is
# the record it produces: a credential page that lists what its students
# will be able to do is a credential, and the competency list on it is
# published against that credential rather than on its own. A page whose
# only label is Competency is a framework of its own.
ENTITY_TYPE_OF_LABEL = {
    LABEL_COURSE: "Course",
    LABEL_CREDENTIAL: "Credential",
    LABEL_LEARNING_OPPORTUNITY: "LearningProgram",
    LABEL_COMPETENCY: "Competency",
}

# The canonical fields whose value is a number, not a string.
NUMERIC_FIELDS = frozenset(
    {
        "course_credits",
        "course_credits_min",
        "course_credits_max",
        "course_lecture_hours",
        "course_lab_hours",
    }
)

# --- what the publisher declares ---------------------------------------------
#
# schema.org types, from JSON-LD or microdata. A publisher that says
# "this page is a Course" in machine-readable form has answered the
# question, and no amount of reading its prose beats that. Only the types
# that map onto a CTDL entity are listed; everything else a catalog
# declares ("WebPage", "BreadcrumbList", "Organization") says nothing
# about what the page is about.
SCHEMA_TYPE_LABELS = {
    "course": LABEL_COURSE,
    "courseinstance": LABEL_COURSE,
    "educationaloccupationalprogram": LABEL_LEARNING_OPPORTUNITY,
    "workbasedprogram": LABEL_LEARNING_OPPORTUNITY,
    "educationaloccupationalcredential": LABEL_CREDENTIAL,
    "degree": LABEL_CREDENTIAL,
    "certification": LABEL_CREDENTIAL,
}
# The property a declaration uses to name the award a program grants.
# A program that declares one is a Credential page, not a
# LearningOpportunity, by the same rule the prose follows.
SCHEMA_AWARD_KEYS = frozenset(
    {
        "educationalcredentialawarded",
        "occupationalcredentialawarded",
        "credentialcategory",
    }
)
# How deep into a JSON-LD document to look for typed nodes. A catalog
# nests them under @graph, itemListElement, and mainEntity, and a deeper
# walk than this is a document that is describing something else.
SCHEMA_MAX_DEPTH = 6

# What sits between a page's name and the site's name in a <title>:
# "Programs | Brookdale Community College Catalog", "Regression (REGR) <
# University of Arkansas".
TITLE_SEPARATOR_RE = re.compile(r"\s+[|<>–—]\s+|\s+-\s+")

# --- url shapes ---------------------------------------------------------------

# The last resort, read only when the page text says nothing. Both are read
# against the URL template - path and query, digits folded - and never the
# whole URL, so a college with "degree" in its hostname is not every page a
# credential.
#
# A word has to be a whole path segment, and another segment has to follow
# it. Matching anywhere in the path read "/honors-program" and
# "/credit-amnesty-program" as programs and "/academic-degrees" as a
# credential, and /programs itself is the list of programs, not one.

# Segments naming awards: /degrees-certificates/nursing,
# /credentials/certifications/x.
CREDENTIAL_URL_SEGMENTS = frozenset(
    {
        "degree",
        "degrees",
        "certificate",
        "certificates",
        "certification",
        "certifications",
        "credential",
        "credentials",
        "diploma",
        "diplomas",
        "badges",
        "licenses",
        "licensure",
        "micro-credentials",
        "microcredentials",
        "degrees-certificates",
        "degrees-and-certificates",
        "certificates-degrees",
        "degree-programs",
    }
)

# Segments naming programs of instruction: /programs/ARCH.AS,
# /catalog/majors/arts/, /programsofstudy/libs/.
PROGRAM_URL_SEGMENTS = frozenset(
    {
        "program",
        "programs",
        "major",
        "majors",
        "programs-of-study",
        "program-of-study",
        "programsofstudy",
        "plans-of-study",
        "areas-of-study",
        "academic-programs",
        "pathway",
        "pathways",
        "curriculum",
        "curricula",
        "training",
    }
)

# A segment that is a phrase rather than a word, read one word at a time:
# "programs-by-program", "academic-programs", "all-degrees". Only the
# plural counts, and that is the whole point of the rule. The plural is
# how a site names the section holding many of them; the singular is how
# it names one, and "academic-english-language-program" is a programme's
# own folder with its courses underneath, not a list of programmes.
PLURAL_PROGRAM_WORDS = frozenset({"programs", "majors", "minors", "pathways"})
PLURAL_CREDENTIAL_WORDS = frozenset(
    {"degrees", "certificates", "certifications", "credentials", "diplomas"}
)
_SEGMENT_WORD_RE = re.compile(r"[-_]+")

# The program page of a vendor that keeps all of them at one address:
# Acalog's preview_program.php.
PROGRAM_URL_ENDPOINT_RE = re.compile(
    r"preview_program\.php|program_?detail", re.IGNORECASE
)

# Words naming courses: /courses/alan/, /course-descriptions/phys/,
# /course-outlines/, preview_course.php. Needed because some catalogs
# encode credits in the course number and print no credits value at all,
# so a whole page of course descriptions holds zero course blocks. On its
# own it proves nothing, so the rule that reads it also wants
# MIN_COURSE_LIST_CODES distinct codes on the page.
COURSE_URL_RE = re.compile(r"course|subject", re.IGNORECASE)


def has_program_structure(terms: list[str]) -> bool:
    """True when the page talks about its own requirements.

    The question this answers: a page holding twenty course codes is either
    a credential printing what it requires or a run of course descriptions.
    Only the first prints a total, a requirements heading, or a plan of
    study. The terms have to come from the page's content: CourseLeaf's
    sidebar links "Degree Requirements" on every page, which kept every
    graduate course listing at the University of Arkansas from being a
    course page.
    """
    return any(term in PROGRAM_STRUCTURE_TERMS for term in terms)


def program_structure_terms(lines: list[str]) -> list[str]:
    """The structure terms a page prints as a heading, not in a sentence.

    Same discipline as total_credits_line, for the same reason and the
    same page: a film course whose prerequisite reads "and 45 total credit
    hours completed" is not a program printing its total, and reading it
    as one stopped a page of film course descriptions being a course page.
    """
    return sorted(
        name
        for name, rule in PROGRAM_TERM_RES.items()
        if name in PROGRAM_STRUCTURE_TERMS
        and any(
            len(line) <= SHORT_LINE_CHARS and rule.search(line)
            for line in lines
        )
    )


def award_matches(text: str) -> list[re.Match[str]]:
    """Every award this text names, in the order it names them.

    Where two patterns match at the same place, the longer comes first, so
    "M.S.E.E." is quoted rather than the "M.S." it starts with.
    """
    found = list(CREDENTIAL_AWARD_RE.finditer(text or ""))
    found.extend(DOTTED_DEGREE_RE.finditer(text or ""))
    return sorted(found, key=lambda match: (match.start(), -len(match[0])))


def credential_award(text: str) -> re.Match[str] | None:
    """Where this text first names an award, so the caller can quote it.

    Every page of a catalog carries an award word somewhere, because the
    main menu is called "Degrees & Certificates". So this is only worth
    reading on the parts of a page that are about the page, never on the
    whole of it.
    """
    found = award_matches(text)
    return found[0] if found else None


def _blank_negations(text: str) -> str:
    """The text with "not a degree" blanked out, offsets unchanged."""
    return NEGATED_AWARD_RE.sub(lambda match: " " * len(match.group(0)), text)


def _specific(matches: list[re.Match[str]]) -> list[re.Match[str]]:
    return [
        match
        for match in matches
        if not GENERIC_AWARD_RE.match(match.group(0).strip())
    ]


def specific_award(text: str) -> str | None:
    """The first award this text names that says which award it is.

    "Degree" and "credential" say that some award exists. "Associate in",
    "Certificate", "B.S.E." and "Professional Series" say which one.
    """
    found = _specific(award_matches(_blank_negations(text or "")))
    return found[0].group(0) if found else None


def singular_award(text: str) -> str | None:
    """The first award this text names that is one award, not a list.

    "Degrees Conferred: M.S.E.E., Ph.D." gives M.S.E.E.; "Graduate
    Certificates and Microcertificates Offered" gives nothing.
    """
    found = _specific(award_matches(_blank_negations(text or "")))
    for match in found:
        if not PLURAL_AWARD_RE.match(match.group(0).strip()):
            return match.group(0)
    return None


def award_family(award: str) -> str:
    """Degree, certificate, or license: the kind of award, not which."""
    if _LICENSE_FAMILY_RE.search(award):
        return "license"
    if _CERTIFICATE_FAMILY_RE.search(award):
        return "certificate"
    return "degree"


def names_a_listing(name: str) -> bool:
    """True when a page's name says it lists awards or programs.

    "Graduate Certificates", "Programs of Study" and "Associate in Applied
    Science" each head a page listing many programs. Their requirements
    may all be printed there, and it is still not one program's page.
    """
    cleaned = _blank_negations(name or "")
    return bool(
        LISTING_NAME_RE.search(cleaned) or AWARD_TYPE_ONLY_RE.match(cleaned)
    )


def names_a_list_or_rule(name: str) -> bool:
    """True when a page's name says it lists, rules, or is an award type.

    "Degrees and Certificates", "Graduation Requirements" and "Associate in
    Applied Science" each say the page is not about one credential, which
    is worth more than a URL that files it under /degrees/.
    """
    cleaned = _blank_negations(name or "")
    return bool(
        LISTING_NAME_RE.search(cleaned)
        or POLICY_NAME_RE.search(cleaned)
        or AWARD_TYPE_ONLY_RE.match(cleaned)
    )


def award_in_name(name: str) -> str | None:
    """The award a page's own name carries, when it names one credential.

    "Associate in Science, Business Administration" and "Accounting
    (A.A.S.)" do. "Degrees and Certificates" lists, "Graduation
    Requirements" is a rule, "Associate in Applied Science" is the award
    type's own page, and "Associate Degree and Certificate Requirements"
    names two kinds of award; none of those is one credential.
    """
    cleaned = _blank_negations(name or "")
    if not cleaned.strip() or names_a_list_or_rule(name):
        return None
    found = _specific(award_matches(cleaned))
    if len({award_family(match.group(0)) for match in found}) != 1:
        return None
    return found[0].group(0)


def award_in_heading(heading: str) -> str | None:
    """The award a section heading names, when it names exactly one.

    "Requirements for B.S. in Chemical Engineering" names one. "Minimum
    Requirements for the B.S.E. or B.S. or B.S.N. Degree" is a college's
    rule for all of them, and "Certificates and Microcertificates" is a
    list.
    """
    cleaned = _blank_negations(heading or "")
    if LISTING_NAME_RE.search(cleaned):
        return None
    found = _specific(award_matches(cleaned))
    if not found:
        return None
    between = cleaned[found[0].end() : found[-1].start()]
    if len(found) > 1 and AWARD_LIST_SEPARATOR_RE.search(between):
        return None
    return found[0].group(0)


def is_contact_line(line: str) -> bool:
    """True when this line is how to reach someone, not the page's prose.

    It names a role and says how to reach them. Both halves matter: a
    sentence that mentions an advisor is the page talking, and a string
    of telephone numbers with no role is a table.
    """
    return bool(
        CONTACT_LINE_RE.search(line or "")
        and PHONE_OR_EMAIL_RE.search(line or "")
    )


def award_in_name_line(line: str) -> str | None:
    """The award a badge line names, when the line is nothing but the award.

    "Associate in Science" and "Graduate Microcertificate in Regression"
    are badges. "Ph.D. Program Director" and "Director, Master of Social
    Work Program" are the people who run the program, and "Christopher
    Nelson, Ph.D." is one of them.
    """
    line = (line or "").strip()
    if not AWARD_NAME_LINE_RE.match(line) or CONTACT_LINE_RE.search(line):
        return None
    return specific_award(line)


def _intro_subject(intro: str) -> str:
    """The first sentence's subject: its words before the verb."""
    first = _SENTENCE_END_RE.split(intro, maxsplit=1)[0]
    subject = _INTRO_VERB_RE.split(first, maxsplit=1)[0]
    if not _INTRO_ARTICLE_RE.match(subject):
        return ""
    if len(subject.split()) > INTRO_SUBJECT_WORDS:
        return ""
    return subject


def award_in_intro(intro: str, name: str) -> str | None:
    """The award the first paragraph says the page is about.

    Four ways of saying it: the award in the subject of the first sentence
    ("The graduate microcertificate in Regression provides"), the program
    calling itself "this degree", the award followed by the page's own name
    ("the Graduate Certificate Program in Building-Level Administration"),
    and the name followed by the award ("Special Education Transition
    Services Graduate Certificate is designed").
    """
    intro = intro or ""
    subject = _intro_subject(intro)
    if subject:
        award = specific_award(subject)
        if award:
            return award
        generic = _SUBJECT_AWARD_NOUN_RE.search(subject)
        if generic is not None:
            return generic.group(1)
    this_award = _THIS_AWARD_RE.search(intro)
    if this_award is not None:
        return this_award.group(1)
    bare = _TRAILING_CODE_RE.sub("", name or "").strip()
    if len(bare) < 4:
        return None
    own = re.search(_OWN_AWARD_WORDS + re.escape(bare), intro, re.IGNORECASE)
    if own is not None:
        return specific_award(own.group(0))
    if intro.lower().startswith(bare.lower()):
        rest = intro[len(bare) : len(bare) + INTRO_NAME_REACH_CHARS]
        if _NAME_THEN_AWARD_RE.match(rest):
            return specific_award(rest)
    return None


def is_outcomes_lead_in(line: str) -> bool:
    """True when this line introduces a list of learning outcomes.

    The whole line names the list ("Student Learning Outcomes"), or it is
    a sentence ending in a colon that introduces one ("Upon completion of
    this program students will be able to:"). A course title is never one,
    and neither is a mission statement or the ABET program educational
    objectives, whose bullets read like outcomes and describe careers.
    """
    line = (line or "").strip()
    if not line or len(line) > OUTCOME_ITEM_MAX_CHARS:
        return False
    if COURSE_TITLE_RE.match(line) or OUTCOMES_EXCLUDED_RE.search(line):
        return False
    if len(line) <= SECTION_HEADING_CHARS and OUTCOMES_HEADING_RE.match(line):
        return True
    return line.endswith(":") and bool(OUTCOMES_LEAD_IN_RE.search(line))


def is_outcome_statement(line: str) -> bool:
    """True when this line reads as one learning outcome.

    It opens with the verb an outcome is written with ("Demonstrate safe
    laboratory practices"), with "An ability to", or with "Graduates will".
    It is a sentence, not a heading ending in a colon, and not a course.
    """
    line = (line or "").strip()
    return (
        OUTCOME_ITEM_MIN_CHARS <= len(line) <= OUTCOME_ITEM_MAX_CHARS
        and not line.endswith(":")
        and not COURSE_TITLE_RE.match(line)
        and bool(OUTCOME_STATEMENT_RE.match(line))
    )


def names_an_organization_or_policy(name: str) -> bool:
    """True when the page is a college's, or a rule's, not a program's."""
    return bool(ORG_NAME_RE.match(name or "")) or bool(
        POLICY_NAME_RE.search(name or "")
    )


def url_label(template: str) -> str | None:
    """Credential or LearningOpportunity by URL shape alone, or None.

    A segment counts whole, or by its words when it is a phrase and one
    of them is a section word in the plural. See PLURAL_PROGRAM_WORDS.
    """
    if PROGRAM_URL_ENDPOINT_RE.search(template):
        return LABEL_LEARNING_OPPORTUNITY
    path = template.split("?", 1)[0].lower()
    segments = [segment for segment in path.split("/") if segment]
    # The last segment is the page itself, so it never names its kind.
    for segment in segments[:-1]:
        if segment in CREDENTIAL_URL_SEGMENTS:
            return LABEL_CREDENTIAL
        if segment in PROGRAM_URL_SEGMENTS:
            return LABEL_LEARNING_OPPORTUNITY
        words = set(_SEGMENT_WORD_RE.split(segment))
        if words & PLURAL_CREDENTIAL_WORDS:
            return LABEL_CREDENTIAL
        if words & PLURAL_PROGRAM_WORDS:
            return LABEL_LEARNING_OPPORTUNITY
    return None


# --- policies, archives, and pages that are not pages -------------------------

# A page explaining how to read course descriptions. It is full of course
# codes and describes none of them.
POLICY_OR_DEFINITION_RE = re.compile(
    r"\bcourse\s+numbering\b|\bnumbering\s+system\b"
    r"|\bhow\s+to\s+read\s+(?:a\s+|the\s+)?course\b"
    r"|\bkey\s+to\s+course\s+descriptions?\b"
    r"|\bcourse\s+description\s+(?:key|legend|format|guide)\b"
    r"|\bdefinition\s+of\s+(?:a\s+)?credit\s+hours?\b"
    r"|\bcredit\s+hour\s+(?:definition|policy)\b"
    r"|\bexplanation\s+of\s+course\b",
    re.IGNORECASE,
)

# A past catalog, in the banners Acalog and CourseLeaf print.
ARCHIVED_RE = re.compile(
    r"\barchived?\s+catalog\b|\bcatalog\s+archive\b"
    r"|\bthis\s+(?:is|was)\s+an\s+archived?\b"
    r"|\bno\s+longer\s+(?:current|in\s+effect)\b"
    r"|\bprevious\s+(?:catalog|edition)\b"
    r"|\bfor\s+(?:reference|historical)\s+purposes\s+only\b",
    re.IGNORECASE,
)

# "2026-2027", "2026/2027" or "2026-27". The first year has to start with
# 20, so a phone number and a credit range are not catalog years.
CATALOG_YEAR_RE = re.compile(r"\b(20\d{2})\s*(?:-|/|to)\s*(20\d{2}|\d{2})\b")

# Nothing was really captured. Four families:
#
#   the error    - 404 has to be error-shaped. On its own it matched the
#                  area code in a phone number, which marked a real program
#                  page empty and dropped it from the sample population.
#   the wall     - the crawler reached a login, not a page
#   the bot wall - Cloudflare and friends answer 200 with prose, so without
#                  this a De Anza block page profiled as a real course page
#   the soft 404 - a themed "that page has moved" that also answers 200,
#                  which is how a dead BC3 program page stayed in the run
EMPTY_OR_ERROR_RE = re.compile(
    r"\b(?:page|file|document)\s+not\s+found\b"
    r"|\b404\s+(?:error|not\s+found)\b|\berror\s+404\b|\bHTTP\s+404\b"
    r"|\ban\s+error\s+(?:has\s+)?occurred\b|\baccess\s+denied\b"
    r"|\bplease\s+log\s*in\b|\bsign\s+in\s+to\s+continue\b"
    r"|\byou\s+do\s+not\s+have\s+permission\b"
    r"|\byou\s+have\s+been\s+blocked\b|\bunable\s+to\s+access\b"
    r"|\bcloudflare\s+ray\s+id\b|\battention\s+required\b"
    r"|\bverify\s+(?:that\s+)?you\s+are\s+(?:a\s+)?human\b"
    r"|\bchecking\s+your\s+browser\b|\benable\s+javascript\b"
    r"|\bthat\s+page\s+has\s+moved\b"
    r"|\bpage\s+you\s+are\s+looking\s+for\b"
    r"|\bno\s+longer\s+exists\b",
    re.IGNORECASE,
)

# Tab panels, found on the attribute rather than in the text: role="tab", or
# a class naming a tab strip. Content in a hidden panel is still content.
TAB_ROLE_RE = re.compile(r"\btab\b", re.IGNORECASE)
TAB_CLASS_RE = re.compile(r"\btabs?\b|\btab-(?:nav|list|pane)\b", re.IGNORECASE)

# --- shared text helpers ------------------------------------------------------

DIGIT_RUN_RE = re.compile(r"\d+")
WHITESPACE_RE = re.compile(r"\s+")
_TRIM_PUNCTUATION = " \t:;,.-_*|/\\"

MARKER_NAMES = (
    "lecture_lab_credit_numbers",
    "lab_clinical_field_study_hours",
    "printed_zero_hours",
    "ceu",
    "prerequisite",
    "corequisite",
    "prerequisite_corequisite_combined",
    "recommended",
    "learning_outcomes",
    "program_markers",
    "credential_award",
    "multi_credential_page",
    "course_requirement_list",
    "published_as",
    "tabs_present",
    "archived",
    "catalog_year",
    "policy_or_definition_page",
    "multi_course_page",
    "empty_or_error_page",
)

# One line per marker on what it costs an extractor that ignores it.
MARKER_MEANING = {
    "lecture_lab_credit_numbers": (
        "Three numbers in a row are lecture, lab, and credit hours. Read as "
        "one value they become a wrong credit count."
    ),
    "lab_clinical_field_study_hours": (
        "Contact hours are printed beside credits. An extractor that takes "
        "the first number on the line reports contact hours as credits."
    ),
    "printed_zero_hours": (
        "A printed 0 is a real value, not a missing one. Treating it as "
        "absent loses the distinction between zero-credit and unstated."
    ),
    "ceu": (
        "Continuing education units are not academic credits and must not "
        "be mapped to the same field."
    ),
    "prerequisite": "A prerequisite list to parse into course references.",
    "corequisite": "A corequisite list, which is a different relation.",
    "prerequisite_corequisite_combined": (
        "One heading covers both relations, so splitting on the heading "
        "alone assigns corequisites to the prerequisite field."
    ),
    "recommended": (
        "A recommendation is not a requirement and must not become one."
    ),
    "learning_outcomes": (
        "A competency list lives here, which is a separate entity from the "
        "course or credential that carries it."
    ),
    "program_markers": (
        "The page describes a program, not a course, so course fields will "
        "be empty or borrowed from a listing."
    ),
    "credential_award": (
        "The page names the award it grants. In CTDL that award is a "
        "Credential, a different entity from the program that leads to it "
        "and from the courses the program requires."
    ),
    "multi_credential_page": (
        "The page prints the requirements of several credentials, one "
        "section each, so one record per page is wrong. It is the "
        "department's page, not one credential's."
    ),
    "course_requirement_list": (
        "The page prints a list of the courses it requires. Those codes "
        "are references to courses described elsewhere, so an extractor "
        "that reads them as descriptions invents a course per row."
    ),
    "published_as": (
        "What the publisher says this page is, in JSON-LD, microdata, or "
        "the type its CMS stamped on the node. It is the one statement on "
        "the page that was not written to be read as prose."
    ),
    "tabs_present": (
        "Content sits in hidden tab panels. Text taken from the visible tab "
        "alone silently drops the rest."
    ),
    "archived": (
        "The page is a past catalog. Mixing it with the current one "
        "produces two versions of the same course."
    ),
    "catalog_year": (
        "The year range this page belongs to, which pins every value on it "
        "to a time frame."
    ),
    "policy_or_definition_page": (
        "The page explains how to read courses. It contains course codes "
        "but describes none of them."
    ),
    "multi_course_page": (
        "Several courses share the page, so one record per page is wrong."
    ),
    "empty_or_error_page": (
        "Nothing was captured. Extracting produces an empty record that "
        "looks like a real one."
    ),
}


def url_template(url: str) -> str:
    """Path and query with every run of digits replaced by {n}."""
    parsed = urlsplit(url)
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return DIGIT_RUN_RE.sub("{n}", f"{path}{query}")


def collapse(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_field_label(text: str) -> str | None:
    """Turn a label as printed into the form the vocabulary counts.

    Lowercase, collapsed spaces, no trailing colon or punctuation, digits
    replaced by #. Anything too long to be a key, or carrying a course code,
    is not a label: those are sentences and course titles.
    """
    raw = collapse(text)
    if not raw:
        return None
    trimmed = raw.strip(_TRIM_PUNCTUATION)
    if not trimmed or len(trimmed) > MAX_FIELD_LABEL_CHARS:
        return None
    if COURSE_CODE_RE.search(trimmed):
        return None
    label = DIGIT_RUN_RE.sub("#", trimmed).lower()
    return label or None


def evidence(text: str, match: re.Match[str] | None = None) -> str:
    """A short quote showing why a marker fired."""
    if match is not None:
        start = max(0, match.start() - 20)
        text = text[start : match.end() + 40]
    return collapse(text)[:MARKER_EVIDENCE_CHARS]


def quote_around(text: str, phrase: str) -> str:
    """A short quote of the text, around the first place it says phrase."""
    return evidence(text, re.search(re.escape(phrase), text))


def catalog_year_value(text: str) -> str | None:
    """The catalog year range as printed, written out in full."""
    match = CATALOG_YEAR_RE.search(text or "")
    if not match:
        return None
    start, end = match.group(1), match.group(2)
    if len(end) == 2:
        end = f"{start[:2]}{end}"
    return f"{start}-{end}"


def course_codes(text: str) -> list[str]:
    return COURSE_CODE_RE.findall(text)


def normalize_course_code(code: str) -> str:
    """ACCT 130, ACCT-130 and ACCT130 are one course, not three."""
    return _CODE_SPACING_RE.sub("", code).upper()


def course_block_count(text: str, ignore: set[str] | None = None) -> int:
    """How many distinct courses the page describes.

    A code on its own is a cross-reference; a code with a credits, units,
    or hours value near it is the course being described. The same code
    printed twice is still one course. A breadcrumb above a heading repeats
    it, and counting both made every single-course page on a Clean Catalog
    site look like a page holding two, which marked it multi_course_page
    and made extraction skip it.

    `ignore` is the codes the markup shows to be references, which are
    never descriptions however they read once flattened. A transfer
    equivalency table prints a code, a title and a credit count per row,
    so on the text alone every row is a course being described.
    """
    described: set[str] = set()
    for match in COURSE_CODE_RE.finditer(text):
        window = text[match.end() : match.end() + COURSE_BLOCK_WINDOW]
        if CREDIT_VALUE_RE.search(window):
            described.add(normalize_course_code(match.group(0)))
    return len(described - (ignore or set()))


def near_course_code(text: str, match: re.Match[str]) -> bool:
    """True when a course code sits within one block window of the match."""
    start = max(0, match.start() - COURSE_BLOCK_WINDOW)
    window = text[start : match.end() + COURSE_BLOCK_WINDOW]
    return bool(COURSE_CODE_RE.search(window))


def program_terms(text: str) -> list[str]:
    """Which program vocabulary terms the page uses, by name."""
    return sorted(
        name for name, rule in PROGRAM_TERM_RES.items() if rule.search(text)
    )


def split_course_title(line: str) -> tuple[str, str, str]:
    """A course-block title line as its code, its name and its credits.

    CourseLeaf prints all three on one line - "ASTR 50303.  Astrophysics
    I: Stars and Planetary Systems.  3 Hours." - so a course page there
    has no labelled fields at all to read. The credits are optional,
    because a zero-credit seminar prints none, and so is the name.
    """
    text = collapse(line)
    code_match = COURSE_CODE_RE.search(text)
    if code_match is None or code_match.start() > 0:
        return "", "", ""
    rest = text[code_match.end() :].strip(" .:-–")
    credits = ""
    credits_match = COURSE_BLOCK_CREDITS_RE.search(rest)
    if credits_match is not None:
        credits = credits_match.group("credits")
        if credits_match.group("maximum"):
            credits = f"{credits}-{credits_match.group('maximum')}"
        rest = rest[: credits_match.start()].strip(" .:-–")
    return code_match.group(0), rest, credits


def total_credits_line(lines: list[str]) -> str:
    """The line printing the program's credit total, or "".

    A total is a line of its own or the last row of the requirement table,
    never a clause inside a sentence. See TOTAL_CREDITS_RE.

    The label and its number may be on two lines, because Clean Catalog
    prints them as two paragraphs inside one div, so each short line is
    read with the short line after it as well.
    """
    for index, line in enumerate(lines):
        if len(line) > SHORT_LINE_CHARS:
            continue
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if len(following) > SHORT_LINE_CHARS:
            following = ""
        for candidate in (line, f"{line} {following}".strip()):
            if TOTAL_CREDITS_RE.search(candidate):
                return candidate
    return ""


def distinct_awards(awards: list[str]) -> list[str]:
    """The awards named, with the same award written two ways counted once.

    "M.S." and "MS" are one award; "M.S." and "Ph.D." are two. Case and
    dots are folded; "Master of Science" stays apart from "M.S.", because
    the point of counting is to find the page that prints the
    requirements of several credentials at once.

    A bare level - "Bachelor", "Master of", "Associate degree" - says a
    degree of that level exists without saying which, so it drops out as
    soon as the page names a specific award. The Eleanor Mann School of
    Nursing heads one section "B.S.N." and another "Bachelor of Science
    in Nursing", which is one credential written twice, not two.
    """
    seen: dict[str, str] = {}
    for award in awards:
        key = award.replace(".", "").replace(" ", "").lower()
        seen.setdefault(key, award)
    specific = [
        award
        for award in seen.values()
        if not BARE_AWARD_LEVEL_RE.match(award.strip())
    ]
    return sorted(specific or seen.values())
