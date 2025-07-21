# Semantic similarity between two texts

LLMs used by xTRA seem to perform well on extracting the requested information however they rarely extract it exactly the same. We observe higher variations in more ambiguous sources such as when aiming for Credential descriptions which are often expressed alongside program descriptions in the same paragraphs or sections. The resulting variation seems to be semantically stable however it is difficult to assert correctness with absolute methods - such as the ones we currently use in our automated test harness. This renders our testing less useful which also makes it difficult to maintain the quality of our extractions as we keep developing the system. One solution to this could be to use [cosine similarity](https://en.wikipedia.org/wiki/Cosine_similarity) between the factors represented by their embedding vectors as this should yield a semantic comparison which might be sufficient to assert that all extraction variations tends toward the same semantic center of gravity. OpenAI provides a model that generates the vectors from textual content, [here](https://platform.openai.com/docs/guides/embeddings).

In this document we explore the feasibility of using the embeddings for our test harness and we expose a few example to provide an understanding of what degree of similarity is achieved by this method. The main topics of interest will be:
  - Comparison examples to determine a equality threshold
  - Cost
  - Time required to get the embeddings from OpenAI, our tests see increasing in coverage which could lead to long test executions


## Credential Title Examples
Examples were ran with `text-embedding-3-small`

<table width="100%" border="0">
  <tr><td>Left</td><td>Right</td><td>Cosine similarity</td><td>Time (s)</td><td>Tokens used</td></tr>
<tr><td>Computer Information Systems - Programming Specialist</td><td>Computer Information Systems - Developer</td><td>0.7479367686532138</td><td>0.569s</td><td>11</td></tr>
<tr><td></td><td>Computer Information Systems</td><td>0.7275811252512632</td><td>0.655s</td><td>9</td></tr>
<tr><td></td><td>Computer Programmer</td><td>0.6581353077146881</td><td>0.61s</td><td>8</td></tr>
<tr><td></td><td>IT Software Developer</td><td>0.51902426656864</td><td>0.693s</td><td>9</td></tr>
<tr><td></td><td>Software Engineer</td><td>0.47889354710365495</td><td>0.785s</td><td>8</td></tr>
<tr><td></td><td>Information Technology</td><td>0.47608394521119207</td><td>0.606s</td><td>8</td></tr>
<tr><td></td><td>Systems of Information</td><td>0.45316827905148166</td><td>0.59s</td><td>9</td></tr>
<tr><td></td><td>Computer Gamer</td><td>0.33026738051405263</td><td>0.932s</td><td>8</td></tr>
<tr><td>Physical Education - Teacher Education, A.S.</td><td>Physical Education - Teacher Education, A.S.</td><td>0.9998977635461961</td><td>0.591s</td><td>18</td></tr>
<tr><td></td><td>Physical Education - Teacher Education, Associate of Science</td><td>0.8794513824894623</td><td>0.653s</td><td>18</td></tr>
<tr><td></td><td>Teacher of Physical Education</td><td>0.731982004476562</td><td>0.739s</td><td>13</td></tr>
<tr><td></td><td>Physical Education Teacher</td><td>0.8003424771088492</td><td>0.723s</td><td>12</td></tr>
<tr><td></td><td>Teacher of Physics</td><td>0.49839019487046965</td><td>0.765s</td><td>12</td></tr>
<tr><td></td><td>Teacher of Psychology</td><td>0.47758230386709843</td><td>0.623s</td><td>12</td></tr>
<tr><td></td><td>Physically Present</td><td>0.2800358280668618</td><td>1.362s</td><td>12</td></tr>
<tr><td>Business Administration</td><td>Business Admin</td><td>0.8981093996033166</td><td>0.691s</td><td>4</td></tr>
<tr><td></td><td>Business Leadership</td><td>0.7003538750341048</td><td>0.643s</td><td>4</td></tr>
<tr><td></td><td>Business Management</td><td>0.819251119438805</td><td>0.692s</td><td>4</td></tr>
<tr><td></td><td>Business Manager</td><td>0.6868935933847727</td><td>0.783s</td><td>4</td></tr>
<tr><td></td><td>Administrator</td><td>0.39482191236588504</td><td>0.719s</td><td>3</td></tr>
<tr><td></td><td>Show business</td><td>0.31768853402172376</td><td>0.765s</td><td>4</td></tr>
<tr><td></td><td>Business</td><td>0.6217146676401093</td><td>0.752s</td><td>3</td></tr>
</table>



## Credential Description Examples
Examples ran with `text-embedding-3-small`

<table width="100%" border="0">
    <tr><td>Left</td><td>Right</td><td>Cosine similarity</td><td>Time (s)</td><td>Tokens used</td></tr>
<tr><td>By utilizing biology, chemistry and engineering principles, learn to create extremely small electronic and mechanical devices.</td><td>Using biology, chemistry and engineering ideas, learn to create extremely small electronic and mechanical devices.</td><td>0.9515293972825998</td><td>2.796s</td><td>37</td></tr>
<tr><td></td><td>With biology, chemistry and engineering concepts, learn to make microscopic electronic and mechanical devices.</td><td>0.8785102745251966</td><td>1.542s</td><td>36</td></tr>
<tr><td></td><td>Following biology, chemistry and engineering principles, understand how to realize microscopic electronic and mechanical things.</td><td>0.8273284338756601</td><td>0.987s</td><td>37</td></tr>
<tr><td></td><td>Using biology and chemistry principles, learn to create extremely small electronic devices.</td><td>0.9374095603665172</td><td>0.803s</td><td>33</td></tr>
<tr><td></td><td>Using biology and engineering ideas, learn to make small mechanical devices.</td><td>0.8188106932342671</td><td>2.694s</td><td>32</td></tr>
<tr><td></td><td>Using engineering principles, learn to produce extremely small electronic and mechanical devices.</td><td>0.8932643497212962</td><td>0.871s</td><td>33</td></tr>
<tr><td></td><td>Learn to make very small electronic and mechanical devices.</td><td>0.7819096325382597</td><td>0.8s</td><td>29</td></tr>
<tr><td></td><td>Learn to make electronic and mechanical devices.</td><td>0.6847207037463873</td><td>1.705s</td><td>27</td></tr>
<tr><td></td><td>The student will study electronic device and circuit behavior, basic chemistry and fabrication techniques used to create micron and submicron scale structures. Techniques covered include electron beam epitaxy, plasma etching, reactive ion etching, metallization, thick and thin film deposition and photolithography.</td><td>0.5440677656560775</td><td>0.804s</td><td>75</td></tr>
<tr><td></td><td>This program provides the student with a comprehensive background in microelectronics and nanofabrication technology.</td><td>0.4897160565480765</td><td>1.541s</td><td>38</td></tr>
<tr><td>The Associate in Fine Arts (AFA) in Art - Studio concentrates on painting and drawing. Experienced and accomplished faculty members mentor students as they cultivate skills and build a portfolio required for transfer into a four-year Bachelor of Fine Arts (BFA) program.</td><td>The Associate in Fine Arts (AFA) in Art - Studio focuses on painting and drawing, with skilled faculty guiding students as they develop techniques and assemble portfolios necessary for transfer into a four-year Bachelor of Fine Arts (BFA) program.</td><td>0.9915229629946466</td><td>1.578s</td><td>99</td></tr>
<tr><td></td><td>Students enrolled in the AFA in Art - Studio program concentrate on painting and drawing, receiving mentorship from experienced faculty as they refine their abilities and prepare transfer portfolios for BFA programs.</td><td>0.8875280405023269</td><td>1.01s</td><td>88</td></tr>
<tr><td></td><td>The AFA in Art - Studio emphasizes painting and drawing, offering guidance from accomplished instructors as students hone their skills and build portfolios to support their transition to four-year BFA programs.</td><td>0.8945381409306055</td><td>0.792s</td><td>87</td></tr>
<tr><td></td><td>In the AFA in Art - Studio track, students work on painting and drawing under the mentorship of experienced faculty, while developing the portfolios necessary to transfer into Bachelor of Fine Arts programs.</td><td>0.8562490675793071</td><td>1.847s</td><td>89</td></tr>
<tr><td></td><td>This Associate in Fine Arts (AFA) - Studio Art degree is designed for aspiring painters and illustrators, pairing them with expert faculty who help develop the technical skills and portfolios needed for BFA program transfer.</td><td>0.9217775535185704</td><td>0.716s</td><td>93</td></tr>
<tr><td></td><td>With a focus on painting and drawing, the AFA in Art - Studio prepares students for future artistic study through skill development and personalized mentorship, guiding them toward a smooth transition into BFA programs.</td><td>0.8836483436157898</td><td>1.084s</td><td>91</td></tr>
<tr><td></td><td>Creative students in the AFA - Studio Art program explore painting and drawing while collaborating with dedicated artists as mentors, building the foundations and portfolios needed to continue their academic journey in BFA studies.</td><td>0.8541483282101396</td><td>0.818s</td><td>89</td></tr>
<tr><td></td><td>The AFA in Studio Art is where creativity meets purpose: students immerse in painting and drawing, work closely with artist-mentors, and craft portfolios that open doors to four-year fine arts adventures.</td><td>0.8379738746533372</td><td>0.757s</td><td>92</td></tr>
<tr><td></td><td>In the Graphic Design concentration, students apply artistic techniques to branding and visual storytelling. With mentorship from professional designers, they build portfolios showcasing their work, preparing for transfer into competitive Bachelor’s programs in applied arts.</td><td>0.5098987099408842</td><td>0.732s</td><td>93</td></tr>
</table>


## Conclusions

### Observations

- The cosine similarity seems to be good tool to assert similarity between extracted and expected information
- The costs using `text-embedding-3-small` is very small (see below)
- Con: Missing words from one of the terms does not impact the coefficient which could be undesirable if applications required that it the assertions ensure no information is missing
- Tooling for using cosine similarity embeddings vectors has been added to the project with an example test at: [../server/tests/extractions/credentials/embeddings.test.ts](../server/tests/extractions/credentials/embeddings.test.ts)

While it might not be a definitive answer for longer worded terms it can be one of the composite KPIs used to assert precision of the model. Combined with word saliency evaluation between the terms we could answer the question that the bodies of text are both close semantically and discuss the same key concepts.

### Cost estimation

Total tokens used for the title examples: 193 total with an average of 8,7 tokens per entry.
Total tokens used for the description examples: 1198 with an average of 63 per entry.

Currently we have 14 tests, each with an average of 4 extraction tests, each test asserting 1 title and 1 description. Cost could be estimated as follows:

```MATH
14 * 4 = 56
```

```MATH
56 * 8.7 = 461.1
```
```MATH
56 * 63 = 3528
```
```MATH

Tokens = 3528+461.1 = 3989.1
```
At the time of writing (Jul. 2025), the `text-embedding-3-small` embeddings model has a price of $0.02/per 1M token, a test run could cost around $0,000079