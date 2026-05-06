## Agentic Crawler MVP
This tool combines agentic website navigation (Anthropic SDK) with the xTRA extraction system. The agent is responsible for finding the detail pages (the pages that contain the course/program/etc overview information) and submitting the URLs to the tool (registerPage) we provide it. Once registered, we rely on the existing prompts and infrastructure (OpenAI SDK) to convert text to structured information.

We generate a CSV at the end of the extraction without using the Database. This because of MVP reasons (we needed a quick unblocking of certain catalogues)

Before running it is required to have the packages installed with pnpm and have Claude MCP setup for Pupeteer configured on the system.

To run, issue:

```bash
pnpm agentic:experiment -- antelope-course-competencies
```

The 2nd part `antelope-course-competencies` corresponds to the desired catalogue from ./catalogues. We support a few other flags and environment variables, please see run.ts to see what they are.