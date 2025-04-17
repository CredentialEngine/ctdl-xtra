# xTRA extraction operations - LLM Usage

## Intro

xTRA is designed to work with learning institutions catalogues with the main objective to leverage LLMs for extracting and categorizing information from online websites in order to index structured information such as courses, learning programs or competencies into relational data structures to be used to form relational trees or searchable information graphs.

## Extraction stages

xTRA allows the user to use web UI to add a new catalogue URL. Using only the URL the system goes through the following stages:

### Stage 1 - Extraction recipe detection

Using the URL given as the root of the web site navigation tree xTRA uses LLM prompts to determine the navigation structure. It asks the LLM to identify what type of page is the root URL. Usually, the catalogue main URL is a category page - a page that contains sub categories of other categories or courses directly. Using the 4o model, we determine which page type it is by describing the structure. If the page is a container page, xTRA uses the LLM to identify the regex pattern of relevant sub links. If the page is a detail page - a leaf of the navigation tree, that page is marked accordingly and enqueued for extraction. 

#### Example - University of Pennsylvania

Catalogue URL: https://catalog.upenn.edu/courses/

The catalogue main page is simplified to its markdown version:

```markdown
*   [Skip to Content](#content)
*   [AZ Index](/azindex/)
*   [Catalog Home](/)
*   [Institution Home](/)

*   [Home](/)/
*   Courses A-Z

[Print Options](#print-dialog)

2024-25 Catalog

2024-25 Catalog

*   [Undergraduate Catalog](/undergraduate/)
*   [Graduate Catalog](/graduate/)
*   [Programs A-​Z](/programs/)
*   [Courses A-​Z](#)
    
*   [Course Attributes A-​Z](/attributes/)
*   [Search Courses](https://courses.upenn.edu/)
*   [Pennbook](/pennbook/)
*   [Faculty Handbook](/faculty-handbook/)

Courses A-Z
===========

Courses are organized by subject and include courses at the undergraduate and graduate levels. 

Search courses by keyword using the [Advanced Course Search](https://courses.upenn.edu/).

For more information, see the guide to [Course Numbering and Academic Credit](/undergraduate/policies-procedures/course-exam/course-numbering-academic-credit/) at the University of Pennsylvania.

  

*   #
*   [A](#a5181714)
*   [B](#b5181714)
*   [C](#c5181714)
*   [D](#d5181714)
*   [E](#e5181714)
*   [F](#f5181714)
*   [G](#g5181714)
*   [H](#h5181714)
*   [I](#i5181714)
*   [J](#j5181714)
*   [K](#k5181714)
*   [L](#l5181714)
*   [M](#m5181714)
*   [N](#n5181714)
*   [O](#o5181714)
*   [P](#p5181714)
*   [Q](#q5181714)
*   [R](#r5181714)
*   [S](#s5181714)
*   [T](#t5181714)
*   [U](#u5181714)
*   [V](#v5181714)
*   [W](#w5181714)
*   X
*   [Y](#y5181714)
*   [Z](#z5181714)

A
-

*   [Academic Foundations (ACFD)](/courses/acfd/)
*   [Accounting (ACCT)](/courses/acct/)
*   [Africana Studies (AFRC)](/courses/afrc/)
*   [American Sign Language (ASLD)](/courses/asld/)
*   [Amharic (AMHR)](/courses/amhr/)
*   [Anatomy (ANAT)](/courses/anat/)
*   ETC...

B
-

*   [Bachelor of Applied Arts & Sciences (BAAS)](/courses/baas/)
*   [Behavioral & Decision Sciences (BDS)](/courses/bds/)
*   [Bengali (BENG)](/courses/beng/)
*   [Benjamin Franklin Seminars (BENF)](/courses/benf/)
*   ETC...

# Redacted for brevity

Y
-

*   [Yiddish (YDSH)](/courses/ydsh/)
*   [Yoruba (YORB)](/courses/yorb/)

Z
-

*   [Zulu (ZULU)](/courses/zulu/)

[Back to Top](#header)

Print Options
-------------

[Send Page to Printer](#)

_Print this page._

[Download Page (PDF)](/courses/courses.pdf)

_The PDF will include all information unique to this page._

[2024-25 University Catalog](/pdf/University%20of%20Pennsylvania%20Catalog.pdf)

_A PDF of the entire 2024-25 catalog._

[2024-25 Undergraduate Catalog](/pdf/University%20of%20Pennsylvania%20Undergraduate%20Catalog.pdf)

_A PDF of the 2024-25 Undergraduate catalog._

[2024-25 Graduate Catalog](/pdf/University%20of%20Pennsylvania%20Graduate%20Catalog.pdf)

_A PDF of the 2024-25 Graduate catalog._

[Cancel](#)"
```

xTRA prompts the model with the following text:

```
  You are an agent in a system that autonomously scrapes educational data from the internet.

  For this task, you're being given the content of a web page that we believe is relevant
  for finding courses (educational courses offered by an institution) entities.

  Your goal is to identify the primary type of content that features in the page.
  There are descriptions for the content types we're looking for below.

  In order to successfully identify it, follow these instructions:

  1. Walk through the content in the page, step by step, trying to identify the main content section.
  2. In order to do that, note that things like navigation menus, headers, footers, sidebars and
     such might also show up in the page. You can use those pieces as hints and context data,
     but you're looking for the main content section.
  3. When evaluating the main content section, go through it carefully and consider:
     - Is the content in the main section mostly links to individual courses such as ACCT 101 (course links page)?
     - Is the content in the main section mostly links to category pages (course categories page)?
     - Is the content in the main section mostly details such as full descriptions for courses (course detail page)?
     - Is the content something else that doesn't match the descriptions above?
     Sometimes the page may look like a mix of content. In that case:
     - Prioritize content in the main section. If the content in the main section is a course detail,
       even if it's just a single one, consider it a course detail page.
  4. Take into account both the URLs and the text content of the links when you find some that
     may help you make a decision.
  5. Look at the screenshot, if one is provided, to get a better understanding of the page.

  PAGE TYPES
  ==========

  page_type DETAIL_LINKS:

  It has links to the courses of an institution.
  Typically, the course's identifier and title
  show up in the link (example: ACCT 101).
  Presumably, detailed information about the courses will be present in the destination links.

  <example>
  ...
  # Main Content

  [ACCT 101 - Financial Accounting](course.php?catoid=7&coid=1)
  [ACCT 102 - Another course](course.php?catoid=7&coid=2)
  [ACCT 103 - Yet Another course](course.php?catoid=7&coid=3)
  ...

  > page_type: DETAIL_LINKS
  > Reason: The content is mostly links to specific courses like ACCT 101.
  </example>

  page_type DETAIL:

  It has details for the courses of an institution directly in the page.
  Unlike A, pretty much all information about the courses is already in the page.
  In other words, it doesn't have links to detail pages; it IS a detail page.

  For course, we need the following fields:

  course_id: code/identifier for the course (example: "AGRI 101")
course_name: name for the course (for example "Landscape Design")
course_description: the full description of the course. If there are links, only extract the text.
course_prerequisites: if the text explicitly mentions any course prerequisite(s) or course requirements,
          extract them as is - the full text for prerequisites, as it may contain observations.
          (If there are links in the text, only extract the text without links.)
          - If it mentions course corequisites, leave blank.
          - If it mentions mutually exclusive courses, leave blank.
          - If it mentions courses that must be taken concurrently, leave blank.
          - Only extract the text if it's explicitly stated that the course has prerequisites/requirements.
          - Otherwise leave blank.
          
course_credits_min: min credit
course_credits_max: max credit (if the page shows a range). If there is only a single credit information in the page, set it as the max.
course_credits_type: type of credits, infer it from the page.
          IMPORTANT:
            - Only infer the type if it's CLEARLY stated in the page somewhere.
            - If you can't infer the type, set it as "UNKNOWN"
            - MUST BE either UNKNOWN or: AcademicYear, CarnegieUnit, CertificateCredit, ClockHour, CompetencyCredit, ContactHour, DegreeCredit, DualCredit, QuarterHour, RequirementCredit, SecondaryDiplomaCredit, SemesterHour, TimeBasedCredit, TypeBasedCredit, UNKNOWN
            - Sometimes the course has a special type of credit: CEUs (Continuing Education Units).
              (If you see "CEU" values in the page, that's the same as Continuing Education Units)
            - In that case, there's a separate field: course_ceu_credits.
            - A course may have both normal credits like the types we mentioned above, and CEUs.

          It is ok to have the course credits set to a number and the course credits type set to "UNKNOWN"
          if the content shows the credits value but doesn't mention the type.

          It is ok to have CEUs and course credits type set to "UNKNOWN" if the page doesn't mention the type
          but does mention CEUs.

          EVEN MORE IMPORTANT REGARDING COURSE CREDITS:

          IF THERE ARE NO CLEARLY STATED COURSE CREDITS INFORMATION, LEAVE ALL COURSE CREDITS FIELDS BLANK.
          ONLY INCLUDE COURSE CREDITS INFORMATION IF IT'S EXPLICITLY STATED IN THE PAGE!
        
course_ceu_credits: CEU credits

  <example>
  ...
  # Main Content

  ## ACCT 101
  Financial Accounting
  A study of the underlying theory and application of financial accounting concepts.
  ...

  > page_type: DETAIL
  > Reason: The content is full details for courses.
  </example>

  page_type CATEGORY_LINKS:

  It has links to programs, careers, degrees, or course category pages.
  In other words, the page links to "categories" or "groups" of courses.
  We'll find more detailed course information if we navigate to those category pages.

  <example>
  ...
  # Main Content

  *   [Academic Skills courses](/catalog/course-descriptions/asc/)
  *   [Accounting courses](/catalog/course-descriptions/acct/)
  *   [Agricultural Economics courses](/catalog/course-descriptions/agec/)
  ...

  > page_type: CATEGORY_LINKS
  > Reason: The content is mostly links to generic subjects like "Accounting" and not to individual courses.
  </example>

  Blank page_type:

  Other. It doesn't match the descriptions above.

  IMPORTANT
  =========
  - only submit ONE tool call. There is ONE primary content type in the page.
  - the examples are not exhaustive or meant to represent the whole universe of content out there.
    They're just examples that give you an idea of what the content looks like.

  URL: https://catalog.upenn.edu/courses/

  PAGE CONTENT
  ============
  *   [Skip to Content](#content)
*   [AZ Index](/azindex/)
*   [Catalog Home](/)
*   [Institution Home](/)

*   [Home](/)/
*   Courses A-Z

[Print Options](#print-dialog)

2024-25 Catalog

2024-25 Catalog

*   [Undergraduate Catalog](/undergraduate/)
*   [Graduate Catalog](/graduate/)
*   [Programs A-​Z](/programs/)
*   [Courses A-​Z](#)
    
*   [Course Attributes A-​Z](/attributes/)
*   [Search Courses](https://courses.upenn.edu/)
*   [Pennbook](/pennbook/)
*   [Faculty Handbook](/faculty-handbook/)

Courses A-Z
===========

Courses are organized by subject and include courses at the undergraduate and graduate levels...

*   #
*   [A](#a5181714)
*   [B](#b5181714)

*   X
*   [Y](#y5181714)
*   [Z](#z5181714)

A
-

*   [Academic Foundations (ACFD)](/courses/acfd/)
*   [Accounting (ACCT)](/courses/acct/)
*   [Africana Studies (AFRC)](/courses/afrc/)
*   [American Sign Language (ASLD)](/courses/asld/)
*   [Amharic (AMHR)](/courses/amhr/)


B
-

*   [Bachelor of Applied Arts & Sciences (BAAS)](/courses/baas/)
*   [Behavioral & Decision Sciences (BDS)](/courses/bds/)
*   [Bengali (BENG)](/courses/beng/)
*   [Benjamin Franklin Seminars (BENF)](/courses/benf/)
*   [Biochemistry & Molecular Biophysics (BMB)](/courses/bmb/)
*   [Biochemistry (BCHE)](/courses/bche/)
*   [Bioengineering (BE)](/courses/be/)

--- REDACTED FOR BREVITY -----
`
```

The prompt returns the following JSON: 
```JSON
{
  "page_type": "CATEGORY_LINKS",
}
```

indicating the page as a page containing categories of courses which xTRA further prompts the LLM to detect the pattern of sub-page links. For the specific example the prompt use for URL pattern detection is:

```
    The following webpage has a list of links to detail pages of a certain type.

    Your goal is to create a single JS regexp that will find all the URLs of those links.

    Go through the content carefully and think about a regexp that finds all the links
    with the type above.

    We are going to use it like this:

    > const detailUrls = content.match(new RegExp(regexp, "g"));

    DESCRIPTION OF THE LINKS
    ========================

    
    COURSE CATEGORY LINKS
    It has links to programs, careers, degrees, or course category pages.

    In other words, the page links to "categories" or "groups" of courses,
    and we'll find more detailed course information if we navigate to those category pages.

    EXAMPLE ON HOW TO IDENTIFY THE CATEGORIES:

    ...
    Possibly links to other things (that are not categories)... (we don't want these)
    ...
    # Main Content

    *   [Accounting (ACCT)](/catalog/course/acct/)
    *   [Agricultural Economics (AGEC)](/catalog/course/agec/)
    *   [Agricultural Systems Management (ASM)](/catalog/course/asm/)
    *   [Agriculture (AGRI)](/catalog/course/agri/)
    *   [Allied Health (AH)](/catalog/course/ah/)
    *   [Animal and Range Science (ANSC)](/catalog/course/ansc/)
    *   [Anthropology (ANTH)](/catalog/course/anth/)
    *   [Architectural Drafting & Estimating Technology (ARCT)](/catalog/course/arct/)
    *   [Art (ART)](/catalog/course/art/)
    *   [Artificial Intelligence (AI)](/catalog/course/ai/)
    *   [Automation Management (AM)](/catalog/course/am/)
    *   [Automotive Collision Technology (ABOD)](/catalog/course/abod/)
    *   [Automotive Technology (AUTO)](/catalog/course/auto/)
    ...
    Possibly links to other things (that are not categories)... (we don't want these)
    ...

    > page_type: category_links
    > Reason: The content is mostly links to generic subjects like "Accounting" and "Art"
      and not to individual courses.

    

    GUIDELINES FOR REGEXP CREATION
    ==============================

    Content:
    [Course Page A](course_page.php?id=1)
    [Course Page B](course_page.php?id=2)
    [Course Page C](course_page.php?id=3)
    Regexp: course_page.php?id=d+

    Content:
    [Course Page A](/course_page.php?id=1)
    [Course Page B](/course_page.php?id=2)
    [Course Page C](/course_page.php?id=3)
    Regexp: /course_page.php?id=d+

    Content:
    [Course Page A](https://www.blablabla.com/course_page.php?id=1)
    [Course Page B](https://www.blablabla.com/course_page.php?id=2)
    [Course Page C](https://www.blablabla.com/course_page.php?id=3)
    Regexp: https://www.blablabla.com/course_page.php?id=d+

    Content:
    [Course Page A](www.blablabla.com/course_page.php?id=1)
    [Course Page B](www.blablabla.com/course_page.php?id=2)
    [Course Page C](www.blablabla.com/course_page.php?id=3)
    Regexp: www.blablabla.com/course_page.php?id=d+

    IMPORTANT
    =========
    - only extract links for the type we mentioned above.
    - do not attempt to transform links in any way.
    - do not add any extra characters to the links.
    - we will run the regexp as you give it, on the content we gave you.
    - only submit one tool call with one regexp and total_links.
      There must be one regexp for all the links.
    - example_matches: some example matches that we should find when running your regexp. Max 5 examples.
    - it's obvious, but the URLs detected by your regexp should be in the page content!
    - if we give you multiple pages, make sure the single regexp works for all of them.

    The examples are EXAMPLES. Don't just blindly submit those as an answer. Create a regexp for the specific
    page content we give you.

    <page_content>
    *   [Skip to Content](#content)
*   [AZ Index](/azindex/)
*   [Catalog Home](/)
*   [Institution Home](/)

*   [Home](/)/
*   Courses A-Z

[Print Options](#print-dialog)

2024-25 Catalog

2024-25 Catalog

*   [Undergraduate Catalog](/undergraduate/)
*   [Graduate Catalog](/graduate/)
*   [Programs A-​Z](/programs/)
*   [Courses A-​Z](#)
    
*   [Course Attributes A-​Z](/attributes/)
*   [Search Courses](https://courses.upenn.edu/)
*   [Pennbook](/pennbook/)
*   [Faculty Handbook](/faculty-handbook/)

Courses A-Z
===========

Courses are organized by subject and include courses at the undergraduate...   

*   #
*   [A](#a5181714)
*   [B](#b5181714)
*   [W](#w5181714)
*   X
*   [Y](#y5181714)
*   [Z](#z5181714)

A
-

*   [Academic Foundations (ACFD)](/courses/acfd/)
*   [Accounting (ACCT)](/courses/acct/)
*   [Africana Studies (AFRC)](/courses/afrc/)
*   [American Sign Language (ASLD)](/courses/asld/)
*   [Amharic (AMHR)](/courses/amhr/)
*   [Anatomy (ANAT)](/courses/anat/)
*   [Ancient History (ANCH)](/courses/anch/)

REDACTED FOR BREVITY

</page_content>
```

The prompt above yields the following JSON:
```JSON
{
  "regexp": "\\/courses\\/[a-z]+\\/",
  "example_matches": [
    "/courses/acfd/",
    "/courses/acct/",
    "/courses/afrc/",
    "/courses/asld/",
    "/courses/amhr/",
  ],
}
```

xTRA samples a few of the example matches and replays the page type detection and link pattern detection until a leaf page (DETAIL) is reached. After a number of iteration we should have this resulting recipe:

```JSON
{
  "links": {
    "pageType": "DETAIL"
  },
  "pageType": "CATEGORY_LINKS",
  "linkRegexp": "\\/courses\\/[^\\s)]+\\/"
}
```

### Stage 2 - Fetching information

Using the recipe, xTRA fetches pages using a headless browser and stores the HTML, the page screenshot and a custom simplified markdown version of each page. There are no LLM prompts in this stage.

### Stage 3 - Extraction

After stage 2 gathered the catalogue content, xTRA prepares a an extraction LLM prompt for each detail page. The prompt is customized depending on the catalogue type (the class of information the user wants to extract) and sent to the OpenAI platform for processing. Each prompt invocation is verified for hallucination and is performed again if the content is found to not exist in within the page. xTRA uses few-shot examples to inform the model of what it extracted incorrectly.


#### Example - University of Pennsylvania

Page URL: http://localhost:5173/extractions/69/steps/1639/items/6355

Prompt:
```
Your goal is to extract course data from this page.
       Extract the data EXACTLY as it shows up in the page.
       NEVER paraphrase, rewrite or change content unless requested.


We are looking for the following fields:

course_id: code/identifier for the course (example: "AGRI 101") (REQUIRED)
course_name: name for the course (for example "Landscape Design") (REQUIRED)
course_description: the full description of the course. If there are links, only extract the text. (REQUIRED)
course_prerequisites: if the text explicitly mentions any course prerequisite(s) or course requirements,
          extract them as is - the full text for prerequisites, as it may contain observations.
          (If there are links in the text, only extract the text without links.)
          - If it mentions course corequisites, leave blank.
          - If it mentions mutually exclusive courses, leave blank.
          - If it mentions courses that must be taken concurrently, leave blank.
          - Only extract the text if it's explicitly stated that the course has prerequisites/requirements.
          - Otherwise leave blank.
          
course_credits_min: min credit
course_credits_max: max credit (if the page shows a range). If there is only a single credit information in the page, set it as the max.
course_credits_type: type of credits, infer it from the page.
          IMPORTANT:
            - Only infer the type if it's CLEARLY stated in the page somewhere.
            - If you can't infer the type, set it as "UNKNOWN"
            - MUST BE either UNKNOWN or: AcademicYear, CarnegieUnit, CertificateCredit, ClockHour, CompetencyCredit, ContactHour, DegreeCredit, DualCredit, QuarterHour, RequirementCredit, SecondaryDiplomaCredit, SemesterHour, TimeBasedCredit, TypeBasedCredit, UNKNOWN
            - Sometimes the course has a special type of credit: CEUs (Continuing Education Units).
              (If you see "CEU" values in the page, that's the same as Continuing Education Units)
            - In that case, there's a separate field: course_ceu_credits.
            - A course may have both normal credits like the types we mentioned above, and CEUs.

          It is ok to have the course credits set to a number and the course credits type set to "UNKNOWN"
          if the content shows the credits value but doesn't mention the type.

          It is ok to have CEUs and course credits type set to "UNKNOWN" if the page doesn't mention the type
          but does mention CEUs.

          EVEN MORE IMPORTANT REGARDING COURSE CREDITS:

          IF THERE ARE NO CLEARLY STATED COURSE CREDITS INFORMATION, LEAVE ALL COURSE CREDITS FIELDS BLANK.
          ONLY INCLUDE COURSE CREDITS INFORMATION IF IT'S EXPLICITLY STATED IN THE PAGE!
        
course_ceu_credits: CEU credits



PAGE URL:

https://catalog.upenn.edu/courses/cit/

SIMPLIFIED PAGE CONTENT:

*   [Skip to Content](#content)
*   [AZ Index](/azindex/)
*   [Catalog Home](/)
*   [Institution Home](/)

*   [Home](/)/
*   [Courses A-Z](/courses/)/
*   Computer and Information Technology (CIT)

[Print Options](#print-dialog)

2024-25 Catalog

2024-25 Catalog

*   [Undergraduate Catalog](/undergraduate/)
*   [Graduate Catalog](/graduate/)
*   [Programs A-​Z](/programs/)
*   [Courses A-​Z](/courses/)
    *   [Computer and Information Technology (CIT)](#)
*   [Course Attributes A-​Z](/attributes/)
*   [Search Courses](https://courses.upenn.edu/)
*   [Pennbook](/pennbook/)
*   [Faculty Handbook](/faculty-handbook/)

Computer and Information Technology (CIT)
=========================================

**CIT 5200 Introduction to Robotics**

This course introduces the fundamental geometric, kinematic, dynamic, and computational principles underlying modern robotic systems. The main topics of the course include: rotation matrices, homogeneous transformations, manipulator forward and inverse kinematics, mobile robot kinematics, Jacobians, and trajectory planning. The purpose of the course is to provide you with a mathematical, computational and practical foundation for future explorations into the robotics field. Students should have knowledge of simple geometry and trigonometry (triangle inequalities, sine, cosine), previous exposure to linear algebra (matrices and vectors), and previous programming experience. Although [MEAM 2110](/search/?P=MEAM%202110) is often listed as a prerequisite for the on-campus version of this course, it is not strictly required. Previous experience in simple rigid body kinematics will be useful.

Fall or Spring

1 Course Unit

**CIT 5820 Blockchains and Cryptography**

Blockchains or Distributed Ledger Technology (DLT) provide a novel method for decentralizing databases in the presence of mutually distrustful or malicious agents. The promise of DLTs has attracted billions of dollars in investments, yet the true potential of these systems remains unclear. This course introduces students to the fundamentals of cryptography and distributed systems that underpin modern blockchain platforms -- including collision-resistant hash functions, digital signatures and classical consensus algorithms. From there, we will examine the architecture of modern blockchain platforms, and develop tools to analyze and interact with them in Python. At the end of this course, students should understand the power and limitations of blockchain technology, and be able to develop software that interacts with current blockchain platforms.

Fall or Spring

1 Course Unit

**CIT 5900 Programming Languages and Techniques**

This course is an introduction to fundamental concepts of programming and computer science for students who have little or no experience in these areas. Includes an introduction to programming using Python, where students are introduced to core programming concepts like data structures, conditionals, loops, variables, and functions. Also provides an introduction to basic data science techniques using Python. The second half of this course is an introduction to object-oriented programming using Java, where students are introduced to polymorphism, inheritance, abstract classes, interfaces, and advanced data structures. Students will also learn how to read and write to files, connect to databases, and use regular expressions to parse text. This course includes substantial programming assignments in both Python and Java, and teaches techniques for test-driven development and debugging code.

Fall or Spring

1 Course Unit

**CIT 5910 Introduction to Software Development**

Introduction to fundamental concepts of programming and computer science. Principles of modern object-oriented programming languages: abstraction, types, polymorphism, encapsulation, inheritance, and interfaces. This course will also focus on best practices and aspects of software development such as software design, software testing, pair programming, version control, and using IDEs. Substantial programming assignments.

Fall or Spring

1 Course Unit

**CIT 5920 Mathematical Foundations of Computer Science**

This course introduces you to math concepts that form the backbone of the majority of computer science. Topics covered include sets, functions, permutations and combinations, discrete probability, expectation, mathematical Induction and graph theory. The goal of the course is to ensure that students are comfortable enough with the math required for most of the CIS electives. [CIS 5020](/search/?P=CIS%205020) and [CIT 5960](/search/?P=CIT%205960) heavily rely on concepts taught in this course.

Fall or Spring

1 Course Unit

**CIT 5930 Introduction to Computer Systems**

This course provides an introduction to fundamental concepts of computer systems and computer architecture. You will learn the C programming language and an instruction set (machine language) as a basis for understanding how computers represent data, process information, and execute programs. The course also focuses on the Unix environment and includes a weekly hands-on lab session.

Fall or Spring

1 Course Unit

**CIT 5940 Data Structures and Software Design**

This course will focus on data structures, software design, and advanced Java. The course starts off with an introduction to data structures and basics of the analysis of algorithms. Important data structures covered will include arrays, lists, stacks, queues, trees, hash maps, and graphs. The course will also focus on software design and advanced Java topics such as software architectures, design patterns, networking, multithreading, and graphics. We will use Java for the entire course.

Fall or Spring

Prerequisite: [CIT 5910](/search/?P=CIT%205910)

1 Course Unit

**CIT 5950 Computer Systems Programming**

This course builds on your knowledge of C and focuses on systems programming for Linux, specifically the libraries that programmers use for threading and concurrency, synchronization, inter-process communication, and networking. The course also introduces the C++ programming language, and covers important concepts in modern operating systems, including processes, scheduling, caching, and virtual memory. After completing this course, you will have the requisite knowledge and experience for systems-focused CIS graduate-level electives.

Fall or Spring

Prerequisite: [CIT 5930](/search/?P=CIT%205930)

1 Course Unit

**CIT 5960 Algorithms and Computation**

This course focuses primarily on the design and analysis of algorithms. We will begin with sorting and searching algorithms and then spend most of the course on graph algorithms. In order to study graph algorithms, general algorithm design patterns like dynamic programming and greedy algorithms will be introduced. A section of this course is also devoted to understanding NP-Completeness.

Fall or Spring

Prerequisite: [CIT 5920](/search/?P=CIT%205920)

1 Course Unit

[Back to Top](#header)

Print Options
-------------

[Send Page to Printer](#)

_Print this page._

[Download Page (PDF)](/courses/cit/cit.pdf)

_The PDF will include all information unique to this page._

[2024-25 University Catalog](/pdf/University%20of%20Pennsylvania%20Catalog.pdf)

_A PDF of the entire 2024-25 catalog._

[2024-25 Undergraduate Catalog](/pdf/University%20of%20Pennsylvania%20Undergraduate%20Catalog.pdf)

_A PDF of the 2024-25 Undergraduate catalog._

[2024-25 Graduate Catalog](/pdf/University%20of%20Pennsylvania%20Graduate%20Catalog.pdf)

_A PDF of the 2024-25 Graduate catalog._

[Cancel](#)
```


The resulting JSON:

```
[
  {
    "course_id": "CIT 5200",
    "course_name": "Introduction to Robotics",
    "course_description": "This course introduces the fundamental geometric, kinematic, dynamic, and computational principles underlying modern robotic systems. The main topics of the course include: rotation matrices, homogeneous transformations, manipulator forward and inverse kinematics, mobile robot kinematics, Jacobians, and trajectory planning. The purpose of the course is to provide you with a mathematical, computational and practical foundation for future explorations into the robotics field. Students should have knowledge of simple geometry and trigonometry (triangle inequalities, sine, cosine), previous exposure to linear algebra (matrices and vectors), and previous programming experience. Although MEAM 2110 is often listed as a prerequisite for the on-campus version of this course, it is not strictly required. Previous experience in simple rigid body kinematics will be useful. Fall or Spring 1 Course Unit",
    "course_credits_min": 1,
    "course_credits_max": 1
  },
  {
    "course_id": "CIT 5820",
    "course_name": "Blockchains and Cryptography",
    "course_description": "Blockchains or Distributed Ledger Technology (DLT) provide a novel method for decentralizing databases in the presence of mutually distrustful or malicious agents. The promise of DLTs has attracted billions of dollars in investments, yet the true potential of these systems remains unclear. This course introduces students to the fundamentals of cryptography and distributed systems that underpin modern blockchain platforms -- including collision-resistant hash functions, digital signatures and classical consensus algorithms. From there, we will examine the architecture of modern blockchain platforms, and develop tools to analyze and interact with them in Python. At the end of this course, students should understand the power and limitations of blockchain technology, and be able to develop software that interacts with current blockchain platforms. Fall or Spring 1 Course Unit",
    "course_credits_min": 1,
    "course_credits_max": 1
  },
  {
    "course_id": "CIT 5900",
    "course_name": "Programming Languages and Techniques",
    "course_description": "This course is an introduction to fundamental concepts of programming and computer science for students who have little or no experience in these areas. Includes an introduction to programming using Python, where students are introduced to core programming concepts like data structures, conditionals, loops, variables, and functions. Also provides an introduction to basic data science techniques using Python. The second half of this course is an introduction to object-oriented programming using Java, where students are introduced to polymorphism, inheritance, abstract classes, interfaces, and advanced data structures. Students will also learn how to read and write to files, connect to databases, and use regular expressions to parse text. This course includes substantial programming assignments in both Python and Java, and teaches techniques for test-driven development and debugging code. Fall or Spring 1 Course Unit",
    "course_credits_min": 1,
    "course_credits_max": 1
  },
  {
    "course_id": "CIT 5910",
    "course_name": "Introduction to Software Development",
    "course_description": "Introduction to fundamental concepts of programming and computer science. Principles of modern object-oriented programming languages: abstraction, types, polymorphism, encapsulation, inheritance, and interfaces. This course will also focus on best practices and aspects of software development such as software design, software testing, pair programming, version control, and using IDEs. Substantial programming assignments. Fall or Spring 1 Course Unit",
    "course_credits_min": 1,
    "course_credits_max": 1
  },
  {
    "course_id": "CIT 5920",
    "course_name": "Mathematical Foundations of Computer Science",
    "course_description": "This course introduces you to math concepts that form the backbone of the majority of computer science. Topics covered include sets, functions, permutations and combinations, discrete probability, expectation, mathematical Induction and graph theory. The goal of the course is to ensure that students are comfortable enough with the math required for most of the CIS electives. CIS 5020 and CIT 5960 heavily rely on concepts taught in this course. Fall or Spring 1 Course Unit",
    "course_credits_min": 1,
    "course_credits_max": 1
  },
  {
    "course_id": "CIT 5930",
    "course_name": "Introduction to Computer Systems",
    "course_description": "This course provides an introduction to fundamental concepts of computer systems and computer architecture. You will learn the C programming language and an instruction set (machine language) as a basis for understanding how computers represent data, process information, and execute programs. The course also focuses on the Unix environment and includes a weekly hands-on lab session. Fall or Spring 1 Course Unit",
    "course_credits_min": 1,
    "course_credits_max": 1
  },
  {
    "course_id": "CIT 5940",
    "course_name": "Data Structures and Software Design",
    "course_description": "This course will focus on data structures, software design, and advanced Java. The course starts off with an introduction to data structures and basics of the analysis of algorithms. Important data structures covered will include arrays, lists, stacks, queues, trees, hash maps, and graphs. The course will also focus on software design and advanced Java topics such as software architectures, design patterns, networking, multithreading, and graphics. We will use Java for the entire course. Fall or Spring Prerequisite: CIT 5910 1 Course Unit",
    "course_prerequisites": "Prerequisite: CIT 5910",
    "course_credits_min": 1,
    "course_credits_max": 1
  },
  {
    "course_id": "CIT 5950",
    "course_name": "Computer Systems Programming",
    "course_description": "This course builds on your knowledge of C and focuses on systems programming for Linux, specifically the libraries that programmers use for threading and concurrency, synchronization, inter-process communication, and networking. The course also introduces the C++ programming language, and covers important concepts in modern operating systems, including processes, scheduling, caching, and virtual memory. After completing this course, you will have the requisite knowledge and experience for systems-focused CIS graduate-level electives. Fall or Spring Prerequisite: CIT 5930 1 Course Unit",
    "course_prerequisites": "Prerequisite: CIT 5930",
    "course_credits_min": 1,
    "course_credits_max": 1
  },
  {
    "course_id": "CIT 5960",
    "course_name": "Algorithms and Computation",
    "course_description": "This course focuses primarily on the design and analysis of algorithms. We will begin with sorting and searching algorithms and then spend most of the course on graph algorithms. In order to study graph algorithms, general algorithm design patterns like dynamic programming and greedy algorithms will be introduced. A section of this course is also devoted to understanding NP-Completeness. Fall or Spring Prerequisite: CIT 5920 1 Course Unit",
    "course_prerequisites": "Prerequisite: CIT 5920",
    "course_credits_min": 1,
    "course_credits_max": 1
  }
]
```