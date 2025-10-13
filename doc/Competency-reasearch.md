<!-- - Test harness changes to allow testing variations, in text and in order
- Bulk of work: Tens of prompt iterations to parse new catalogues while not regressing others
- Additional logic added to the xTRA engine, 
    - exploratory prompt during extraction
    - dedicated entity presence prompt
- Prompt & Field simplification
  - Ask the LLM to extract less, remove IDs, remove competency description
    - Description vs core competency text was also a source of model response variations -->

## Intro

Using OpenAI LLMs to capture itemized competencies a student earns from the learning program detail page.

## Conclusion

OpenAI 4o and o3 models in their current form are not able to produce consistent result with the required prompt complexity. The models show their limitation in their inherent randomness by producing varied results for identical prompts. Adjusting `temperature` does not produce any perceivable effects. Reducing `top_p` to 0.5 does improve consistency but it does not fully eliminate response variations. Unsurprisingly, the success rate seems to be related to the prompt size and number of instructions as well as the page content length.

When using OpenAI LLMs to extract competencies, the prompt complexity has a tendency of increasing to accommodate the different catalogues and their page formats. The simpler catalogues (Bristol CC) have been cheap and easy to extract while the more complex required more instructions as the model would confuse itemized competencies with course descriptions talking about skills or with tech used in the learning program or with links to sub programs contained in the same page. Asking the LLM to handle each edge case in a single prompt tends to decrease the quality of the output and devising prompts tailored to each catalog defeats the generalized approach advantage the project is seeking. Moreover, adding more instructions to the prompt can help with the specific extraction we are advising for but generally tends to affect previous successfully tested extractions.  

Results have improved when we aimed for prompt specialization. This divided the number of problems to be solved between multiple prompts leading to higher quality results. We extended the extraction phase into 3 other sub-phases with separating extraction from entity detection - asking the LLM to determine if the page contains information to be extracted and with sub-page exploration into 3 separate prompts.

Focusing on the example exports we received from CE instead of the minimum data policy we noticed we can further reduce complexity of requested output by removing the description column and the ID column. This eliminated a considerable source of variation responses and consolidated the consistency of the existing prompts but the variations are still present and we still see a threshold of instructions we can ask from the LLM until it starts disregarding them as if not included.

## Strategies used

1. Prompt engineering
  
    * We invested in a high number (order of tens) of prompt iterations, adding, simplifying or rewording instructions.
    * This had the most potential ROI as it could have allowed us to reach the goal without major logic changes in xTRA.
    * Few-shot learning has only been useful for the very specific cases exemplified while generally regressing the quality of results
    * Marking page content included as markdown in code block has improved quality visibly.

2. Model invocation method and parameters
    
    * We tested OpenAI 4o and o3-mini. 4o showed the most promise for our task being able to more accurately follow our prompts
    * Adjusting `temperature` has not provided any improvements 
    * Decreasing `top_p` to 0.5 has improved the consistency of results but it has not eliminated response variation
    * We implemented JSON schema structured output (from the function call method) as testing in OpenAI playground revealed the function call to play a detrimental role, this helped improving results slightly
    * We added a flag to customize screenshot inclusion for different class types and we turned off screenshots for competencies - which showed marginally better results.

3. Prompt specializations

    * We divided the extraction prompt into 3 separate prompts
      - Presence detection for competencies in the page
      - Sub-page link detection for sub pages that could contain competencies related to the program (Indiana State University)
      - Extraction prompt
    * Reducing main prompt size and complexity has yielded the highest jump in quality, however this requires specialized logic and increases extraction costs

4. Content verification
  
    * We already have content verification logic in xTRA for course extraction, however the inclusion of the response is not always sufficient for competencies as the LLM would reuse most of the sentence but still miss certain parts or cut the sentence short.
    * We used the NLP `compromise` library to split page content into phrases which we would verify against the LLM output. We would sent a 2nd request to the LLM exemplifying the incomplete extraction but the LLM would continue to respond with the same extraction.

## Future research leads

* Improve page content simplification
* Add more models to the tests
* Fine-tune existing models, potentially integrate UI feedback so users could feed model tuning data.
* Adjust xTRA to test extractions within a single conversation (more messages in the same invocation)
* Refactor xTRA system to allow more advanced conversation logic, decreasing costs for class specific prompt specialization as well as conversation - for example we could resolve messages with a reducer like pattern that associated with the entity would allow configuring agent messaging logic expressively.

## Existing challenges examples

### Variation examples

#### Ivy Tech

##### Example 1
Competency framework sometimes includes the course ID, sometimes it does not. The prompt used is the same.
https://catalog.ivytech.edu/preview_course_nopop.php?catoid=9&coid=40320

```
- Expected
+ Received

  Array [
    Object {
-     "competency_framework": "Health & Wellness Lifespan",
+     "competency_framework": "NSGA 142 Health & Wellness Lifespan",
      "language": "en",
      "text": like("Identify therapeutic communication techniques that develop the nurse-patient relationship and promote intra- and interprofessional collaboration with health care teams."),
    },
    Object {
-     "competency_framework": "Health & Wellness Lifespan",
+     "competency_framework": "NSGA 142 Health & Wellness Lifespan",
      "language": "en",
      "text": like("Demonstrate knowledge in assessment of patients across the lifespan, understanding normal and abnormal variations of findings while recognizing patients and their families as unique individuals with varied preferences, values, and needs."),
    },
    Object {
-     "competency_framework": "Health & Wellness Lifespan",
+     "competency_framework": "NSGA 142 Health & Wellness Lifespan",
      "language": "en",
      "text": like("Discuss the impact of health promotion, disease prevention, and health disparities to promote healthy outcomes in a variety of diverse groups across the lifespan."),
    },
    Object {
-     "competency_framework": "Health & Wellness Lifespan",
+     "competency_framework": "NSGA 142 Health & Wellness Lifespan",
      "language": "en",
      "text": like("Describe concepts utilized to promote diversity and a culture of caring and advocacy that demonstrates respect for individual patient preferences and respect for individual values and needs."),
    },
    Object {
-     "competency_framework": "Health & Wellness Lifespan",
+     "competency_framework": "NSGA 142 Health & Wellness Lifespan",
      "language": "en",
      "text": like("Identify basic nutritional concepts of patients across the lifespan."),
    },
    Object {
-     "competency_framework": "Health & Wellness Lifespan",
+     "competency_framework": "NSGA 142 Health & Wellness Lifespan",
      "language": "en",
      "text": like("Identify cognitive and psychosocial development across the lifespan and the nurse’s role when caring for patients with alterations in growth and development."),
    },
    Object {
-     "competency_framework": "Health & Wellness Lifespan",
+     "competency_framework": "NSGA 142 Health & Wellness Lifespan",
      "language": "en",
      "text": like("Describe the role of the nurse as an educator, counselor, and facilitator in patient centered care."),
    },
    Object {
-     "competency_framework": "Health & Wellness Lifespan",
+     "competency_framework": "NSGA 142 Health & Wellness Lifespan",
      "language": "en",
      "text": like("Demonstrate knowledge of factors that affect patient mobility and interventions that promote safe patient handling and movement across the life span."),
    },
  ]
```

###### Corrective actions

- *action*: Adjust prompt to instruct LLM to extract information exactly as it is in the page
  - *outcome*: LLM will continue to respond with variations.
- *action*: Reduce model `temperature` parameter to 0.5 and 0.3.
  - *outcome*: LLM will continue to respond with the same variation rate, after dropping below 0.3, it would vary more towards responding with an empty list.
- *action*: Reduce model `top_p` parameter to 0.3 and to 0.5
  - *outcome*: Reduction of `top_p` beneath 0.5 causes model to return empty lists more often where competencies are present. 0.5 appears to work best with variation rate reduced to 1/4th. Variations not eliminated.
- *action*: Re-invoke the LLM when the exact phrase is not found, while exemplifying the incorrectly extracted phrase
  - *outcome*: The model response stays the same.

##### Example 2
Number of extracted competencies varies randomly. There are 16 competencies listed, with #6, having 3 sub points. Model response varies between 16 and 19 competencies.

https://catalog.ivytech.edu/preview_course_nopop.php?catoid=9&coid=32130

###### Corrective actions

- *action*: Adjust prompt to instruct LLM to ignore sub levels of the list and take top level items only
  - *outcome*: LLM will continue to respond with the variations. 
- *action*: Reduce model `temperature` parameter to 0.5 and 0.3.
  - *outcome*: LLM will continue to respond with the same variation rate, after dropping below 0.3, it would vary more towards responding with an empty list.
- *action*: Reduce model `top_p` parameter to 0.3 and to 0.5
  - *outcome*: Reduction of `top_p` beneath 0.5 causes model to return empty lists more often where competencies are present. 0.5 appears to work best with variation rate reduced to 1/4th. Variations not eliminated.


#### Indiana State University

##### Example 1
1/3 of invocations would result in an empty list of competencies where items are expected.
https://catalog.indstate.edu/content.php?catoid=60&navoid=3240 

- *action*: Simplify extraction prompt by specializing the sub-page discovery in a separate prompt
  - *outcome*: In a 8-10 invocation sample rate this has seen 100% expected response.

#### Atlantic Cape CC

##### Example 1
Competency framework varies between test runs as per below.
https://careertraining.atlanticcape.edu/training-programs/ace-personal-trainer-with-fitness-health-internship/

```
- Expected
+ Received

  Array [
    Object {
-     "competency_framework": "ACE Personal Trainer with Fitness and Health Internship",
+     "competency_framework": "ACE Personal Trainer",
      "language": "en",
      "text": "Functional Training: Assessments, Programming, and Progressions for Posture, Movement, Core, Balance, and Flexibility",
    },
    Object {
-     "competency_framework": "ACE Personal Trainer with Fitness and Health Internship",
+     "competency_framework": "ACE Personal Trainer",
      "language": "en",
      "text": "Professional and Legal Responsibilities, Scope of Practice, and Business Strategies for Personal Trainers",
    },
    Object {
-     "competency_framework": "ACE Personal Trainer with Fitness and Health Internship",
+     "competency_framework": "ACE Personal Trainer",
      "language": "en",
      "text": "Special Exercise Programming Topics: Mind-body Exercise, Special Populations, and Exercise Implications of Common Musculoskeletal Injuries",
    },
    Object {
-     "competency_framework": "ACE Personal Trainer with Fitness and Health Internship",
+     "competency_framework": "ACE Personal Trainer",
      "language": "en",
      "text": "Physiological Assessments",
    },
    Object {
-     "competency_framework": "ACE Personal Trainer with Fitness and Health Internship",
+     "competency_framework": "ACE Personal Trainer",
      "language": "en",
      "text": "Cardiorespiratory Training: Programming and Progressions",
    },
    Object {
-     "competency_framework": "ACE Personal Trainer with Fitness and Health Internship",
+     "competency_framework": "ACE Personal Trainer",
      "language": "en",
      "text": "Resistance Training: Programming and Progressions",
    },
  ]
```

### Inability to extract exact information

### Indiana State University

#### Example 1
The model rephrases items from `1.1 Students are able to describe the language and procedures associated with financial accounting.` to `Describe the language and procedures associated with financial accounting`

##### Corrective actions

- *action*: Adjust prompt to instruct LLM to extract information exactly as it is in the page
  - *outcome*: LLM will continue to simplify the phrasing and drop the list number.

Output:
```
- Expected
+ Received

  Array [
    Object {
      "competency_framework": like("Accounting Learning Outcomes"),
      "language": "en",
-     "text": like("1.1 Students are able to describe the language and procedures associated with financial accounting."),
+     "text": "Describe the language and procedures associated with financial accounting",
    },
    Object {
      "competency_framework": like("Accounting Learning Outcomes"),
      "language": "en",
-     "text": like("2.1 Students are able to define and identify cost accounting theory and concepts."),
+     "text": "Define and identify cost accounting theory and concepts",
    },
    Object {
      "competency_framework": like("Accounting Learning Outcomes"),
      "language": "en",
-     "text": like("3.1 Students are able to define the terminology of tax accounting."),
+     "text": "Define the terminology of tax accounting",
    },
    Object {
      "competency_framework": like("Accounting Learning Outcomes"),
      "language": "en",
-     "text": like("4.1 Students are able to identify audit and assurance concepts."),
+     "text": "Identify audit and assurance concepts",
    },
    Object {
      "competency_framework": like("Accounting Learning Outcomes"),
      "language": "en",
-     "text": like("5.1 Students are able to analyze, evaluate, and synthesize information for financial reporting."),
+     "text": "Analyze, evaluate, and synthesize information for financial reporting",
    },
    Object {
      "competency_framework": like("Accounting Learning Outcomes"),
      "language": "en",
-     "text": like("6.1 Students are able to analyze, evaluate, and synthesize information to solve cost accounting problems."),
+     "text": "Analyze, evaluate, and synthesize information to solve cost accounting problems",
    },
    Object {
      "competency_framework": like("Accounting Learning Outcomes"),
      "language": "en",
-     "text": like("7.1 Students are able to analyze information and apply tax principles to solve taxation problems."),
+     "text": "Analyze information and apply tax principles to solve taxation problems",
    },
    Object {
      "competency_framework": like("Accounting Learning Outcomes"),
      "language": "en",
      "text": like("8.1 Students are able to properly plan an audit and assess the financial statements for the risk of material misstatement due to errors for fraud."),
    },
    Object {
      "competency_framework": like("Accounting Learning Outcomes"),
      "language": "en",
-     "text": like("9.1 Students are able to determine technological threats to accounting systems and identify applicable controls to mitigate risks."),
+     "text": "Determine technological threats to accounting systems and identify applicable controls to mitigate risks",
    },
    Object {
      "competency_framework": like("Accounting Learning Outcomes"),
      "language": "en",
-     "text": like("10.1 Students are able to use applicable technology tools to evaluate and present accounting information."),
+     "text": "Use applicable technology tools to evaluate and present accounting information",
    },
    Object {
      "competency_framework": like("Accounting Learning Outcomes"),
      "language": "en",
-     "text": like("11.1 Students are able to execute business processes involved in an accounting cycle essential to using integrated accounting software."),
+     "text": "Execute business processes involved in an accounting cycle essential to using integrated accounting software",
    },
    Object {
      "competency_framework": like("Accounting Learning Outcomes"),
      "language": "en",
-     "text": like("12.1 Students are able to use generalized audit software to simulate audit processes."),
+     "text": "Use generalized audit software to simulate audit processes",
    },
  ]
```

### Passaic County CC

#### Example 1

The model extracts `Associate in Applied Science in Accounting` instead of just `Accounting`
https://catalog.pccc.edu/program/178/

